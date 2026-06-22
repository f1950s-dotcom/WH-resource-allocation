"""
案B 最低コストアルゴリズム
案Aの初期解から、安い人員優先で配置換えを行う
"""
import math
import copy
from typing import Dict, List

from .base import BaseOptimizer, Assignment, _parse_time
from .fastest import FastestOptimizer


class CheapestOptimizer(BaseOptimizer):
    RESULT_TYPE = "CHEAPEST"

    def run(self):
        # Start from scratch but use cheapest-first ordering
        assignments: Dict[str, Dict[str, Assignment]] = {
            emp.employee_id: {} for emp in self.active_employees
        }

        self._assign_lunch_breaks(assignments)

        all_process_ids = self.process_order
        all_slots = sorted(set(
            slot
            for proc_slots in self.required_slots.values()
            for slot in proc_slots.keys()
        ))

        for slot in all_slots:
            quotas = self._compute_slot_quotas(slot, all_process_ids)
            for process_id in all_process_ids:
                needed = quotas.get(process_id, 0)
                if needed <= 0:
                    continue

                # Sort by effective wage: cheapest first, prefer no overtime
                def sort_key(emp):
                    emp_assignments = assignments[emp.employee_id]
                    is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
                    wage = float(emp.hourly_wage)
                    effective = wage * (self.overtime_wage_rate if is_ot else 1.0)
                    skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
                    return (effective, -skill)

                sorted_emps = sorted(self.active_employees, key=sort_key)

                assigned_count = 0
                for emp in sorted_emps:
                    if assigned_count >= needed:
                        break
                    emp_assignments = assignments[emp.employee_id]
                    if self.can_assign(emp, process_id, slot, emp_assignments):
                        is_ot = self._is_overtime_slot(emp, slot, emp_assignments)
                        cost = self._calc_slot_cost(emp, slot, emp_assignments)
                        emp_assignments[slot] = Assignment(
                            employee_id=emp.employee_id,
                            process_id=process_id,
                            time_slot_start=slot,
                            slot_type="WORK",
                            is_overtime=is_ot,
                            slot_cost=cost,
                        )
                        assigned_count += 1

        # Local search: replace expensive assignments with cheaper ones
        self._local_search_cheapest(assignments, max_iter=200)

        score = self.calc_score(assignments)
        self._save_result(assignments, score)

    def _local_search_cheapest(
        self, assignments: Dict[str, Dict[str, Assignment]], max_iter: int = 200
    ):
        """Try replacing expensive assignments with cheaper alternatives."""
        for _ in range(max_iter):
            improved = False

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

            # Try to find a cheaper replacement
            replaced = False
            for emp in self.active_employees:
                if emp.employee_id == worst_emp_id:
                    continue
                emp_assignments = assignments[emp.employee_id]
                if self.can_assign(emp, worst_process_id, worst_slot, emp_assignments):
                    new_cost = self._calc_slot_cost(emp, worst_slot, emp_assignments)
                    if new_cost < worst_cost:
                        # Swap
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
                        improved = True
                        break

            if not replaced:
                # Mark this slot to skip next iteration by temporarily zeroing cost
                # (just break to avoid infinite loop)
                break

            if not improved:
                break
