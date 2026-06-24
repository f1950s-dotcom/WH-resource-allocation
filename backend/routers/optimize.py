from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import OptimizationResult, OptimizationAssignment, Employee, Process
from schemas import OptimizationResultResponse, OptimizationResultDetail, OptimizationAssignmentResponse
from services.optimizer.fastest import FastestOptimizer
from services.optimizer.cheapest import CheapestOptimizer
from services.optimizer.least_move import LeastMoveOptimizer

router = APIRouter()

# Track running optimizations
_running: dict = {}


def _run_optimization(date: str, method: str):
    from database import engine
    from sqlalchemy.orm import sessionmaker
    from services.volume_expansion import expand_volume
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        # 最適化の前に必ず物量展開を再生成する。
        # これをしないと、物量登録（volume_plans）を変更しても展開
        # （volume_expansions）が古いままとなり、最適化は旧物量で人員を
        # 組む一方、シフト画面は最新物量で再シミュレーションするため、
        # 「各工程で残が出る」不整合が発生する。
        expand_volume(date, db)
        FastestOptimizer(date, db, method).run()
        CheapestOptimizer(date, db, method).run()
        LeastMoveOptimizer(date, db, method).run()
    finally:
        db.close()
    _running.pop(date, None)


@router.post("/optimize/{date}")
def run_optimization(date: str, background_tasks: BackgroundTasks,
                     method: str = "GREEDY", db: Session = Depends(get_db)):
    if date in _running:
        return {"status": "already_running", "date": date}

    if method not in ("GREEDY", "ANNEALING", "ORTOOLS"):
        method = "GREEDY"

    _running[date] = True
    background_tasks.add_task(_run_optimization, date, method)
    return {"status": "started", "date": date, "method": method}


@router.get("/optimize/{date}/results", response_model=List[OptimizationResultResponse])
def get_optimization_results(date: str, db: Session = Depends(get_db)):
    results = db.query(OptimizationResult).filter(
        OptimizationResult.plan_date == date
    ).order_by(OptimizationResult.calculated_at.desc()).all()
    return results


@router.get("/optimize/{date}/results/{result_id}", response_model=OptimizationResultDetail)
def get_optimization_result_detail(date: str, result_id: str, db: Session = Depends(get_db)):
    result = db.query(OptimizationResult).filter(
        OptimizationResult.result_id == result_id,
        OptimizationResult.plan_date == date,
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    assignments = db.query(OptimizationAssignment).filter(
        OptimizationAssignment.result_id == result_id
    ).order_by(
        OptimizationAssignment.employee_id,
        OptimizationAssignment.time_slot_start,
    ).all()
    emp_names = {e.employee_id: e.name for e in db.query(Employee).all()}
    proc_names = {p.process_id: p.process_name for p in db.query(Process).all()}
    return OptimizationResultDetail(
        result=OptimizationResultResponse(
            result_id=result.result_id,
            plan_date=result.plan_date,
            result_type=result.result_type,
            total_cost=float(result.total_cost),
            total_overtime_cost=float(result.total_overtime_cost),
            total_process_moves=result.total_process_moves,
            is_deadline_met=bool(result.is_deadline_met),
            deadline_violations=result.deadline_violations,
            calculated_at=result.calculated_at,
            is_selected=bool(result.is_selected),
            patterns_evaluated=result.patterns_evaluated,
        ),
        assignments=[
            OptimizationAssignmentResponse(
                assignment_id=a.assignment_id,
                result_id=a.result_id,
                employee_id=a.employee_id,
                employee_name=emp_names.get(a.employee_id, a.employee_id),
                process_id=a.process_id,
                process_name=proc_names.get(a.process_id) if a.process_id else None,
                time_slot_start=a.time_slot_start,
                slot_type=a.slot_type,
                is_overtime=bool(a.is_overtime),
                slot_cost=float(a.slot_cost),
            )
            for a in assignments
        ],
    )


@router.post("/optimize/{date}/results/{result_id}/select")
def select_result(date: str, result_id: str, db: Session = Depends(get_db)):
    result = db.query(OptimizationResult).filter(
        OptimizationResult.result_id == result_id,
        OptimizationResult.plan_date == date,
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    # Deselect others
    db.query(OptimizationResult).filter(
        OptimizationResult.plan_date == date,
        OptimizationResult.result_id != result_id,
    ).update({"is_selected": 0})
    result.is_selected = 1
    db.commit()
    return {"status": "selected", "result_id": result_id}


@router.get("/optimize/{date}/status")
def get_status(date: str):
    return {"date": date, "running": date in _running}
