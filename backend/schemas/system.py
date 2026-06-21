from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class SystemConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    condition_key: str
    condition_value: str
    description: Optional[str]


class SystemConditionUpdate(BaseModel):
    condition_key: str
    condition_value: str
    description: Optional[str] = None


class SystemConditionsUpdate(BaseModel):
    conditions: List[SystemConditionUpdate]
