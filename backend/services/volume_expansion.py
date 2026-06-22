"""
物量展開サービス
工程接続に基づいてトポロジカル順に展開。
上流工程の処理量が下流工程の投入量になる。
"""
from datetime import datetime
import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import VolumePlan, VolumeConversionRule, VolumeExpansion, Process, ProcessConnection, Employee


def _time_to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _min_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _topological_sort(process_ids: List[str], connections: List) -> List[str]:
    """Return process_ids in topological order (upstream first)."""
    downstream_of: Dict[str, str] = {c.to_process_id: c.from_process_id for c in connections}
    visited = set()
    order = []

    def visit(pid: str):
        if pid in visited:
            return
        visited.add(pid)
        upstream = downstream_of.get(pid)
        if upstream and upstream in process_ids:
            visit(upstream)
        order.append(pid)

    for pid in process_ids:
        visit(pid)
    return order


def expand_volume(plan_date: str, db: Session) -> List[VolumeExpansion]:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    plans = db.query(VolumePlan).filter(VolumePlan.plan_date == plan_date).all()
    if not plans:
        return []

    plan_map: Dict[tuple, float] = {}
    for p in plans:
        plan_map[(p.volume_type, p.time_slot_start)] = float(p.volume)

    rules = db.query(VolumeConversionRule).all()
    rule_map: Dict[str, tuple] = {r.process_id: (r.source_type, float(r.conversion_rate)) for r in rules}

    connections = db.query(ProcessConnection).all()
    # downstream -> upstream
    upstream_of: Dict[str, str] = {c.to_process_id: c.from_process_id for c in connections}

    active_processes = {
        p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()
    }
    if not active_processes:
        return []

    employee_count = max(1, db.query(Employee).filter(Employee.is_active == 1).count())

    plan_slots = sorted(set(p.time_slot_start for p in plans))
    first_min = _time_to_min(plan_slots[0])

    # Generate slots from first plan slot to 23:30 to accommodate carry-over
    all_slots: List[str] = []
    t = first_min
    while t <= 23 * 60 + 30:
        all_slots.append(_min_to_time(t))
        t += 15

    # Topological order
    process_order = _topological_sort(list(active_processes.keys()), connections)

    db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == plan_date).delete()

    expansions: List[VolumeExpansion] = []
    slot_duration_hours = 15.0 / 60.0

    # throughput[process_id][slot] = items actually processed (passed to downstream)
    throughput: Dict[str, Dict[str, float]] = {}

    for process_id in process_order:
        proc = active_processes.get(process_id)
        if proc is None:
            continue

        base_productivity = float(proc.base_productivity)
        # Max throughput per slot with all employees
        max_throughput_per_slot = employee_count * base_productivity * slot_duration_hours

        # Determine input source
        upstream_id = upstream_of.get(process_id)
        has_conversion_rule = process_id in rule_map

        if upstream_id and upstream_id in throughput:
            # Input comes from upstream process's throughput
            input_map: Dict[str, float] = throughput[upstream_id]
            def get_input(slot: str) -> float:
                return input_map.get(slot, 0.0)
        elif has_conversion_rule:
            # Root process: input from raw volume plan
            source_type, conversion_rate = rule_map[process_id]
            def get_input(slot: str, _st=source_type, _cr=conversion_rate) -> float:
                return plan_map.get((_st, slot), 0.0) * _cr
        else:
            # No input source defined, skip
            continue

        carry_over = 0.0
        process_throughput: Dict[str, float] = {}

        for slot in all_slots:
            new_volume = get_input(slot)
            total_volume = new_volume + carry_over

            if total_volume <= 0:
                carry_over = 0.0
                process_throughput[slot] = 0.0
                continue

            if base_productivity > 0:
                required_person_slots = total_volume / (base_productivity * slot_duration_hours)
            else:
                required_person_slots = 0.0

            # How much can be processed with all employees (upper bound)
            processed = min(total_volume, max_throughput_per_slot)
            carry_over = max(0.0, total_volume - processed)
            process_throughput[slot] = processed

            exp = VolumeExpansion(
                expansion_id=str(uuid.uuid4()),
                plan_date=plan_date,
                process_id=process_id,
                time_slot_start=slot,
                process_volume=round(total_volume, 2),
                carry_over_volume=round(carry_over, 2),
                required_person_slots=round(required_person_slots, 3),
                calculated_at=now,
            )
            db.add(exp)
            expansions.append(exp)

            if carry_over <= 0 and new_volume <= 0:
                break

        throughput[process_id] = process_throughput

    db.commit()
    for e in expansions:
        db.refresh(e)

    return expansions
