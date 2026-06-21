"""
シフトデータ生成サービス
最適化結果から人別・工程別のシフトデータを構築する
"""
from typing import Dict, List, Any

from models import OptimizationAssignment, Employee, Process


def build_shift_data(
    date: str,
    result,
    assignments: List[OptimizationAssignment],
    employees: List[Employee],
    processes: List[Process],
) -> Dict[str, Any]:
    emp_map = {e.employee_id: e.name for e in employees}
    proc_map = {p.process_id: p.process_name for p in processes}

    # Build all time slots
    all_slots = sorted(set(a.time_slot_start for a in assignments))

    # Employee timeline: employee -> slot -> assignment info
    employee_timeline = {}
    for a in assignments:
        emp_id = a.employee_id
        if emp_id not in employee_timeline:
            employee_timeline[emp_id] = {
                "employee_id": emp_id,
                "employee_name": emp_map.get(emp_id, emp_id),
                "slots": {},
            }
        employee_timeline[emp_id]["slots"][a.time_slot_start] = {
            "process_id": a.process_id,
            "process_name": proc_map.get(a.process_id, "") if a.process_id else None,
            "slot_type": a.slot_type,
            "is_overtime": bool(a.is_overtime),
            "slot_cost": float(a.slot_cost),
        }

    # Process timeline: process -> slot -> [employee names]
    process_timeline = {}
    for a in assignments:
        if a.slot_type != "WORK" or not a.process_id:
            continue
        proc_id = a.process_id
        if proc_id not in process_timeline:
            process_timeline[proc_id] = {
                "process_id": proc_id,
                "process_name": proc_map.get(proc_id, proc_id),
                "slots": {},
            }
        slot_key = a.time_slot_start
        process_timeline[proc_id]["slots"].setdefault(slot_key, []).append(
            emp_map.get(a.employee_id, a.employee_id)
        )

    return {
        "date": date,
        "result_id": result.result_id,
        "result_type": result.result_type,
        "all_slots": all_slots,
        "employees": list(employee_timeline.values()),
        "processes": list(process_timeline.values()),
    }
