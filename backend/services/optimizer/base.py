"""
最適化基底クラス
共通処理（スロット生成、配置可否判定、スコア計算）を提供する
"""
import math
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Set

from sqlalchemy.orm import Session

from models import (
    Employee, EmployeeProcessSkill, EmployeeWorkCondition,
    VolumeExpansion, ProcessDeadlineCondition,
    SystemCondition, SkillLevelProductivityRate,
    OptimizationResult, OptimizationAssignment,
    ProcessConnection, Process, VolumeConversionRule,
)


def _parse_time(t: str) -> int:
    """Parse HH:MM to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _format_time(minutes: int) -> str:
    """Format minutes since midnight to HH:MM."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def _generate_slots(start_time: str, end_time: str, slot_minutes: int = 15) -> List[str]:
    """Generate list of HH:MM slot starts from start_time to end_time (exclusive)."""
    start = _parse_time(start_time)
    end = _parse_time(end_time)
    slots = []
    t = start
    while t < end:
        slots.append(_format_time(t))
        t += slot_minutes
    return slots


class Assignment:
    """Represents a single slot assignment for an employee."""
    __slots__ = ("employee_id", "process_id", "time_slot_start", "slot_type", "is_overtime", "slot_cost")

    def __init__(self, employee_id, process_id, time_slot_start, slot_type, is_overtime, slot_cost):
        self.employee_id = employee_id
        self.process_id = process_id
        self.time_slot_start = time_slot_start
        self.slot_type = slot_type  # WORK / LUNCH_BREAK / LEGAL_BREAK / OFF
        self.is_overtime = is_overtime
        self.slot_cost = slot_cost


class BaseOptimizer:
    RESULT_TYPE: str = ""

    def __init__(self, plan_date: str, db: Session, method: str = "GREEDY"):
        self.plan_date = plan_date
        self.db = db
        self.method = method  # GREEDY / ANNEALING / ORTOOLS
        self.slot_minutes = 15
        # Number of candidate placements examined by the heuristic
        self.patterns_evaluated = 0
        # MIPソルバーの実行記録（solve_mip が設定）。画面の計算ログに使う。
        # {"status": str, "gap": float|None, "seconds": float}
        self.last_solve_meta = None

        # Load system conditions
        conds = {c.condition_key: c.condition_value for c in db.query(SystemCondition).all()}
        self.overtime_wage_rate = float(conds.get("overtime_wage_rate", "1.20"))
        self.overtime_threshold_minutes = int(conds.get("overtime_threshold_minutes", "480"))
        self.lunch_break_start = conds.get("lunch_break_start", "11:30")
        self.lunch_break_end = conds.get("lunch_break_end", "13:00")
        self.lunch_break_duration = int(conds.get("lunch_break_duration_minutes", "60"))
        self.legal_break_threshold = int(conds.get("legal_break_threshold_minutes", "360"))
        self.legal_break_minutes = int(conds.get("legal_break_minutes", "45"))
        # 残業可能者の最大勤務終了時刻。overtime_available=True の場合、
        # 通常の work_end_time を超えてこの時刻まで配置可能とする。
        self.overtime_max_end_time = conds.get("overtime_max_end_time", "20:00")
        # 工程移動直後スロットの生産性ペナルティ（休憩なしで別工程へ移ったとき）
        self.transition_penalty_enabled = conds.get("process_transition_penalty_enabled", "1") == "1"
        self.transition_penalty_rate = float(conds.get("process_transition_penalty_rate", "0.30"))
        # 最低勤務時間（分）：これ未満しか働けない人は配置しない（0=無効）
        self.min_work_minutes = int(conds.get("min_work_minutes", "0"))
        # 1工程の最低連続配置時間（分）：頻繁な工程移動を抑制（0=無効）。
        # ただしその工程の当日作業が完了するタイミングでは適用しない。
        self.min_process_assignment_minutes = int(conds.get("min_process_assignment_minutes", "0"))

        # Load skill productivity rates
        self.skill_rates = {
            r.skill_level: float(r.productivity_rate)
            for r in db.query(SkillLevelProductivityRate).all()
        }

        # Determine day of week
        d = date.fromisoformat(plan_date)
        self.day_of_week = d.weekday()  # 0=Monday, 6=Sunday

        # Load employees
        self.employees = db.query(Employee).filter(Employee.is_active == 1).all()

        # Load skills: employee_id -> {process_id: skill_level}
        self.skills: Dict[str, Dict[str, int]] = {}
        for s in db.query(EmployeeProcessSkill).all():
            self.skills.setdefault(s.employee_id, {})[s.process_id] = s.skill_level

        # Load work conditions for this day
        self.work_conditions: Dict[str, EmployeeWorkCondition] = {}
        for c in db.query(EmployeeWorkCondition).filter(
            EmployeeWorkCondition.day_of_week == self.day_of_week
        ).all():
            self.work_conditions[c.employee_id] = c

        # Build available employees (those with work condition for this day)
        self.active_employees = [
            e for e in self.employees
            if e.employee_id in self.work_conditions
        ]

        # Build employee available slots (before breaks).
        # overtime_available=True の場合、通常の work_end_time を超えて
        # overtime_max_end_time まで配置可能スロットを延長する。
        # これにより残務がある限り残業可能者を配置できる。
        self.employee_available_slots: Dict[str, List[str]] = {}
        self.employee_slot_index: Dict[str, Dict[str, int]] = {}  # O(1)スロット→インデックス逆引き
        for emp in self.active_employees:
            cond = self.work_conditions[emp.employee_id]
            end_time = cond.work_end_time
            if cond.overtime_available:
                # overtime_max_end_time が定時より後であれば延長
                if _parse_time(self.overtime_max_end_time) > _parse_time(end_time):
                    end_time = self.overtime_max_end_time
            slots = _generate_slots(cond.work_start_time, end_time, self.slot_minutes)
            self.employee_available_slots[emp.employee_id] = slots
            self.employee_slot_index[emp.employee_id] = {s: i for i, s in enumerate(slots)}

        # Load active processes and their base productivity
        self.process_map: Dict[str, Process] = {
            p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()
        }
        self.base_prod: Dict[str, float] = {
            pid: float(p.base_productivity) for pid, p in self.process_map.items()
        }
        self.slot_hours = self.slot_minutes / 60.0

        # Load conversion rates: process_id -> rate (used to convert upstream
        # throughput into this process's work volume)
        self.conv_rate: Dict[str, float] = {
            r.process_id: float(r.conversion_rate)
            for r in db.query(VolumeConversionRule).all()
        }

        # Load volume expansions (root processes only): work volume per slot
        # {process_id: {time_slot: process_volume}}
        expansions = db.query(VolumeExpansion).filter(
            VolumeExpansion.plan_date == plan_date
        ).all()
        self.root_volume: Dict[str, Dict[str, float]] = {}
        for e in expansions:
            self.root_volume.setdefault(e.process_id, {})[e.time_slot_start] = float(e.process_volume)

        # Process chain: upstream -> [downstream], and topological order
        connections = db.query(ProcessConnection).all()
        upstream_of: Dict[str, str] = {c.to_process_id: c.from_process_id for c in connections}
        self.downstream_of: Dict[str, List[str]] = {}
        for c in connections:
            self.downstream_of.setdefault(c.from_process_id, []).append(c.to_process_id)

        all_pids = list(self.process_map.keys())
        visited: set = set()
        topo_order: List[str] = []

        def _visit(pid: str):
            if pid in visited:
                return
            visited.add(pid)
            up = upstream_of.get(pid)
            if up and up in self.process_map:
                _visit(up)
            topo_order.append(pid)

        for pid in all_pids:
            _visit(pid)
        self.process_order: List[str] = topo_order

        # Load deadlines
        self.deadlines: Dict[str, str] = {}
        for d in db.query(ProcessDeadlineCondition).filter(
            ProcessDeadlineCondition.is_active == 1
        ).all():
            self.deadlines[d.process_id] = d.must_finish_by

        # Lunch break slots
        self.lunch_slots = _generate_slots(
            self.lunch_break_start, self.lunch_break_end, self.slot_minutes
        )
        # We need to assign 60min / 15min = 4 slots per employee
        self.lunch_slots_count = self.lunch_break_duration // self.slot_minutes

    def _assign_lunch_breaks(
        self,
        assignments: Dict[str, Dict[str, Assignment]],
    ):
        """
        Assign lunch break slots to employees.
        Stagger start times across employees in groups.
        """
        employees = self.active_employees
        n = len(employees)
        if n == 0:
            return

        # Group employees into 3 groups with lunch at 11:30, 11:45, 12:00
        group_starts = [
            _parse_time(self.lunch_break_start),
            _parse_time(self.lunch_break_start) + 15,
            _parse_time(self.lunch_break_start) + 30,
        ]

        for i, emp in enumerate(employees):
            emp_id = emp.employee_id
            group_start_min = group_starts[i % 3]
            emp_assignments = assignments.setdefault(emp_id, {})

            for j in range(self.lunch_slots_count):
                slot_min = group_start_min + j * self.slot_minutes
                slot_str = _format_time(slot_min)
                if slot_str in self.employee_available_slots.get(emp_id, []):
                    emp_assignments[slot_str] = Assignment(
                        employee_id=emp_id,
                        process_id=None,
                        time_slot_start=slot_str,
                        slot_type="LUNCH_BREAK",
                        is_overtime=False,
                        slot_cost=0.0,
                    )

    def can_assign(
        self,
        employee: Employee,
        process_id: str,
        time_slot: str,
        emp_assignments: Dict[str, Assignment],
        backlog: Optional[Dict[str, float]] = None,
    ) -> bool:
        emp_id = employee.employee_id
        # Check if slot is in available slots
        if time_slot not in self.employee_available_slots.get(emp_id, []):
            return False
        # Check not already assigned
        if time_slot in emp_assignments:
            return False
        # Check skill
        if process_id not in self.skills.get(emp_id, {}):
            return False
        # Check overtime availability
        if self._is_overtime_slot(employee, time_slot, emp_assignments):
            cond = self.work_conditions.get(emp_id)
            if cond and not cond.overtime_available:
                return False
        # 注：1工程の最低連続配置時間は can_assign では強制しない。
        # ハードに禁止すると（GREEDYでは残務が処理できず、MIPでは解けなくなる）
        # 弊害が大きいため、配置決定後に _repair_continuity で
        # 「同一スロット内の工程ラベル入れ替え」によって細切れ切替を後処理で
        # 解消する方式に変更した（処理量・コストを変えずに連続化する）。
        return True

    def _is_overtime_slot(
        self,
        employee: Employee,
        time_slot: str,
        emp_assignments: Dict[str, Assignment],
    ) -> bool:
        """Check if this slot would be overtime."""
        work_count = sum(
            1 for a in emp_assignments.values()
            if a.slot_type == "WORK" and a.time_slot_start < time_slot
        )
        worked_minutes = work_count * self.slot_minutes
        return worked_minutes >= self.overtime_threshold_minutes

    def _calc_slot_cost(
        self,
        employee: Employee,
        time_slot: str,
        emp_assignments: Dict[str, Assignment],
    ) -> float:
        """Calculate cost for one slot."""
        hourly = float(employee.hourly_wage)
        slot_hours = self.slot_minutes / 60.0
        base_cost = hourly * slot_hours
        if self._is_overtime_slot(employee, time_slot, emp_assignments):
            return base_cost * self.overtime_wage_rate
        return base_cost

    def calc_score(
        self,
        assignments: Dict[str, Dict[str, Assignment]],
    ) -> dict:
        """Calculate scores for current assignment."""
        total_cost = 0.0
        total_overtime_cost = 0.0
        total_moves = 0
        deadline_violations: Dict[str, float] = {}

        for emp_id, emp_assignments in assignments.items():
            emp = next((e for e in self.active_employees if e.employee_id == emp_id), None)
            if not emp:
                continue

            hourly = float(emp.hourly_wage)
            slot_hours = self.slot_minutes / 60.0

            sorted_slots = sorted(emp_assignments.values(), key=lambda a: a.time_slot_start)
            work_count = 0
            prev_process = None

            for a in sorted_slots:
                if a.slot_type == "WORK":
                    is_ot = (work_count * self.slot_minutes) >= self.overtime_threshold_minutes
                    base = hourly * slot_hours
                    cost = base * self.overtime_wage_rate if is_ot else base
                    total_cost += cost
                    if is_ot:
                        total_overtime_cost += base * (self.overtime_wage_rate - 1.0)
                    work_count += 1

                    if prev_process is not None and a.process_id != prev_process:
                        total_moves += 1
                    prev_process = a.process_id
                else:
                    prev_process = None

        # Check deadline violations
        for process_id, deadline_str in self.deadlines.items():
            deadline_min = _parse_time(deadline_str)
            # Find last work slot for this process
            last_slot_min = 0
            for emp_assignments in assignments.values():
                for a in emp_assignments.values():
                    if a.process_id == process_id and a.slot_type == "WORK":
                        slot_min = _parse_time(a.time_slot_start) + self.slot_minutes
                        if slot_min > last_slot_min:
                            last_slot_min = slot_min
            if last_slot_min > deadline_min:
                deadline_violations[process_id] = (last_slot_min - deadline_min) / 60.0

        return {
            "total_cost": total_cost,
            "total_overtime_cost": total_overtime_cost,
            "total_moves": total_moves,
            "deadline_violations": deadline_violations,
            "is_deadline_met": len(deadline_violations) == 0,
        }

    def _strip_orphan_lunch_breaks(self, assignments: Dict[str, Dict[str, Assignment]]):
        """実際の作業に挟まれていない昼休憩を除去する。

        昼休憩は「午前働いて昼に休み午後も働く」人にのみ意味がある。
        次の3パターンの人には「昼」を残さない：
          - 出社しない人（作業スロットが1つも無い）
          - 昼休憩前に帰る人（昼より後に作業が無い）
          - 昼休憩後に来る人（昼より前に作業が無い）
        判定：その昼休憩スロットの前後どちらにもWORKがある場合のみ残す。
        """
        for emp_id, ea in assignments.items():
            work_times = [
                _parse_time(a.time_slot_start)
                for a in ea.values() if a.slot_type == "WORK"
            ]
            for slot, a in list(ea.items()):
                if a.slot_type != "LUNCH_BREAK":
                    continue
                t = _parse_time(slot)
                has_before = any(wt < t for wt in work_times)
                has_after = any(wt > t for wt in work_times)
                if not (has_before and has_after):
                    del ea[slot]

    def _repair_continuity(self, assignments: Dict[str, Dict[str, Assignment]]):
        """配置決定後の連続化リペア（15分単位の無意味な工程切替を減らす）。

        【考え方】最適化結果は「各工程・各スロットの人数（＝人員計画）」と
        「その枠を具体的に誰が埋めるか（＝席割当）」に分解できる。人員計画を
        固定したまま席割当だけを組み替えても、各工程の処理量・完了時刻・
        各人の総勤務時間（＝コスト）は一切変わらない。そこで本処理は
        「同一スロット内で、就労中の従業員同士の工程ラベルを入れ替える」
        ことだけで、なるべく同じ人が同じ工程に連続して就くようにする。

        評価指標は「連続する2スロット間で工程が変わる回数（＝切替数）」。
        休憩・勤務外で途切れた箇所はリセット（昼休み後の工程変更は自由）。
        スワップはスキル制約（双方が相手の工程スキルを持つ）を満たす場合のみ。
        コスト・処理量に影響しない安全な変換で、切替だけを局所探索で削減する。
        """
        min_run = self.min_process_assignment_minutes // self.slot_minutes
        if min_run <= 1:
            return

        # 各スロットで就労中の (employee_id, Assignment) を集める
        slot_workers: Dict[str, List[str]] = {}
        for eid, ea in assignments.items():
            for slot, a in ea.items():
                if a.slot_type == "WORK":
                    slot_workers.setdefault(slot, []).append(eid)
        all_slots = sorted(slot_workers.keys())

        def proc_at_offset(eid: str, slot: str, offset: int):
            """eid の available スロット並びで slot の offset 隣のWORK工程を返す。
            隣が休憩・勤務外・非WORKなら None（＝そこで連続が途切れている）。"""
            idx_map = self.employee_slot_index.get(eid, {})
            idx = idx_map.get(slot)
            if idx is None:
                return None
            slots = self.employee_available_slots.get(eid, [])
            nidx = idx + offset
            if nidx < 0 or nidx >= len(slots):
                return None
            a = assignments[eid].get(slots[nidx])
            if a is None or a.slot_type != "WORK":
                return None
            return a.process_id

        def local_switch_count(eid: str, slot: str, cur_pid: str) -> int:
            """eid が slot で cur_pid に就く場合の、前後との切替本数（0〜2）。"""
            cnt = 0
            prev_p = proc_at_offset(eid, slot, -1)
            if prev_p is not None and prev_p != cur_pid:
                cnt += 1
            next_p = proc_at_offset(eid, slot, +1)
            if next_p is not None and next_p != cur_pid:
                cnt += 1
            return cnt

        skills = self.skills
        # スワップ前の状態を退避（処理量が悪化したら丸ごと戻すため）。
        snapshot = {
            (eid, slot): a.process_id
            for eid, ea in assignments.items()
            for slot, a in ea.items() if a.slot_type == "WORK"
        }
        base_backlog = self._flow_backlog_fixed(assignments)

        # 局所探索：同一スロット内の2人で工程を入れ替えると切替が減る場合に実施
        for _pass in range(8):
            improved = False
            for slot in all_slots:
                workers = slot_workers[slot]
                n = len(workers)
                for i in range(n):
                    ai = workers[i]
                    pa = assignments[ai][slot].process_id
                    for j in range(i + 1, n):
                        bj = workers[j]
                        pb = assignments[bj][slot].process_id
                        if pa == pb:
                            continue
                        # スワップにはスキルが必要（互いに相手の工程をこなせる）
                        if pb not in skills.get(ai, {}) or pa not in skills.get(bj, {}):
                            continue
                        before = (local_switch_count(ai, slot, pa)
                                  + local_switch_count(bj, slot, pb))
                        after = (local_switch_count(ai, slot, pb)
                                 + local_switch_count(bj, slot, pa))
                        if after < before:
                            # 工程ラベルだけ入れ替え（人数は不変）。
                            assignments[ai][slot].process_id = pb
                            assignments[bj][slot].process_id = pa
                            pa = pb  # ai の現工程を更新
                            improved = True
            if not improved:
                break

        # 安全網：スキルレベル差により工程別の実効処理能力が変わり、未処理量が
        # 増えてしまった場合はリペアを丸ごと取り消す（処理量・完了時刻を守る）。
        if self._flow_backlog_fixed(assignments) > base_backlog + 1e-6:
            for (eid, slot), pid in snapshot.items():
                a = assignments.get(eid, {}).get(slot)
                if a is not None:
                    a.process_id = pid

    def _flow_backlog_fixed(self, assignments: Dict[str, Dict[str, Assignment]]) -> float:
        """与えられた配置（誰がどの工程か固定）での総未処理量を返す。

        _run_flow と違い再配置はせず、配置から各工程・各スロットの実効処理能力
        （スキル率・工程移動ペナルティ込み）を積み上げてフローを前進させる。
        連続化リペアが処理量を悪化させていないかの検証に使う。
        """
        slot_set: Set[str] = set()
        for ea in assignments.values():
            slot_set.update(ea.keys())
        for vmap in self.root_volume.values():
            slot_set.update(vmap.keys())
        all_slots = sorted(slot_set)
        prev_slot = {s: all_slots[i - 1] if i > 0 else None
                     for i, s in enumerate(all_slots)}

        cap: Dict = {}
        for eid, ea in assignments.items():
            for slot, a in ea.items():
                if a.slot_type != "WORK":
                    continue
                pid = a.process_id
                skill = self.skills.get(eid, {}).get(pid, 1)
                rate = self.skill_rates.get(skill, 1.0)
                tf = self._transition_factor(eid, pid, slot, ea, prev_slot)
                cap[(pid, slot)] = cap.get((pid, slot), 0.0) + \
                    self.base_prod.get(pid, 0.0) * rate * tf * self.slot_hours

        backlog: Dict[str, float] = {pid: 0.0 for pid in self.process_order}
        incoming: Dict[str, Dict[str, float]] = {pid: {} for pid in self.process_order}
        for pid, vmap in self.root_volume.items():
            for slot, vol in vmap.items():
                incoming.setdefault(pid, {})[slot] = incoming.get(pid, {}).get(slot, 0.0) + vol

        for idx, slot in enumerate(all_slots):
            next_slot = all_slots[idx + 1] if idx + 1 < len(all_slots) else None
            for pid in self.process_order:
                backlog[pid] += incoming[pid].get(slot, 0.0)
            for pid in self.process_order:
                thr = min(backlog[pid], cap.get((pid, slot), 0.0))
                backlog[pid] -= thr
                if thr > 0 and next_slot:
                    for dn in self.downstream_of.get(pid, []):
                        if dn in incoming:
                            r = self.conv_rate.get(dn, 1.0)
                            incoming[dn][next_slot] = incoming[dn].get(next_slot, 0.0) + thr * r
        return sum(backlog.values())

    def _save_result(self, assignments: Dict[str, Dict[str, Assignment]], score: dict):
        """Persist optimization result to DB."""
        # 注: 最低勤務時間・最低配置時間（ハード制約）はMIP定式化内で扱う。
        # GREEDYヒューリスティックは「滞留がある時だけ人を割り当てる」フロー
        # モデルのため、待機を含む最低勤務（在席させて支払う）の概念と相容れず、
        # ここでは強制しない。これらの制約は ORTOOLS/ANNEALING エンジンで反映される。

        # 出社しない・午前で帰る・午後から来る人の「昼」表示を消す
        self._strip_orphan_lunch_breaks(assignments)

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        result_id = str(uuid.uuid4())

        # Delete previous results of the same type AND same engine for this
        # date, and their assignments. エンジン(method)別に残すことで、
        # 貪欲/焼きなまし/OR-Tools の結果を画面で比較できるようにする。
        old_ids = [
            r.result_id for r in self.db.query(OptimizationResult).filter(
                OptimizationResult.plan_date == self.plan_date,
                OptimizationResult.result_type == self.RESULT_TYPE,
                OptimizationResult.calculation_method == self.method,
            ).all()
        ]
        if old_ids:
            self.db.query(OptimizationAssignment).filter(
                OptimizationAssignment.result_id.in_(old_ids)
            ).delete(synchronize_session=False)
        self.db.query(OptimizationResult).filter(
            OptimizationResult.plan_date == self.plan_date,
            OptimizationResult.result_type == self.RESULT_TYPE,
            OptimizationResult.calculation_method == self.method,
        ).delete()

        # 計算ログ用のソルバー実行記録を決定する。
        #  - GREEDY: MIP不使用。ヒューリスティックのみ。
        #  - ANNEALING/ORTOOLS: MIPを使用。last_solve_meta に状態・ギャップ・時間。
        #    MIPが解けずフォールバックした場合も meta に状態が入る（gap=None）。
        meta = self.last_solve_meta
        if self.method == "GREEDY":
            solver_status = "HEURISTIC"
            solver_gap = None
            solve_seconds = None
        elif meta is not None:
            solver_status = meta.get("status")
            solver_gap = meta.get("gap")
            solve_seconds = meta.get("seconds")
        else:
            # MIP未導入などで一度も解けなかった
            solver_status = "HEURISTIC"
            solver_gap = None
            solve_seconds = None

        result = OptimizationResult(
            result_id=result_id,
            plan_date=self.plan_date,
            result_type=self.RESULT_TYPE,
            total_cost=round(score["total_cost"], 2),
            total_overtime_cost=round(score["total_overtime_cost"], 2),
            total_process_moves=score["total_moves"],
            is_deadline_met=1 if score["is_deadline_met"] else 0,
            deadline_violations=json.dumps(score["deadline_violations"]) if score["deadline_violations"] else None,
            calculated_at=now,
            is_selected=0,
            patterns_evaluated=self.patterns_evaluated,
            calculation_method=self.method,
            solver_status=solver_status,
            solver_gap=round(solver_gap, 4) if solver_gap is not None else None,
            solve_seconds=round(solve_seconds, 2) if solve_seconds is not None else None,
        )
        self.db.add(result)

        for emp_id, emp_assignments in assignments.items():
            for a in emp_assignments.values():
                assign = OptimizationAssignment(
                    assignment_id=str(uuid.uuid4()),
                    result_id=result_id,
                    employee_id=emp_id,
                    process_id=a.process_id,
                    time_slot_start=a.time_slot_start,
                    slot_type=a.slot_type,
                    is_overtime=1 if a.is_overtime else 0,
                    slot_cost=round(a.slot_cost, 4),
                )
                self.db.add(assign)

        self.db.commit()
        return result_id

    def _demand_to_quotas(self, demand: Dict[str, float]) -> Dict[str, int]:
        """
        Bottleneck-balanced worker quota per process for one slot.

        `demand[pid]` = number of person-slots needed to fully clear the backlog
        of process `pid` in this slot. Every process with work gets at least 1
        worker; the remaining workforce is split proportionally to demand. This
        prevents an upstream process from monopolising all workers while a
        downstream process also has work waiting.
        """
        active = [pid for pid, d in demand.items() if d > 0]
        if not active:
            return {}

        n_workers = len(self.active_employees)
        guaranteed = min(len(active), n_workers)
        remainder = max(0, n_workers - guaranteed)
        total = sum(demand[pid] for pid in active)

        quotas: Dict[str, int] = {}
        for pid in active:
            prop = round(remainder * demand[pid] / total) if total > 0 else 0
            quotas[pid] = min(1 + prop, math.ceil(demand[pid]))
        return quotas

    def _emp_sort_key(self, emp, process_id: str, slot: str,
                      assignments: Dict[str, Dict[str, Assignment]]):
        """Employee priority for assignment. Overridden per strategy."""
        return (float(emp.hourly_wage),)

    def _transition_factor(self, emp_id: str, to_pid: str, slot: str,
                           emp_assignments: Dict[str, Assignment],
                           prev_slot_map: Dict[str, str]) -> float:
        """工程移動直後の生産性係数。

        直前スロットが休憩でなく、かつ別工程だった場合に (1 - penalty_rate) を返す。
        ペナルティが無効のとき・前スロットが存在しないとき・同じ工程継続のときは 1.0。
        """
        if not self.transition_penalty_enabled:
            return 1.0
        ps = prev_slot_map.get(slot)
        if ps is None:
            return 1.0
        prev_a = emp_assignments.get(ps)
        if prev_a is None or prev_a.slot_type != "WORK":
            return 1.0
        if prev_a.process_id == to_pid:
            return 1.0
        return 1.0 - self.transition_penalty_rate

    def _run_flow(self, assignments: Dict[str, Dict[str, Assignment]]):
        """
        Forward flow simulation tied to assignment.

        Time advances slot by slot. Within each slot, processes are handled
        upstream-first. A process can only work on volume that has actually
        arrived (root volume at its registered slot, or upstream throughput from
        the previous slot via the 15-min lag). Workers are assigned according to
        the strategy's sort key, the actual throughput is computed from the
        assigned headcount, and the leftover backlog carries to the next slot.
        Downstream work is generated only from real upstream throughput.
        """
        # Candidate working slots: union of every employee's available slots
        # plus the slots where root volume arrives.
        slot_set: Set[str] = set()
        for slots in self.employee_available_slots.values():
            slot_set.update(slots)
        for vmap in self.root_volume.values():
            slot_set.update(vmap.keys())
        all_slots = sorted(slot_set)

        backlog: Dict[str, float] = {pid: 0.0 for pid in self.process_order}
        # incoming[pid][slot] = work volume arriving at that slot
        incoming: Dict[str, Dict[str, float]] = {pid: {} for pid in self.process_order}
        for pid, vmap in self.root_volume.items():
            for slot, vol in vmap.items():
                incoming.setdefault(pid, {})[slot] = incoming.get(pid, {}).get(slot, 0.0) + vol

        prev_slot = {s: all_slots[i - 1] if i > 0 else None
                     for i, s in enumerate(all_slots)}

        for idx, slot in enumerate(all_slots):
            next_slot = all_slots[idx + 1] if idx + 1 < len(all_slots) else None

            # 1. Add newly arrived work to each process's backlog
            for pid in self.process_order:
                backlog[pid] += incoming[pid].get(slot, 0.0)

            # 2. Demand (person-slots) to clear each backlog this slot
            demand: Dict[str, float] = {}
            for pid in self.process_order:
                bp = self.base_prod.get(pid, 0.0)
                cap_per_person = bp * self.slot_hours
                if backlog[pid] > 1e-9 and cap_per_person > 0:
                    demand[pid] = backlog[pid] / cap_per_person
            quotas = self._demand_to_quotas(demand)

            # 3a. 第1パス：quotaで上流/下流の人員バランスを取りながら配置
            slot_throughput: Dict[str, float] = {}
            for pid in self.process_order:
                need = quotas.get(pid, 0)
                if need <= 0:
                    slot_throughput[pid] = 0.0
                    continue
                sorted_emps = sorted(
                    self.active_employees,
                    key=lambda e: self._emp_sort_key(e, pid, slot, assignments),
                )
                assigned = 0
                _assigned_capacity = 0.0
                for emp in sorted_emps:
                    if assigned >= need:
                        break
                    emp_assignments = assignments[emp.employee_id]
                    self.patterns_evaluated += 1
                    if self.can_assign(emp, pid, slot, emp_assignments, backlog=backlog):
                        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
                        cost = self._calc_slot_cost(emp, slot, emp_assignments)
                        emp_assignments[slot] = Assignment(
                            employee_id=emp.employee_id,
                            process_id=pid,
                            time_slot_start=slot,
                            slot_type="WORK",
                            is_overtime=is_ot,
                            slot_cost=cost,
                        )
                        assigned += 1
                        skill = self.skills.get(emp.employee_id, {}).get(pid, 1)
                        rate = self.skill_rates.get(skill, 1.0)
                        tf = self._transition_factor(emp.employee_id, pid, slot,
                                                     emp_assignments, prev_slot)
                        _assigned_capacity += self.base_prod.get(pid, 0.0) * rate * tf * self.slot_hours
                slot_throughput[pid] = min(backlog[pid], _assigned_capacity)

            # 3b. 第2パス（モップアップ）：残務があるのに空き人員がいれば追加配置。
            #    「熟練度が低い人員が配置されて実処理量がquota見積りを下回った」
            #    場合でも処理残が出ないよう、空き人員を使い切る。
            for pid in self.process_order:
                remaining_backlog_before = backlog[pid] - slot_throughput[pid]
                if remaining_backlog_before <= 1e-9:
                    continue
                sorted_emps = sorted(
                    self.active_employees,
                    key=lambda e: self._emp_sort_key(e, pid, slot, assignments),
                )
                extra_capacity = 0.0
                for emp in sorted_emps:
                    emp_assignments = assignments[emp.employee_id]
                    self.patterns_evaluated += 1
                    if self.can_assign(emp, pid, slot, emp_assignments, backlog=backlog):
                        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
                        cost = self._calc_slot_cost(emp, slot, emp_assignments)
                        emp_assignments[slot] = Assignment(
                            employee_id=emp.employee_id,
                            process_id=pid,
                            time_slot_start=slot,
                            slot_type="WORK",
                            is_overtime=is_ot,
                            slot_cost=cost,
                        )
                        skill = self.skills.get(emp.employee_id, {}).get(pid, 1)
                        rate = self.skill_rates.get(skill, 1.0)
                        tf = self._transition_factor(emp.employee_id, pid, slot,
                                                     emp_assignments, prev_slot)
                        extra_capacity += self.base_prod.get(pid, 0.0) * rate * tf * self.slot_hours
                        # 残務をカバーできた時点で追加配置を打ち切る
                        if extra_capacity >= remaining_backlog_before:
                            break
                slot_throughput[pid] = min(backlog[pid], slot_throughput[pid] + extra_capacity)

            # 4. backlогを確定し、下流へ伝播
            for pid in self.process_order:
                throughput = slot_throughput[pid]
                backlog[pid] -= throughput

                if throughput > 0 and next_slot:
                    for down_pid in self.downstream_of.get(pid, []):
                        if down_pid not in incoming:
                            continue
                        rate = self.conv_rate.get(down_pid, 1.0)
                        incoming[down_pid][next_slot] = (
                            incoming[down_pid].get(next_slot, 0.0) + throughput * rate
                        )

        return sum(backlog.values())

    # ------------------------------------------------------------------
    # Objective and refinement engines (shared by all result types)
    # ------------------------------------------------------------------
    def _objective(self, assignments: Dict[str, Dict[str, Assignment]]) -> float:
        """Scalar score to minimise. Lower is better. Overridden per strategy."""
        return self.calc_score(assignments)["total_cost"]

    def _eligible_employees(self, process_id: str, slot: str,
                            assignments: Dict[str, Dict[str, Assignment]]):
        """Employees who could legally take (process_id, slot) right now."""
        out = []
        for emp in self.active_employees:
            # refinement 段階ではバックログが追跡できないため {} を渡し、
            # 最低配置チェックの例外（バックログ0=完了扱い）を常に有効にする
            if self.can_assign(emp, process_id, slot, assignments[emp.employee_id], backlog={}):
                out.append(emp)
        return out

    def _refine(self, assignments: Dict[str, Dict[str, Assignment]]):
        """Apply the selected refinement engine to a flow-feasible solution."""
        if self.method == "ANNEALING":
            self._refine_annealing(assignments)
        elif self.method == "ORTOOLS":
            self._refine_ortools(assignments)
        # GREEDY: strategy-specific local search runs in the subclass

    def _refine_annealing(self, assignments: Dict[str, Dict[str, Assignment]],
                          iterations: int = 6000):
        """
        Simulated annealing over employee selection.

        The staffing plan (how many people work each process/slot) is kept
        fixed so the process-chain flow stays valid. A move re-assigns one
        existing seat to a different eligible employee. Worse moves are
        accepted with probability exp(-delta/T) to escape local optima.
        """
        import math as _math
        import random

        rng = random.Random(42)

        # Seats currently filled (employee can change, process/slot stays)
        seats = [
            (emp_id, slot, a.process_id)
            for emp_id, ea in assignments.items()
            for slot, a in ea.items()
            if a.slot_type == "WORK"
        ]
        if not seats:
            return

        cur_obj = self._objective(assignments)
        T = max(1.0, cur_obj * 0.05)
        cooling = 0.9995

        for _ in range(iterations):
            seat_idx = rng.randrange(len(seats))
            cur_emp_id, slot, process_id = seats[seat_idx]

            # Vacate the seat temporarily
            removed = assignments[cur_emp_id].pop(slot)

            candidates = self._eligible_employees(process_id, slot, assignments)
            candidates = [e for e in candidates if e.employee_id != cur_emp_id]
            self.patterns_evaluated += 1

            if not candidates:
                assignments[cur_emp_id][slot] = removed  # restore
                T *= cooling
                continue

            new_emp = rng.choice(candidates)
            is_ot = self._is_overtime_slot(new_emp, slot, assignments[new_emp.employee_id])
            cost = self._calc_slot_cost(new_emp, slot, assignments[new_emp.employee_id])
            assignments[new_emp.employee_id][slot] = Assignment(
                employee_id=new_emp.employee_id,
                process_id=process_id,
                time_slot_start=slot,
                slot_type="WORK",
                is_overtime=is_ot,
                slot_cost=cost,
            )

            new_obj = self._objective(assignments)
            delta = new_obj - cur_obj
            if delta <= 0 or rng.random() < _math.exp(-delta / T):
                # Accept
                cur_obj = new_obj
                seats[seat_idx] = (new_emp.employee_id, slot, process_id)
            else:
                # Revert
                del assignments[new_emp.employee_id][slot]
                assignments[cur_emp_id][slot] = removed

            T *= cooling

    def _refine_ortools(self, assignments: Dict[str, Dict[str, Assignment]],
                        time_limit_sec: float = 10.0):
        """
        Exact-ish employee selection via OR-Tools CP-SAT.

        Keeps the staffing plan (seats per process/slot) fixed and chooses the
        cheapest legal employee for each seat, modelling overtime as a convex
        per-employee cost. Falls back to the existing solution if OR-Tools is
        not installed or no feasible model is found.
        """
        try:
            from ortools.sat.python import cp_model
        except ImportError:
            return  # OR-Tools not available; keep current solution

        # Collect seats and reserved (lunch/legal break) slots per employee
        seats = []  # (slot, process_id)
        reserved: Dict[str, set] = {e.employee_id: set() for e in self.active_employees}
        for emp_id, ea in assignments.items():
            for slot, a in ea.items():
                if a.slot_type == "WORK":
                    seats.append((slot, a.process_id))
                else:
                    reserved.setdefault(emp_id, set()).add(slot)
        if not seats:
            return

        model = cp_model.CpModel()
        wage_unit = self.slot_hours  # hours per slot

        # x[s, emp] = 1 if employee emp fills seat s
        x: Dict = {}
        seat_emps: Dict[int, list] = {}
        for s_idx, (slot, process_id) in enumerate(seats):
            emps = []
            for emp in self.active_employees:
                eid = emp.employee_id
                if process_id not in self.skills.get(eid, {}):
                    continue
                if slot not in self.employee_available_slots.get(eid, []):
                    continue
                if slot in reserved.get(eid, set()):
                    continue
                x[(s_idx, eid)] = model.NewBoolVar(f"x_{s_idx}_{eid}")
                emps.append(eid)
            seat_emps[s_idx] = emps
            if emps:
                model.Add(sum(x[(s_idx, eid)] for eid in emps) == 1)
            else:
                return  # a seat is unfillable; abort and keep current solution

        # One process per slot per employee
        slots_set = set(slot for slot, _ in seats)
        for emp in self.active_employees:
            eid = emp.employee_id
            for slot in slots_set:
                vars_here = [
                    x[(s_idx, eid)]
                    for s_idx, (s_slot, _) in enumerate(seats)
                    if s_slot == slot and (s_idx, eid) in x
                ]
                if len(vars_here) > 1:
                    model.Add(sum(vars_here) <= 1)

        # Per-employee overtime: cost = base*n + (rate-1)*base*overtime_slots
        threshold_slots = self.overtime_threshold_minutes // self.slot_minutes
        cost_terms = []
        SCALE = 100  # integer scaling for wages
        for emp in self.active_employees:
            eid = emp.employee_id
            my_vars = [x[(s_idx, eid)] for s_idx in range(len(seats)) if (s_idx, eid) in x]
            if not my_vars:
                continue
            wage = float(emp.hourly_wage)
            base_per_slot = int(round(wage * wage_unit * SCALE))
            ot_extra = int(round(wage * wage_unit * (self.overtime_wage_rate - 1.0) * SCALE))

            n = model.NewIntVar(0, len(my_vars), f"n_{eid}")
            model.Add(n == sum(my_vars))
            ot = model.NewIntVar(0, len(my_vars), f"ot_{eid}")
            # ot >= n - threshold ; ot >= 0
            model.Add(ot >= n - threshold_slots)
            cost_terms.append(base_per_slot * n + ot_extra * ot)

        model.Minimize(sum(cost_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_sec
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        # CP-SAT explores a huge space internally; surface that effort
        self.patterns_evaluated += int(solver.NumBranches())

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return  # keep current solution

        # Rebuild assignments from the solution (preserve breaks)
        new_assignments: Dict[str, Dict[str, Assignment]] = {
            e.employee_id: {} for e in self.active_employees
        }
        # Re-place reserved (break) slots
        for emp_id, ea in assignments.items():
            for slot, a in ea.items():
                if a.slot_type != "WORK":
                    new_assignments.setdefault(emp_id, {})[slot] = a
        # Place WORK seats per solver decision
        for s_idx, (slot, process_id) in enumerate(seats):
            for eid in seat_emps[s_idx]:
                if solver.Value(x[(s_idx, eid)]) == 1:
                    emp = next(e for e in self.active_employees if e.employee_id == eid)
                    is_ot = self._is_overtime_slot(emp, slot, new_assignments[eid])
                    cost = self._calc_slot_cost(emp, slot, new_assignments[eid])
                    new_assignments[eid][slot] = Assignment(
                        employee_id=eid,
                        process_id=process_id,
                        time_slot_start=slot,
                        slot_type="WORK",
                        is_overtime=is_ot,
                        slot_cost=cost,
                    )
                    break

        # Commit back into the caller's dict
        for emp_id in list(assignments.keys()):
            assignments[emp_id] = new_assignments.get(emp_id, {})

    def _dismiss_expensive_workers(self, assignments: Dict[str, Dict[str, Assignment]],
                                    max_candidates: int = 8):
        """
        Send expensive workers home when the remaining workforce can still meet
        all objectives without them.

        max_candidates: 試みる上位高コスト従業員の最大数（計算時間上限のため）。
        改善が見つかった場合のみ次の候補へ進む（1パス）。

        残業務（backlog）が増えない場合のみ解雇を受け入れる。
        backlogが増えると業務未完了のまま人が帰宅してしまうため。
        """
        emps_by_wage = sorted(
            self.active_employees, key=lambda e: -float(e.hourly_wage)
        )
        # 既に稼働中の従業員のみ候補にする（上位max_candidates人まで）
        candidates = [
            e for e in emps_by_wage
            if any(a.slot_type == "WORK" for a in assignments.get(e.employee_id, {}).values())
        ][:max_candidates]

        base_obj = self._objective(assignments)

        # 現状のbacklogを計算するため、trial実行時のbacklogを比較基準として使う
        # 初回は現行割当を再シミュレートして取得する
        _ref_trial: Dict[str, Dict[str, Assignment]] = {
            e.employee_id: {} for e in self.active_employees
        }
        self._assign_lunch_breaks(_ref_trial)
        base_backlog = self._run_flow(_ref_trial)

        for emp in candidates:
            eid = emp.employee_id

            saved_active = self.active_employees
            saved_avail = self.employee_available_slots
            self.active_employees = [e for e in saved_active if e.employee_id != eid]
            self.employee_available_slots = {
                k: v for k, v in saved_avail.items() if k != eid
            }
            self.patterns_evaluated += 1

            trial: Dict[str, Dict[str, Assignment]] = {
                e.employee_id: {} for e in self.active_employees
            }
            self._assign_lunch_breaks(trial)
            trial_backlog = self._run_flow(trial)

            trial_obj = self._objective(trial)

            # 解雇を受け入れる条件：コスト改善 かつ backlogが増えない
            if trial_obj < base_obj - 1e-9 and trial_backlog <= base_backlog + 1e-6:
                # Better without this worker — adopt the trial solution
                for e in self.active_employees:
                    assignments[e.employee_id] = trial[e.employee_id]
                for slot, a in list(assignments[eid].items()):
                    if a.slot_type == "WORK":
                        del assignments[eid][slot]
                base_obj = trial_obj
                base_backlog = trial_backlog
                # 次の候補も時給降順で継続（while不要、forで十分）
            else:
                self.active_employees = saved_active
                self.employee_available_slots = saved_avail

    def run(self):
        raise NotImplementedError
