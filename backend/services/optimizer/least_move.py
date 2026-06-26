"""
案C 最小移動アルゴリズム
案Bの結果をベースに、工程切替回数を最小化する
"""
import math
from typing import Dict, List, Tuple

from .base import BaseOptimizer, Assignment, _parse_time
from .cheapest import CheapestOptimizer
from .mip import solve_mip_isolated


class LeastMoveOptimizer(BaseOptimizer):
    RESULT_TYPE = "LEAST_MOVE"

    def _emp_sort_key(self, emp, process_id, slot, assignments):
        # Prefer employees continuing on the same process (fewer moves),
        # then cheaper effective wage.
        emp_assignments = assignments[emp.employee_id]
        work_slots = sorted(
            [a.time_slot_start for a in emp_assignments.values() if a.slot_type == "WORK"]
        )
        same_process = False
        if work_slots:
            last_a = emp_assignments.get(work_slots[-1])
            if last_a and last_a.process_id == process_id:
                same_process = True
        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
        wage = float(emp.hourly_wage)
        return (0 if same_process else 1, wage * (self.overtime_wage_rate if is_ot else 1.0))

    def _objective(self, assignments):
        # Primary: fewest process moves; tiebreak: cheaper
        s = self.calc_score(assignments)
        return s["total_moves"] * 1_000_000 + s["total_cost"]

    def run(self):
        # GREEDYモードではMIPをスキップして高速ヒューリスティックのみ使用
        assignments = None
        if self.method != "GREEDY":
            assignments = solve_mip_isolated(self, "MOVES")
        if assignments is None:
            # フォールバック：従来のフローヒューリスティック＋帰宅後処理
            assignments = {emp.employee_id: {} for emp in self.active_employees}
            self._assign_lunch_breaks(assignments)
            self._run_flow(assignments)
            if self.method == "GREEDY":
                self._resolve_isolated_slots(assignments, max_iter=200)
            else:
                self._refine(assignments)
            self._dismiss_expensive_workers(assignments)

        score = self.calc_score(assignments)
        self._save_result(assignments, score)

    def _count_moves(self, emp_assignments: Dict[str, Assignment]) -> int:
        """Count process switches for one employee."""
        sorted_slots = sorted(
            [a for a in emp_assignments.values() if a.slot_type == "WORK"],
            key=lambda a: a.time_slot_start,
        )
        moves = 0
        prev = None
        for a in sorted_slots:
            if prev is not None and a.process_id != prev:
                moves += 1
            prev = a.process_id
        return moves

    def _resolve_isolated_slots(
        self, assignments: Dict[str, Dict[str, Assignment]], max_iter: int = 200
    ):
        """
        Detect isolated slots (e.g. [A, A, B, A, A]) and try to move them
        to another employee who already works that process.
        """
        for _ in range(max_iter):
            improved = False

            for emp_id, emp_assignments in assignments.items():
                work_slots = sorted(
                    [a for a in emp_assignments.values() if a.slot_type == "WORK"],
                    key=lambda a: a.time_slot_start,
                )
                if len(work_slots) < 3:
                    continue

                # Find isolated slots
                for i in range(1, len(work_slots) - 1):
                    prev_a = work_slots[i - 1]
                    curr_a = work_slots[i]
                    next_a = work_slots[i + 1]

                    # Isolated if neighbors both differ from current
                    if prev_a.process_id != curr_a.process_id and next_a.process_id != curr_a.process_id:
                        # Try to hand off this slot to another employee
                        target_process = curr_a.process_id
                        target_slot = curr_a.time_slot_start

                        moved = False
                        for other_emp in self.active_employees:
                            if other_emp.employee_id == emp_id:
                                continue
                            other_assignments = assignments[other_emp.employee_id]

                            # Check if other already works this process in adjacent slot
                            adjacent_slots = []
                            for a in other_assignments.values():
                                if a.slot_type == "WORK" and a.process_id == target_process:
                                    if abs(_parse_time(a.time_slot_start) - _parse_time(target_slot)) <= 15:
                                        adjacent_slots.append(a)

                            if not adjacent_slots:
                                continue

                            self.patterns_evaluated += 1
                            if self.can_assign(other_emp, target_process, target_slot, other_assignments):
                                old_moves_emp = self._count_moves(emp_assignments)
                                old_moves_other = self._count_moves(other_assignments)

                                # Tentatively move
                                removed = emp_assignments.pop(target_slot)
                                is_ot = self._is_overtime_slot(other_emp, target_slot, other_assignments)
                                cost = self._calc_slot_cost(other_emp, target_slot, other_assignments)
                                other_assignments[target_slot] = Assignment(
                                    employee_id=other_emp.employee_id,
                                    process_id=target_process,
                                    time_slot_start=target_slot,
                                    slot_type="WORK",
                                    is_overtime=is_ot,
                                    slot_cost=cost,
                                )

                                new_moves_emp = self._count_moves(emp_assignments)
                                new_moves_other = self._count_moves(other_assignments)

                                if (new_moves_emp + new_moves_other) < (old_moves_emp + old_moves_other):
                                    improved = True
                                    moved = True
                                    break
                                else:
                                    # Revert
                                    emp_assignments[target_slot] = removed
                                    del other_assignments[target_slot]

                        if moved:
                            break  # Restart outer loop

            if not improved:
                break
