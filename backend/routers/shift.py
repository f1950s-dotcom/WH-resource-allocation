from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from database import get_db
from models import OptimizationResult, OptimizationAssignment, Employee, Process
from services.excel_exporter import generate_excel

router = APIRouter()


@router.get("/shifts/{date}")
def get_shifts(date: str, db: Session = Depends(get_db)):
    # Get selected result for date
    result = db.query(OptimizationResult).filter(
        OptimizationResult.plan_date == date,
        OptimizationResult.is_selected == 1,
    ).first()

    if not result:
        # Return latest result if no selected
        result = db.query(OptimizationResult).filter(
            OptimizationResult.plan_date == date,
        ).order_by(OptimizationResult.calculated_at.desc()).first()

    if not result:
        raise HTTPException(status_code=404, detail="No optimization results found for this date")

    assignments = db.query(OptimizationAssignment).filter(
        OptimizationAssignment.result_id == result.result_id
    ).all()

    employees = {e.employee_id: e.name for e in db.query(Employee).all()}
    processes = {p.process_id: p.process_name for p in db.query(Process).all()}

    # Build employee timeline
    employee_timeline = {}
    for a in assignments:
        emp_id = a.employee_id
        if emp_id not in employee_timeline:
            employee_timeline[emp_id] = {
                "employee_id": emp_id,
                "employee_name": employees.get(emp_id, emp_id),
                "slots": [],
            }
        employee_timeline[emp_id]["slots"].append({
            "time_slot_start": a.time_slot_start,
            "process_id": a.process_id,
            "process_name": processes.get(a.process_id, "") if a.process_id else None,
            "slot_type": a.slot_type,
            "is_overtime": bool(a.is_overtime),
            "slot_cost": float(a.slot_cost),
        })

    # Sort slots per employee
    for emp_data in employee_timeline.values():
        emp_data["slots"].sort(key=lambda x: x["time_slot_start"])

    return {
        "date": date,
        "result_id": result.result_id,
        "result_type": result.result_type,
        "employees": list(employee_timeline.values()),
    }


@router.get("/shifts/{date}/export")
def export_shifts(date: str, db: Session = Depends(get_db)):
    result = db.query(OptimizationResult).filter(
        OptimizationResult.plan_date == date,
        OptimizationResult.is_selected == 1,
    ).first()

    if not result:
        result = db.query(OptimizationResult).filter(
            OptimizationResult.plan_date == date,
        ).order_by(OptimizationResult.calculated_at.desc()).first()

    if not result:
        raise HTTPException(status_code=404, detail="No optimization results found for this date")

    assignments = db.query(OptimizationAssignment).filter(
        OptimizationAssignment.result_id == result.result_id
    ).all()

    employees = db.query(Employee).all()
    processes = db.query(Process).all()

    excel_bytes = generate_excel(date, result, assignments, employees, processes)

    filename = f"shift_{date}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
