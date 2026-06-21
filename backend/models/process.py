from sqlalchemy import Column, Text, Numeric, Integer, ForeignKey, UniqueConstraint
from database import Base


class Process(Base):
    __tablename__ = "processes"

    process_id = Column(Text, primary_key=True)
    process_name = Column(Text, nullable=False)
    line_type = Column(Text, nullable=False)
    base_productivity = Column(Numeric(10, 3), nullable=False)
    buffer_capacity = Column(Integer, nullable=False, default=0)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1)


class ProcessConnection(Base):
    __tablename__ = "process_connections"

    connection_id = Column(Text, primary_key=True)
    from_process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)
    to_process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)

    __table_args__ = (UniqueConstraint("from_process_id", "to_process_id"),)


class VolumeConversionRule(Base):
    __tablename__ = "volume_conversion_rules"

    rule_id = Column(Text, primary_key=True)
    source_type = Column(Text, nullable=False)
    process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)
    conversion_rate = Column(Numeric(8, 4), nullable=False)
    unit_description = Column(Text)

    __table_args__ = (UniqueConstraint("source_type", "process_id"),)


class ProcessDeadlineCondition(Base):
    __tablename__ = "process_deadline_conditions"

    deadline_id = Column(Text, primary_key=True)
    process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)
    must_finish_by = Column(Text, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
