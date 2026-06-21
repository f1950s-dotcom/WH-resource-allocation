from sqlalchemy import Column, Text, Numeric, ForeignKey, UniqueConstraint
from database import Base


class VolumePlan(Base):
    __tablename__ = "volume_plans"

    volume_plan_id = Column(Text, primary_key=True)
    plan_date = Column(Text, nullable=False)
    volume_type = Column(Text, nullable=False)
    time_slot_start = Column(Text, nullable=False)
    volume = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("plan_date", "volume_type", "time_slot_start"),)


class VolumeExpansion(Base):
    __tablename__ = "volume_expansions"

    expansion_id = Column(Text, primary_key=True)
    plan_date = Column(Text, nullable=False)
    process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)
    time_slot_start = Column(Text, nullable=False)
    process_volume = Column(Numeric(10, 2), nullable=False, default=0)
    carry_over_volume = Column(Numeric(10, 2), nullable=False, default=0)
    required_person_slots = Column(Numeric(8, 3), nullable=False, default=0)
    calculated_at = Column(Text, nullable=False)

    __table_args__ = (UniqueConstraint("plan_date", "process_id", "time_slot_start"),)
