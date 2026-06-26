from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any


class OptimizationAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: str
    result_id: str
    employee_id: str
    employee_name: Optional[str] = None
    process_id: Optional[str]
    process_name: Optional[str] = None
    time_slot_start: str
    slot_type: str
    is_overtime: bool
    slot_cost: float


class OptimizationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    result_id: str
    plan_date: str
    result_type: str
    total_cost: float
    total_overtime_cost: float
    total_process_moves: int
    is_deadline_met: bool
    deadline_violations: Optional[str]
    calculated_at: str
    is_selected: bool
    patterns_evaluated: int = 0
    calculation_method: str = "GREEDY"
    solver_status: Optional[str] = None
    solver_gap: Optional[float] = None
    solve_seconds: Optional[float] = None
    process_moves_before_repair: Optional[int] = None


class OptimizationResultDetail(BaseModel):
    result: OptimizationResultResponse
    assignments: List[OptimizationAssignmentResponse]
