from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class ProcessCreate(BaseModel):
    process_name: str
    line_type: str
    base_productivity: float
    buffer_capacity: int = 0
    display_order: int = 0
    is_active: bool = True


class ProcessUpdate(BaseModel):
    process_name: Optional[str] = None
    line_type: Optional[str] = None
    base_productivity: Optional[float] = None
    buffer_capacity: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProcessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    process_id: str
    process_name: str
    line_type: str
    base_productivity: float
    buffer_capacity: int
    display_order: int
    is_active: bool


class ProcessConnectionCreate(BaseModel):
    from_process_id: str
    to_process_id: str


class ProcessConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connection_id: str
    from_process_id: str
    to_process_id: str


class ProcessConnectionsUpdate(BaseModel):
    connections: List[ProcessConnectionCreate]


class VolumeConversionRuleCreate(BaseModel):
    source_type: str
    process_id: str
    conversion_rate: float
    unit_description: Optional[str] = None


class VolumeConversionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    source_type: str
    process_id: str
    conversion_rate: float
    unit_description: Optional[str]


class VolumeConversionRulesUpdate(BaseModel):
    rules: List[VolumeConversionRuleCreate]


class ProcessDeadlineConditionCreate(BaseModel):
    process_id: str
    must_finish_by: str
    is_active: bool = True


class ProcessDeadlineConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    deadline_id: str
    process_id: str
    must_finish_by: str
    is_active: bool


class DeadlineConditionsUpdate(BaseModel):
    deadlines: List[ProcessDeadlineConditionCreate]
