"""
物量展開サービス
volume_plans から各工程・スロットごとの必要人員数を計算して volume_expansions に保存する
積み残し（carry-over）を次スロットに繰り越す
"""
from datetime import datetime
import uuid
from typing import List

from sqlalchemy.orm import Session

from models import VolumePlan, VolumeConversionRule, VolumeExpansion, Process, Employee


def _time_to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _min_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def expand_volume(plan_date: str, db: Session) -> List[VolumeExpansion]:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    plans = db.query(VolumePlan).filter(VolumePlan.plan_date == plan_date).all()
    if not plans:
        return []

    plan_map: dict = {}
    for p in plans:
        plan_map[(p.volume_type, p.time_slot_start)] = float(p.volume)

    rules = db.query(VolumeConversionRule).all()
    if not rules:
        return []

    active_processes = {p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()}

    # Active employee count for throughput estimation (upper bound)
    employee_count = max(1, db.query(Employee).filter(Employee.is_active == 1).count())

    plan_slots = sorted(set(p.time_slot_start for p in plans))
    first_min = _time_to_min(plan_slots[0])

    # Generate slots from first plan slot up to 23:30 to accommodate carry-over
    all_slots = []
    t = first_min
    while t <= 23 * 60 + 30:
        all_slots.append(_min_to_time(t))
        t += 15

    db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == plan_date).delete()

    expansions = []
    slot_duration_hours = 15.0 / 60.0

    for rule in rules:
        process_id = rule.process_id
        if process_id not in active_processes:
            continue

        proc = active_processes[process_id]
        base_productivity = float(proc.base_productivity)
        source_type = rule.source_type
        conversion_rate = float(rule.conversion_rate)

        # Max items all employees can process per slot (optimistic upper bound)
        max_throughput_per_slot = employee_count * base_productivity * slot_duration_hours

        carry_over = 0.0

        for slot in all_slots:
            new_volume = plan_map.get((source_type, slot), 0.0) * conversion_rate
            total_volume = new_volume + carry_over

            if total_volume <= 0:
                carry_over = 0.0
                continue

            if base_productivity > 0:
                required_person_slots = total_volume / (base_productivity * slot_duration_hours)
            else:
                required_person_slots = 0.0

            # Carry-over = what can't be processed even with all employees
            carry_over = max(0.0, total_volume - max_throughput_per_slot)

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

            if carry_over <= 0:
                break

    db.commit()
    for e in expansions:
        db.refresh(e)

    return expansions
