"""
物量展開サービス
volume_plans から各工程・スロットごとの必要人員数を計算して volume_expansions に保存する
"""
from datetime import datetime
import uuid
from typing import List

from sqlalchemy.orm import Session

from models import VolumePlan, VolumeConversionRule, VolumeExpansion, Process


def _time_slots_for_date(plans: List[VolumePlan]) -> List[str]:
    """Return sorted unique time slots."""
    slots = sorted(set(p.time_slot_start for p in plans))
    return slots


def expand_volume(plan_date: str, db: Session) -> List[VolumeExpansion]:
    """
    Compute volume expansion for a given date and persist results.
    Returns list of created VolumeExpansion records.
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    # Fetch volume plans
    plans = db.query(VolumePlan).filter(VolumePlan.plan_date == plan_date).all()
    if not plans:
        return []

    # Build lookup: (volume_type, time_slot_start) -> volume
    plan_map: dict = {}
    for p in plans:
        plan_map[(p.volume_type, p.time_slot_start)] = float(p.volume)

    # Fetch conversion rules
    rules = db.query(VolumeConversionRule).all()
    if not rules:
        return []

    # Fetch active processes
    active_processes = {p.process_id: p for p in db.query(Process).filter(Process.is_active == 1).all()}

    # All time slots
    all_slots = sorted(set(p.time_slot_start for p in plans))

    # Delete existing expansions for this date
    db.query(VolumeExpansion).filter(VolumeExpansion.plan_date == plan_date).delete()

    expansions = []

    for rule in rules:
        process_id = rule.process_id
        if process_id not in active_processes:
            continue

        proc = active_processes[process_id]
        base_productivity = float(proc.base_productivity)
        source_type = rule.source_type
        conversion_rate = float(rule.conversion_rate)

        carry_over = 0.0

        for slot in all_slots:
            raw_volume = plan_map.get((source_type, slot), 0.0)
            process_volume = raw_volume * conversion_rate

            # required person slots = process_volume / (base_productivity × (15/60))
            slot_duration_hours = 15.0 / 60.0
            if base_productivity > 0:
                required_person_slots = process_volume / (base_productivity * slot_duration_hours)
            else:
                required_person_slots = 0.0

            exp = VolumeExpansion(
                expansion_id=str(uuid.uuid4()),
                plan_date=plan_date,
                process_id=process_id,
                time_slot_start=slot,
                process_volume=round(process_volume, 2),
                carry_over_volume=round(carry_over, 2),
                required_person_slots=round(required_person_slots, 3),
                calculated_at=now,
            )
            db.add(exp)
            expansions.append(exp)

            # Simple carry-over: anything not processed in this slot carries to next
            # For now carry_over stays 0 (full capacity assumed available)
            carry_over = 0.0

    db.commit()
    for e in expansions:
        db.refresh(e)

    return expansions
