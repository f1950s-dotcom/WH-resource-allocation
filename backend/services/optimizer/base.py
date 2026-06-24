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

        # Delete previous results of same type for this date, and their
        # assignments (avoid orphaned assignment rows accumulating on re-run)
        old_ids = [
            r.result_id for r in self.db.query(OptimizationResult).filter(
                OptimizationResult.plan_date == self.plan_date,
                OptimizationResult.result_type == self.RESULT_TYPE,
            ).all()
        ]
        if old_ids:
            self.db.query(OptimizationAssignment).filter(
                OptimizationAssignment.result_id.in_(old_ids)
            ).delete(synchronize_session=False)
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
            patterns_evaluated=self.patterns_evaluated,
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

            # 3. Assign workers and compute actual throughput, upstream first
            for pid in self.process_order:
                need = quotas.get(pid, 0)
                if need <= 0:
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
                    # Each examined candidate counts as one evaluated pattern
                    self.patterns_evaluated += 1
                    if self.can_assign(emp, pid, slot, emp_assignments):
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
                        # Accumulate skill-adjusted capacity for this employee
                        skill = self.skills.get(emp.employee_id, {}).get(pid, 1)
                        rate = self.skill_rates.get(skill, 1.0)
                        _assigned_capacity += self.base_prod.get(pid, 0.0) * rate * self.slot_hours

                # Actual throughput: sum of each assigned employee's skill-adjusted capacity
                throughput = min(backlog[pid], _assigned_capacity)
                backlog[pid] -= throughput

                # 4. Propagate to downstream with 15-min lag
                if throughput > 0 and next_slot:
                    for down_pid in self.downstream_of.get(pid, []):
                        if down_pid not in incoming:
                            continue
                        rate = self.conv_rate.get(down_pid, 1.0)
                        incoming[down_pid][next_slot] = (
                            incoming[down_pid].get(next_slot, 0.0) + throughput * rate
                        )

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
            if self.can_assign(emp, process_id, slot, assignments[emp.employee_id]):
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

    def _dismiss_expensive_workers(self, assignments: Dict[str, Dict[str, Assignment]]):
        """
        Send expensive workers home when the remaining workforce can still meet
        all objectives without them.

        The correct approach is NOT slot-swapping (the other workers are already
        occupied), but re-simulating the flow WITHOUT the expensive worker and
        checking whether the strategy objective (completion time / cost / moves)
        improves. If yes, replace the full assignment dict with the cheaper
        solution. Repeat until no further dismissal is possible.
        """
        emps_by_wage = sorted(
            self.active_employees, key=lambda e: -float(e.hourly_wage)
        )

        improved = True
        while improved:
            improved = False
            base_obj = self._objective(assignments)

            for emp in emps_by_wage:
                eid = emp.employee_id
                # Skip workers who are already idle (no WORK slots)
                if not any(a.slot_type == "WORK" for a in assignments[eid].values()):
                    continue

                # Temporarily remove this worker from the active set
                saved_active = self.active_employees
                saved_avail = self.employee_available_slots
                self.active_employees = [e for e in saved_active if e.employee_id != eid]
                self.employee_available_slots = {
                    k: v for k, v in saved_avail.items() if k != eid
                }
                self.patterns_evaluated += 1

                # Re-run the full flow with the reduced workforce
                trial: Dict[str, Dict[str, Assignment]] = {
                    e.employee_id: {} for e in self.active_employees
                }
                self._assign_lunch_breaks(trial)
                self._run_flow(trial)

                trial_obj = self._objective(trial)

                if trial_obj < base_obj - 1e-9:
                    # Better without this worker — adopt the trial solution,
                    # leaving the dismissed worker with only their break slots
                    for e in self.active_employees:
                        assignments[e.employee_id] = trial[e.employee_id]
                    # Clear all WORK slots for the dismissed employee
                    for slot, a in list(assignments[eid].items()):
                        if a.slot_type == "WORK":
                            del assignments[eid][slot]
                    improved = True
                    # Restore state (active_employees already shrunk permanently)
                    # Rebuild emps_by_wage without dismissed worker
                    emps_by_wage = [e for e in emps_by_wage if e.employee_id != eid]
                    break  # restart while loop with updated workforce
                else:
                    # Restore
                    self.active_employees = saved_active
                    self.employee_available_slots = saved_avail

    def run(self):
        raise NotImplementedError
