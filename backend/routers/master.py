from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime

from database import get_db
from models import (
    Employee, EmployeeProcessSkill, EmployeeWorkCondition,
    Process, ProcessConnection, VolumeConversionRule, ProcessDeadlineCondition,
    SystemCondition,
)
from schemas import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    SkillResponse, SkillsUpdate,
    WorkConditionResponse, WorkConditionsUpdate,
    ProcessCreate, ProcessUpdate, ProcessResponse,
    ProcessConnectionResponse, ProcessConnectionsUpdate,
    VolumeConversionRuleResponse, VolumeConversionRulesUpdate,
    ProcessDeadlineConditionResponse, DeadlineConditionsUpdate,
    SystemConditionResponse, SystemConditionsUpdate,
)

router = APIRouter()


def now_str():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


# ─── Employees ───────────────────────────────────────────────────────────────

@router.get("/employees", response_model=List[EmployeeResponse])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).all()


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
def create_employee(body: EmployeeCreate, db: Session = Depends(get_db)):
    now = now_str()
    emp = Employee(
        employee_id=str(uuid.uuid4()),
        name=body.name,
        hourly_wage=body.hourly_wage,
        is_active=1 if body.is_active else 0,
        created_at=now,
        updated_at=now,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: str, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.put("/employees/{employee_id}", response_model=EmployeeResponse)
def update_employee(employee_id: str, body: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if body.name is not None:
        emp.name = body.name
    if body.hourly_wage is not None:
        emp.hourly_wage = body.hourly_wage
    if body.is_active is not None:
        emp.is_active = 1 if body.is_active else 0
    emp.updated_at = now_str()
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: str, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()


# ─── Employee Skills ──────────────────────────────────────────────────────────

@router.get("/employees/{employee_id}/skills", response_model=List[SkillResponse])
def get_employee_skills(employee_id: str, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return db.query(EmployeeProcessSkill).filter(
        EmployeeProcessSkill.employee_id == employee_id
    ).all()


@router.put("/employees/{employee_id}/skills", response_model=List[SkillResponse])
def update_employee_skills(employee_id: str, body: SkillsUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    # Delete existing
    db.query(EmployeeProcessSkill).filter(
        EmployeeProcessSkill.employee_id == employee_id
    ).delete()
    # Insert new
    skills = []
    for s in body.skills:
        skill = EmployeeProcessSkill(
            skill_id=str(uuid.uuid4()),
            employee_id=employee_id,
            process_id=s.process_id,
            skill_level=s.skill_level,
        )
        db.add(skill)
        skills.append(skill)
    db.commit()
    for s in skills:
        db.refresh(s)
    return skills


# ─── Employee Work Conditions ─────────────────────────────────────────────────

@router.get("/employees/{employee_id}/conditions", response_model=List[WorkConditionResponse])
def get_employee_conditions(employee_id: str, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return db.query(EmployeeWorkCondition).filter(
        EmployeeWorkCondition.employee_id == employee_id
    ).all()


@router.put("/employees/{employee_id}/conditions", response_model=List[WorkConditionResponse])
def update_employee_conditions(employee_id: str, body: WorkConditionsUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.query(EmployeeWorkCondition).filter(
        EmployeeWorkCondition.employee_id == employee_id
    ).delete()
    conditions = []
    for c in body.conditions:
        cond = EmployeeWorkCondition(
            condition_id=str(uuid.uuid4()),
            employee_id=employee_id,
            day_of_week=c.day_of_week,
            work_start_time=c.work_start_time,
            work_end_time=c.work_end_time,
            overtime_available=1 if c.overtime_available else 0,
            min_work_minutes=c.min_work_minutes,
        )
        db.add(cond)
        conditions.append(cond)
    db.commit()
    for c in conditions:
        db.refresh(c)
    return conditions


# ─── Processes ────────────────────────────────────────────────────────────────

@router.get("/processes", response_model=List[ProcessResponse])
def list_processes(db: Session = Depends(get_db)):
    return db.query(Process).order_by(Process.display_order).all()


@router.post("/processes", response_model=ProcessResponse, status_code=201)
def create_process(body: ProcessCreate, db: Session = Depends(get_db)):
    proc = Process(
        process_id=str(uuid.uuid4()),
        process_name=body.process_name,
        line_type=body.line_type,
        base_productivity=body.base_productivity,
        buffer_capacity=body.buffer_capacity,
        display_order=body.display_order,
        is_active=1 if body.is_active else 0,
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    return proc


@router.get("/processes/{process_id}", response_model=ProcessResponse)
def get_process(process_id: str, db: Session = Depends(get_db)):
    proc = db.query(Process).filter(Process.process_id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    return proc


@router.put("/processes/{process_id}", response_model=ProcessResponse)
def update_process(process_id: str, body: ProcessUpdate, db: Session = Depends(get_db)):
    proc = db.query(Process).filter(Process.process_id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if body.process_name is not None:
        proc.process_name = body.process_name
    if body.line_type is not None:
        proc.line_type = body.line_type
    if body.base_productivity is not None:
        proc.base_productivity = body.base_productivity
    if body.buffer_capacity is not None:
        proc.buffer_capacity = body.buffer_capacity
    if body.display_order is not None:
        proc.display_order = body.display_order
    if body.is_active is not None:
        proc.is_active = 1 if body.is_active else 0
    db.commit()
    db.refresh(proc)
    return proc


@router.delete("/processes/{process_id}", status_code=204)
def delete_process(process_id: str, db: Session = Depends(get_db)):
    proc = db.query(Process).filter(Process.process_id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    db.delete(proc)
    db.commit()


# ─── Process Connections ──────────────────────────────────────────────────────

@router.get("/processes/connections", response_model=List[ProcessConnectionResponse])
def get_connections(db: Session = Depends(get_db)):
    return db.query(ProcessConnection).all()


@router.put("/processes/connections", response_model=List[ProcessConnectionResponse])
def update_connections(body: ProcessConnectionsUpdate, db: Session = Depends(get_db)):
    db.query(ProcessConnection).delete()
    connections = []
    for c in body.connections:
        conn = ProcessConnection(
            connection_id=str(uuid.uuid4()),
            from_process_id=c.from_process_id,
            to_process_id=c.to_process_id,
        )
        db.add(conn)
        connections.append(conn)
    db.commit()
    for c in connections:
        db.refresh(c)
    return connections


# ─── Volume Conversion Rules ──────────────────────────────────────────────────

@router.get("/volume-rules", response_model=List[VolumeConversionRuleResponse])
def get_volume_rules(db: Session = Depends(get_db)):
    return db.query(VolumeConversionRule).all()


@router.put("/volume-rules", response_model=List[VolumeConversionRuleResponse])
def update_volume_rules(body: VolumeConversionRulesUpdate, db: Session = Depends(get_db)):
    db.query(VolumeConversionRule).delete()
    rules = []
    for r in body.rules:
        rule = VolumeConversionRule(
            rule_id=str(uuid.uuid4()),
            source_type=r.source_type,
            process_id=r.process_id,
            conversion_rate=r.conversion_rate,
            unit_description=r.unit_description,
        )
        db.add(rule)
        rules.append(rule)
    db.commit()
    for r in rules:
        db.refresh(r)
    return rules


# ─── Deadline Conditions ──────────────────────────────────────────────────────

@router.get("/conditions/deadlines", response_model=List[ProcessDeadlineConditionResponse])
def get_deadlines(db: Session = Depends(get_db)):
    return db.query(ProcessDeadlineCondition).all()


@router.put("/conditions/deadlines", response_model=List[ProcessDeadlineConditionResponse])
def update_deadlines(body: DeadlineConditionsUpdate, db: Session = Depends(get_db)):
    db.query(ProcessDeadlineCondition).delete()
    deadlines = []
    for d in body.deadlines:
        dl = ProcessDeadlineCondition(
            deadline_id=str(uuid.uuid4()),
            process_id=d.process_id,
            must_finish_by=d.must_finish_by,
            is_active=1 if d.is_active else 0,
        )
        db.add(dl)
        deadlines.append(dl)
    db.commit()
    for d in deadlines:
        db.refresh(d)
    return deadlines


# ─── System Conditions ────────────────────────────────────────────────────────

@router.get("/conditions/system", response_model=List[SystemConditionResponse])
def get_system_conditions(db: Session = Depends(get_db)):
    return db.query(SystemCondition).all()


@router.put("/conditions/system", response_model=List[SystemConditionResponse])
def update_system_conditions(body: SystemConditionsUpdate, db: Session = Depends(get_db)):
    for item in body.conditions:
        cond = db.query(SystemCondition).filter(
            SystemCondition.condition_key == item.condition_key
        ).first()
        if cond:
            cond.condition_value = item.condition_value
            if item.description is not None:
                cond.description = item.description
        else:
            cond = SystemCondition(
                condition_key=item.condition_key,
                condition_value=item.condition_value,
                description=item.description,
            )
            db.add(cond)
    db.commit()
    return db.query(SystemCondition).all()
