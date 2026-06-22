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
    ProcessConnection,
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

    def __init__(self, plan_date: str, db: Session):
        self.plan_date = plan_date
        self.db = db
        self.slot_minutes = 15

        # Load system conditions
        conds = {c.condition_key: c.condition_value for c in db.query(SystemCondition).all()}
        self.overtime_wage_rate = float(conds.get("overtime_wage_rate", "1.20"))
        self.overtime_threshold_minutes = int(conds.get("overtime_threshold_minutes", "480"))
        self.lunch_break_start = conds.get("lunch_break_start", "11:30")
        self.lunch_break_end = conds.get("lunch_break_end", "13:00")
        self.lunch_break_duration = int(conds.get("lunch_break_duration_minutes", "60"))
        self.legal_break_threshold = int(conds.get("legal_break_threshold_minutes", "360"))
        self.legal_break_minutes = int(conds.get("legal_break_minutes", "45"))

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

        # Build employee available slots (before breaks)
        self.employee_available_slots: Dict[str, List[str]] = {}
        for emp in self.active_employees:
            cond = self.work_conditions[emp.employee_id]
            slots = _generate_slots(cond.work_start_time, cond.work_end_time, self.slot_minutes)
            self.employee_available_slots[emp.employee_id] = slots

        # Load volume expansions
        expansions = db.query(VolumeExpansion).filter(
            VolumeExpansion.plan_date == plan_date
        ).all()
        # {process_id: {time_slot: required_person_slots}}
        self.required_slots: Dict[str, Dict[str, float]] = {}
        for e in expansions:
            self.required_slots.setdefault(e.process_id, {})[e.time_slot_start] = float(e.required_person_slots)

        # Build topological order of processes (upstream first)
        connections = db.query(ProcessConnection).all()
        upstream_of: Dict[str, str] = {c.to_process_id: c.from_process_id for c in connections}
        all_pids = list(self.required_slots.keys())
        visited: set = set()
        topo_order: List[str] = []

        def _visit(pid: str):
            if pid in visited:
                return
            visited.add(pid)
            up = upstream_of.get(pid)
            if up and up in self.required_slots:
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

    def _save_result(self, assignments: Dict[str, Dict[str, Assignment]], score: dict):
        """Persist optimization result to DB."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        result_id = str(uuid.uuid4())

        # Delete previous results of same type for this date
        self.db.query(OptimizationResult).filter(
            OptimizationResult.plan_date == self.plan_date,
            OptimizationResult.result_type == self.RESULT_TYPE,
        ).delete()

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

    def run(self):
        raise NotImplementedError
