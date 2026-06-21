from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class VolumePlanEntry(BaseModel):
    volume_type: str
    time_slot_start: str
    volume: float


class VolumePlansUpdate(BaseModel):
    entries: List[VolumePlanEntry]


class VolumePlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    volume_plan_id: str
    plan_date: str
    volume_type: str
    time_slot_start: str
    volume: float
    created_at: str
    updated_at: str


class VolumeExpansionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    expansion_id: str
    plan_date: str
    process_id: str
    time_slot_start: str
    process_volume: float
    carry_over_volume: float
    required_person_slots: float
    calculated_at: str
