from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime

from database import get_db
from models import VolumePlan, VolumeExpansion
from schemas import VolumePlansUpdate, VolumePlanResponse, VolumeExpansionResponse
from services.volume_expansion import expand_volume

router = APIRouter()


def now_str():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


@router.get("/volume-plans/{date}", response_model=List[VolumePlanResponse])
def get_volume_plans(date: str, db: Session = Depends(get_db)):
    return db.query(VolumePlan).filter(VolumePlan.plan_date == date).all()


@router.put("/volume-plans/{date}", response_model=List[VolumePlanResponse])
def update_volume_plans(date: str, body: VolumePlansUpdate, db: Session = Depends(get_db)):
    now = now_str()
    # Determine which volume_types are present in the submitted entries
    submitted_types = {entry.volume_type for entry in body.entries}
    # Delete only the rows for the submitted type(s), leaving other types intact
    db.query(VolumePlan).filter(
        VolumePlan.plan_date == date,
        VolumePlan.volume_type.in_(submitted_types),
    ).delete(synchronize_session=False)
    plans = []
    for entry in body.entries:
        plan = VolumePlan(
            volume_plan_id=str(uuid.uuid4()),
            plan_date=date,
            volume_type=entry.volume_type,
            time_slot_start=entry.time_slot_start,
            volume=entry.volume,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        plans.append(plan)
    db.commit()
    for p in plans:
        db.refresh(p)
    return plans


@router.post("/volume-plans/{date}/expand")
def expand_volume_plans(date: str, db: Session = Depends(get_db)):
    try:
        result = expand_volume(date, db)
        return {"status": "ok", "expanded_count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/volume-expansions/{date}", response_model=List[VolumeExpansionResponse])
def get_volume_expansions(date: str, db: Session = Depends(get_db)):
    return db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == date).order_by(
        VolumeExpansion.process_id, VolumeExpansion.time_slot_start
    ).all()
