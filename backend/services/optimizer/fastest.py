"""
案A 最速完了アルゴリズム
スキルレベル降順・時給昇順で配置し、最速完了を目指す
"""
from typing import Dict

from .base import BaseOptimizer, Assignment, _parse_time
from .mip import solve_mip


class FastestOptimizer(BaseOptimizer):
    RESULT_TYPE = "FASTEST"

    def _emp_sort_key(self, emp, process_id, slot, assignments):
        # Highest skill for this process first, then lowest wage
        skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
        return (-skill, float(emp.hourly_wage))

    def _objective(self, assignments):
        # Primary: finish as early as possible; tiebreak: cheaper
        latest = 0
        for ea in assignments.values():
            for a in ea.values():
                if a.slot_type == "WORK":
                    end = _parse_time(a.time_slot_start) + self.slot_minutes
                    latest = max(latest, end)
        cost = self.calc_score(assignments)["total_cost"]
        return latest * 1_000_000 + cost

    def run(self):
        # GREEDYモードではMIPをスキップして高速ヒューリスティックのみ使用
        assignments = None
        if self.method != "GREEDY":
            assignments = solve_mip(self, "MAKESPAN", time_limit_sec=15.0)
        if assignments is None:
            # フォールバック：従来のフローヒューリスティック＋帰宅後処理
            assignments = {emp.employee_id: {} for emp in self.active_employees}
            self._assign_lunch_breaks(assignments)
            self._run_flow(assignments)
            self._refine(assignments)
            self._dismiss_expensive_workers(assignments)

        score = self.calc_score(assignments)
        self._save_result(assignments, score)
