"""
物量展開サービス（フローシミュレーション方式）

考え方:
  - 末端の入庫量/出庫量は「最上流工程」の作業を生成する起点。
  - 各工程は自分の変換係数を「入力源の量」に掛けて自工程の作業量を得る。
      入力源 = 最上流工程: 生の入庫/出庫量
              下流工程  : 1つ上流工程が "前スロットで処理した量"（15分のタイムラグ）
  - 例) 入庫100, 入庫→入荷=0.5 なら 入荷の作業発生=50。
        入荷が50処理し, 入荷→棚入=2.0 なら 棚入の作業発生=100。
  - 各スロットで処理しきれなかった作業は backlog として次スロットへ滞留し続ける。
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


def _topological_sort(process_ids: List[str], upstream_of: Dict[str, str]) -> List[str]:
    """Return process_ids in topological order (upstream first)."""
    visited = set()
    order: List[str] = []

    def visit(pid: str):
        if pid in visited:
            return
        visited.add(pid)
        up = upstream_of.get(pid)
        if up and up in process_ids:
            visit(up)
        order.append(pid)

    for pid in process_ids:
        visit(pid)
    return order


def expand_volume(plan_date: str, db: Session) -> List[VolumeExpansion]:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    plans = db.query(VolumePlan).filter(VolumePlan.plan_date == plan_date).all()
    if not plans:
        return []

    # 生の入出庫量: (volume_type, slot) -> volume
    plan_map: Dict[tuple, float] = {}
    for p in plans:
        plan_map[(p.volume_type, p.time_slot_start)] = float(p.volume)

    # 変換係数: process_id -> (source_type, rate)
    rules = db.query(VolumeConversionRule).all()
    rule_map: Dict[str, tuple] = {r.process_id: (r.source_type, float(r.conversion_rate)) for r in rules}

    # 工程接続: 下流 -> 上流
    connections = db.query(ProcessConnection).all()
    upstream_of: Dict[str, str] = {c.to_process_id: c.from_process_id for c in connections}

    active_processes = {
        p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()
    }
    if not active_processes:
        return []

    employee_count = max(1, db.query(Employee).filter(Employee.is_active == 1).count())

    plan_slots = sorted(set(p.time_slot_start for p in plans))
    first_min = _time_to_min(plan_slots[0])

    # 滞留分を処理しきるため 23:30 まで枠を生成
    all_slots: List[str] = []
    t = first_min
    while t <= 23 * 60 + 30:
        all_slots.append(_min_to_time(t))
        t += 15

    process_order = _topological_sort(list(active_processes.keys()), upstream_of)

    slot_duration_hours = 15.0 / 60.0

    # 工程ごとの定数を準備
    base_prod: Dict[str, float] = {}
    max_cap: Dict[str, float] = {}    # 全員投入時の1スロット最大処理量（上限の目安）
    is_root: Dict[str, bool] = {}
    own_rate: Dict[str, float] = {}
    root_source: Dict[str, str] = {}

    for pid in process_order:
        proc = active_processes[pid]
        bp = float(proc.base_productivity)
        base_prod[pid] = bp
        max_cap[pid] = employee_count * bp * slot_duration_hours
        up = upstream_of.get(pid)
        root = not (up and up in active_processes)
        is_root[pid] = root
        rate = rule_map[pid][1] if pid in rule_map else 1.0
        own_rate[pid] = rate
        if root and pid in rule_map:
            root_source[pid] = rule_map[pid][0]

    db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == plan_date).delete()

    expansions: List[VolumeExpansion] = []

    # シミュレーション状態
    backlog: Dict[str, float] = {pid: 0.0 for pid in process_order}
    throughput: Dict[str, Dict[str, float]] = {pid: {} for pid in process_order}

    for idx, slot in enumerate(all_slots):
        prev_slot = all_slots[idx - 1] if idx > 0 else None

        for pid in process_order:  # 上流から順に
            # --- このスロットで新規に発生する作業量 ---
            if is_root[pid]:
                src = root_source.get(pid)
                incoming = plan_map.get((src, slot), 0.0) * own_rate[pid] if src else 0.0
            else:
                up = upstream_of[pid]
                # 上流が「前スロットで処理した量」に自工程の係数を掛ける（15分ラグ）
                up_processed_prev = throughput[up].get(prev_slot, 0.0) if prev_slot else 0.0
                incoming = up_processed_prev * own_rate[pid]

            backlog[pid] += incoming
            work_present = backlog[pid]

            if work_present <= 1e-9:
                throughput[pid][slot] = 0.0
                continue

            # 全作業を当スロットで捌くのに必要な人員スロット数
            bp = base_prod[pid]
            required_person_slots = work_present / (bp * slot_duration_hours) if bp > 0 else 0.0

            # 全員投入した場合に処理できる上限（目安）。残りは滞留。
            processed = min(work_present, max_cap[pid])
            backlog[pid] = work_present - processed
            throughput[pid][slot] = processed

            exp = VolumeExpansion(
                expansion_id=str(uuid.uuid4()),
                plan_date=plan_date,
                process_id=pid,
                time_slot_start=slot,
                process_volume=round(work_present, 2),       # そのスロットに存在する作業量
                carry_over_volume=round(backlog[pid], 2),     # 処理後の滞留量
                required_person_slots=round(required_person_slots, 3),
                calculated_at=now,
            )
            db.add(exp)
            expansions.append(exp)

        # 全工程の backlog が枯れ、かつ以降の新規入力も無ければ終了
        if all(backlog[pid] <= 1e-9 for pid in process_order):
            future_input = any(
                plan_map.get((root_source.get(pid), fs), 0.0) > 0
                for pid in process_order if is_root[pid] and pid in root_source
                for fs in all_slots[idx + 1:]
            )
            if not future_input:
                break

    db.commit()
    for e in expansions:
        db.refresh(e)

    return expansions
