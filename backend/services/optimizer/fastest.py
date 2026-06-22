"""
案A 最速完了アルゴリズム
スキルレベル降順・時給昇順で配置し、最速完了を目指す
"""
import math
from typing import Dict, List, Optional

from .base import BaseOptimizer, Assignment, _parse_time, _format_time, _generate_slots


class FastestOptimizer(BaseOptimizer):
    RESULT_TYPE = "FASTEST"

    def run(self):
        assignments: Dict[str, Dict[str, Assignment]] = {
            emp.employee_id: {} for emp in self.active_employees
        }

        # Assign lunch breaks first
        self._assign_lunch_breaks(assignments)

        # Sort employees: skill_level desc (will be per-process), wage asc
        # We'll sort per process when assigning
        all_process_ids = self.process_order

        # Get all time slots from required_slots
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

                # Sort employees: highest skill for this process first, then lowest wage
                def sort_key(emp):
                    skill = self.skills.get(emp.employee_id, {}).get(process_id, 0)
                    return (-skill, float(emp.hourly_wage))

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

        # Local search: try to improve (up to 200 iterations)
        self._local_search(assignments, max_iter=200)

        score = self.calc_score(assignments)
        self._save_result(assignments, score)

    def _local_search(self, assignments: Dict[str, Dict[str, Assignment]], max_iter: int = 200):
        """
        Simple local search: try to assign unassigned required slots
        by finding any eligible employee.
        """
        all_process_ids = self.process_order
        all_slots = sorted(set(
            slot
            for proc_slots in self.required_slots.values()
            for slot in proc_slots.keys()
        ))

        for _ in range(max_iter):
            improved = False
            for slot in all_slots:
                for process_id in all_process_ids:
                    required = self.required_slots.get(process_id, {}).get(slot, 0.0)
                    if required <= 0:
                        continue

                    # Count current assignments for this slot/process
                    current = sum(
                        1 for emp_assignments in assignments.values()
                        for a in emp_assignments.values()
                        if a.process_id == process_id
                        and a.time_slot_start == slot
                        and a.slot_type == "WORK"
                    )
                    needed = math.ceil(required)
                    if current >= needed:
                        continue

                    # Try to find an employee to assign
                    for emp in self.active_employees:
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
                            improved = True
                            break

            if not improved:
                break
