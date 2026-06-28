"""
処理フローレポート（唯一の真実 / single source of truth）

確定したシフト（保存済み割当）から、工程ごと・スロットごとの
  - 処理発生量（incoming）
  - 処理量（throughput）
  - 処理残（backlog）
を計算する。

重要:
  これまでフロントエンド(Shift.tsx)とバックエンド(optimizer)で別々に
  フローを再現していたため、熟練度や物量ソースの扱いがズレて「残」が
  食い違っていた。本モジュールがバックエンドで唯一の計算を担い、
  フロントは結果を表示するだけにすることで不整合を根絶する。

  最適化エンジンが人員を組むときの _run_flow と同じロジック・同じ物量
  （volume_expansions = 根元工程の作業量）・同じ熟練度補正を用いる。
"""
from collections import defaultdict
from typing import Dict, List

from sqlalchemy.orm import Session

from models import (
    Process, ProcessConnection, VolumeConversionRule, VolumeExpansion,
    EmployeeProcessSkill, SkillLevelProductivityRate,
    OptimizationResult, OptimizationAssignment, SystemCondition,
)

SLOT_HOURS = 15.0 / 60.0


def _parse_time(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def compute_flow_report(date: str, result_id: str, db: Session) -> Dict[str, List[dict]]:
    """
    指定の最適化結果(result_id)について、工程ごとのスロット別フローを返す。

    戻り値: { process_id: [ {slot, incoming, processed, backlog,
                            cum_arrived, cum_processed}, ... ] }
    """
    processes = {
        p.process_id: p
        for p in db.query(Process).filter(Process.is_active == 1).all()
    }
    if not processes:
        return {}

    # 工程接続: 下流 -> 上流 / 上流 -> [下流]
    connections = db.query(ProcessConnection).all()
    upstream_of = {c.to_process_id: c.from_process_id for c in connections}
    downstream_of: Dict[str, List[str]] = defaultdict(list)
    for c in connections:
        downstream_of[c.from_process_id].append(c.to_process_id)

    # トポロジカル順序（上流から）
    order: List[str] = []
    seen = set()

    def visit(pid: str):
        if pid in seen:
            return
        seen.add(pid)
        up = upstream_of.get(pid)
        if up and up in processes:
            visit(up)
        order.append(pid)

    for pid in processes:
        visit(pid)

    # 変換係数（下流伝播時に使用）
    conv_rate = {
        r.process_id: float(r.conversion_rate)
        for r in db.query(VolumeConversionRule).all()
    }

    # 根元工程の作業量（= 最適化が使う volume_expansions）
    root_volume: Dict[str, Dict[str, float]] = defaultdict(dict)
    for e in db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == date).all():
        root_volume[e.process_id][e.time_slot_start] = float(e.process_volume)

    # 熟練度係数
    skill_rates = {
        r.skill_level: float(r.productivity_rate)
        for r in db.query(SkillLevelProductivityRate).all()
    }
    skills: Dict[str, Dict[str, int]] = defaultdict(dict)
    for s in db.query(EmployeeProcessSkill).all():
        skills[s.employee_id][s.process_id] = s.skill_level

    base_prod = {pid: float(p.base_productivity) for pid, p in processes.items()}

    # 工程移動ペナルティ設定（optimizer/base.py と同じ条件を参照）
    conds = {c.condition_key: c.condition_value for c in db.query(SystemCondition).all()}
    penalty_enabled = conds.get("process_transition_penalty_enabled", "1") == "1"
    penalty_rate = float(conds.get("process_transition_penalty_rate", "0.30"))

    # 保存済み割当を「従業員 → 時刻順リスト」に整理し、工程移動直後スロットを検出
    # capacity[pid][slot] = Σ base_prod * skill_rate * transition_factor * SLOT_HOURS
    assigns_all = db.query(OptimizationAssignment).filter(
        OptimizationAssignment.result_id == result_id,
    ).order_by(OptimizationAssignment.employee_id, OptimizationAssignment.time_slot_start).all()

    # 従業員ごとの時系列割当 {emp_id: [(slot, process_id or None), ...]}
    emp_timeline: Dict[str, list] = defaultdict(list)
    for a in assigns_all:
        emp_timeline[a.employee_id].append((a.time_slot_start, a.process_id if a.slot_type == "WORK" else None))

    # 工程移動直後スロットを集合で保持 {(emp_id, slot): True}
    transition_slots: set = set()
    if penalty_enabled:
        for eid, tl in emp_timeline.items():
            tl.sort(key=lambda x: _parse_time(x[0]))
            for i in range(1, len(tl)):
                prev_pid = tl[i - 1][1]
                cur_pid = tl[i][1]
                cur_slot = tl[i][0]
                # 前スロットがWORK（prev_pid!=None）かつ別工程への移動
                if prev_pid is not None and cur_pid is not None and prev_pid != cur_pid:
                    transition_slots.add((eid, cur_slot))

    capacity: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for a in assigns_all:
        if not a.process_id or a.slot_type != "WORK":
            continue
        level = skills.get(a.employee_id, {}).get(a.process_id, 2)
        rate = skill_rates.get(level, 1.0)
        tf = (1.0 - penalty_rate) if (a.employee_id, a.time_slot_start) in transition_slots else 1.0
        capacity[a.process_id][a.time_slot_start] += (
            base_prod.get(a.process_id, 0.0) * rate * tf * SLOT_HOURS
        )

    # 全スロット = 物量到着スロット ∪ 割当スロット
    slot_set = set()
    for vmap in root_volume.values():
        slot_set.update(vmap.keys())
    for cmap in capacity.values():
        slot_set.update(cmap.keys())
    all_slots = sorted(slot_set, key=_parse_time)

    backlog = {pid: 0.0 for pid in order}
    incoming: Dict[str, Dict[str, float]] = {pid: {} for pid in order}
    for pid, vmap in root_volume.items():
        for slot, vol in vmap.items():
            incoming.setdefault(pid, {})[slot] = vol

    cum_arrived = {pid: 0.0 for pid in order}
    cum_processed = {pid: 0.0 for pid in order}
    result: Dict[str, List[dict]] = {pid: [] for pid in order}

    for idx, slot in enumerate(all_slots):
        next_slot = all_slots[idx + 1] if idx + 1 < len(all_slots) else None
        for pid in order:
            inc = incoming[pid].get(slot, 0.0)
            cum_arrived[pid] += inc
            backlog[pid] += inc

            cap = capacity.get(pid, {}).get(slot, 0.0)
            throughput = min(backlog[pid], cap)
            backlog[pid] -= throughput
            cum_processed[pid] += throughput

            # 下流へ15分ラグで伝播
            if throughput > 0 and next_slot:
                for down_pid in downstream_of.get(pid, []):
                    if down_pid not in incoming:
                        continue
                    rate = conv_rate.get(down_pid, 1.0)
                    incoming[down_pid][next_slot] = (
                        incoming[down_pid].get(next_slot, 0.0) + throughput * rate
                    )

            if cum_arrived[pid] > 1e-9 or cum_processed[pid] > 1e-9:
                # 稼働率 = 実処理数 ÷ 配置人員の最大処理能力。
                # 人を配置していない（cap=0）スロットは稼働率の対象外（None）。
                utilization = (throughput / cap) if cap > 1e-9 else None
                result[pid].append({
                    "slot": slot,
                    "incoming": round(inc, 1),
                    "processed": round(throughput, 1),
                    "backlog": round(backlog[pid], 1),
                    "cum_arrived": round(cum_arrived[pid], 1),
                    "cum_processed": round(cum_processed[pid], 1),
                    # 配置人員から求まる最大処理能力（個/スロット）
                    "capacity": round(cap, 1),
                    # 稼働率（0.0〜1.0）。cap=0 のスロットは None
                    "utilization": round(utilization, 4) if utilization is not None else None,
                })

    return result


def get_flow_report_for_date(date: str, db: Session) -> dict:
    """選択中（無ければ最新）の結果についてフローレポートを返す。"""
    result = db.query(OptimizationResult).filter(
        OptimizationResult.plan_date == date,
        OptimizationResult.is_selected == 1,
    ).first()
    if not result:
        result = db.query(OptimizationResult).filter(
            OptimizationResult.plan_date == date,
        ).order_by(OptimizationResult.calculated_at.desc()).first()
    if not result:
        return {"date": date, "result_id": None, "processes": {}}

    flow = compute_flow_report(date, result.result_id, db)
    return {
        "date": date,
        "result_id": result.result_id,
        "result_type": result.result_type,
        "processes": flow,
    }
