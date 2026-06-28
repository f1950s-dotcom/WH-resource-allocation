"""
案B 最低コストアルゴリズム
安い人員を優先して配置する。配置後に高コストな割当を安い人員へ置換する。
"""
from typing import Dict

from .base import BaseOptimizer, Assignment
from .mip import solve_mip_isolated


class CheapestOptimizer(BaseOptimizer):
    RESULT_TYPE = "CHEAPEST"

    def _emp_sort_key(self, emp, process_id, slot, assignments):
        # 「処理1個あたりのコスト」が安い順に選ぶ。
        # 時給だけで選ぶと、安いが低スキル（低生産性）な人を優先してしまい、
        # 同じ物量を捌くのに延べ人時が増えて総コストがかえって高くなる
        # （最速案より高くなる逆転が起きる）。実効時給を生産性（スキル率）で
        # 割った「単位処理コスト」で選ぶことで、総コスト最小に近づける。
        emp_assignments = assignments[emp.employee_id]
        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
        wage = float(emp.hourly_wage)
        effective = wage * (self.overtime_wage_rate if is_ot else 1.0)
        skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
        # スキル無し（=配置不可）は最後尾へ。スキル有りは実効時給÷生産性。
        rate = self.skill_rates.get(skill, 0.0)
        cost_per_unit = (effective / rate) if rate > 0 else float("inf")
        return (cost_per_unit, -skill)

    def _objective(self, assignments):
        return self.calc_score(assignments)["total_cost"]

    def run(self):
        # GREEDYモードではMIPをスキップして高速ヒューリスティックのみ使用
        assignments = None
        if self.method != "GREEDY":
            assignments = solve_mip_isolated(self, "COST")
        if assignments is None:
            # フォールバック：従来のフローヒューリスティック＋帰宅後処理
            assignments = {emp.employee_id: {} for emp in self.active_employees}
            self._assign_lunch_breaks(assignments)
            self._run_flow(assignments)
            if self.method == "GREEDY":
                self._local_search_cheapest(assignments, max_iter=200)
            else:
                self._refine(assignments)
            self._dismiss_expensive_workers(assignments)

        # 連続化リペア：処理量・完了時刻・コストを変えずに15分単位の工程切替を削減
        self._repair_continuity(assignments)
        score = self.calc_score(assignments)
        self._save_result(assignments, score)

    def _local_search_cheapest(
        self, assignments: Dict[str, Dict[str, Assignment]], max_iter: int = 200
    ):
        """Try replacing expensive assignments with cheaper alternatives."""
        for _ in range(max_iter):
            # Find most expensive WORK assignment
            worst_cost = 0.0
            worst_emp_id = None
            worst_slot = None
            worst_process_id = None

            for emp_id, emp_assignments in assignments.items():
                for slot, a in emp_assignments.items():
                    if a.slot_type == "WORK" and a.slot_cost > worst_cost:
                        worst_cost = a.slot_cost
                        worst_emp_id = emp_id
                        worst_slot = slot
                        worst_process_id = a.process_id

            if worst_emp_id is None:
                break

            replaced = False
            for emp in self.active_employees:
                if emp.employee_id == worst_emp_id:
                    continue
                emp_assignments = assignments[emp.employee_id]
                self.patterns_evaluated += 1
                if self.can_assign(emp, worst_process_id, worst_slot, emp_assignments):
                    new_cost = self._calc_slot_cost(emp, worst_slot, emp_assignments)
                    if new_cost < worst_cost:
                        del assignments[worst_emp_id][worst_slot]
                        is_ot = self._is_overtime_slot(emp, worst_slot, emp_assignments)
                        emp_assignments[worst_slot] = Assignment(
                            employee_id=emp.employee_id,
                            process_id=worst_process_id,
                            time_slot_start=worst_slot,
                            slot_type="WORK",
                            is_overtime=is_ot,
                            slot_cost=new_cost,
                        )
                        replaced = True
                        break

            if not replaced:
                break
