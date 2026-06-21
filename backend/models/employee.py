from sqlalchemy import Column, Text, Numeric, Integer, ForeignKey, UniqueConstraint
from database import Base


class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    hourly_wage = Column(Numeric(8, 2), nullable=False)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)


class EmployeeProcessSkill(Base):
    __tablename__ = "employee_process_skills"

    skill_id = Column(Text, primary_key=True)
    employee_id = Column(Text, ForeignKey("employees.employee_id"), nullable=False)
    process_id = Column(Text, ForeignKey("processes.process_id"), nullable=False)
    skill_level = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("employee_id", "process_id"),)


class EmployeeWorkCondition(Base):
    __tablename__ = "employee_work_conditions"

    condition_id = Column(Text, primary_key=True)
    employee_id = Column(Text, ForeignKey("employees.employee_id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    work_start_time = Column(Text, nullable=False)
    work_end_time = Column(Text, nullable=False)
    overtime_available = Column(Integer, nullable=False, default=0)
    min_work_minutes = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("employee_id", "day_of_week"),)
