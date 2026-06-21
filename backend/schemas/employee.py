from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class EmployeeCreate(BaseModel):
    name: str
    hourly_wage: float
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    hourly_wage: Optional[float] = None
    is_active: Optional[bool] = None


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: str
    name: str
    hourly_wage: float
    is_active: bool
    created_at: str
    updated_at: str


class SkillCreate(BaseModel):
    process_id: str
    skill_level: int


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: str
    employee_id: str
    process_id: str
    skill_level: int


class SkillsUpdate(BaseModel):
    skills: List[SkillCreate]


class WorkConditionCreate(BaseModel):
    day_of_week: int
    work_start_time: str
    work_end_time: str
    overtime_available: bool = False
    min_work_minutes: int = 0


class WorkConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    condition_id: str
    employee_id: str
    day_of_week: int
    work_start_time: str
    work_end_time: str
    overtime_available: bool
    min_work_minutes: int


class WorkConditionsUpdate(BaseModel):
    conditions: List[WorkConditionCreate]
