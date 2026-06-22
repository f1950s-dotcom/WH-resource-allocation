"""
案B 最低コストアルゴリズム
安い人員を優先して配置する。配置後に高コストな割当を安い人員へ置換する。
"""
from typing import Dict

from .base import BaseOptimizer, Assignment


class CheapestOptimizer(BaseOptimizer):
    RESULT_TYPE = "CHEAPEST"

    def _emp_sort_key(self, emp, process_id, slot, assignments):
        # Cheapest effective wage first (avoid overtime), higher skill as tiebreak
        emp_assignments = assignments[emp.employee_id]
        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
        wage = float(emp.hourly_wage)
        effective = wage * (self.overtime_wage_rate if is_ot else 1.0)
        skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
        return (effective, -skill)

    def run(self):
        assignments: Dict[str, Dict[str, Assignment]] = {
            emp.employee_id: {} for emp in self.active_employees
        }
        self._assign_lunch_breaks(assignments)
        self._run_flow(assignments)

        # Replace expensive assignments with cheaper alternatives
        # (same process/slot -> headcount and flow unchanged)
        self._local_search_cheapest(assignments, max_iter=200)

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
