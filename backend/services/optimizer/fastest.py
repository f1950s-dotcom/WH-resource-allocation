"""
案A 最速完了アルゴリズム
スキルレベル降順・時給昇順で配置し、最速完了を目指す
"""
from typing import Dict

from .base import BaseOptimizer, Assignment


class FastestOptimizer(BaseOptimizer):
    RESULT_TYPE = "FASTEST"

    def _emp_sort_key(self, emp, process_id, slot, assignments):
        # Highest skill for this process first, then lowest wage
        skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
        return (-skill, float(emp.hourly_wage))

    def run(self):
        assignments: Dict[str, Dict[str, Assignment]] = {
            emp.employee_id: {} for emp in self.active_employees
        }
        self._assign_lunch_breaks(assignments)
        self._run_flow(assignments)

        score = self.calc_score(assignments)
        self._save_result(assignments, score)
