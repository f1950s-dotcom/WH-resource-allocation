from sqlalchemy import Column, Text, Numeric, Integer
from database import Base


class SkillLevelProductivityRate(Base):
    __tablename__ = "skill_level_productivity_rates"

    skill_level = Column(Integer, primary_key=True)
    productivity_rate = Column(Numeric(5, 3), nullable=False)


class SystemCondition(Base):
    __tablename__ = "system_conditions"

    condition_key = Column(Text, primary_key=True)
    condition_value = Column(Text, nullable=False)
    description = Column(Text)
