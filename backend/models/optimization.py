from sqlalchemy import Column, Text, Numeric, Integer, ForeignKey
from database import Base


class OptimizationResult(Base):
    __tablename__ = "optimization_results"

    result_id = Column(Text, primary_key=True)
    plan_date = Column(Text, nullable=False)
    result_type = Column(Text, nullable=False)
    total_cost = Column(Numeric(12, 2), nullable=False, default=0)
    total_overtime_cost = Column(Numeric(12, 2), nullable=False, default=0)
    total_process_moves = Column(Integer, nullable=False, default=0)
    is_deadline_met = Column(Integer, nullable=False, default=0)
    deadline_violations = Column(Text)
    calculated_at = Column(Text, nullable=False)
    is_selected = Column(Integer, nullable=False, default=0)
    patterns_evaluated = Column(Integer, nullable=False, default=0)
    # 計算エンジン・ソルバーの実行記録（画面に「計算ログ」として表示）
    calculation_method = Column(Text, nullable=False, default="GREEDY")  # GREEDY/ANNEALING/ORTOOLS
    solver_status = Column(Text)        # OPTIMAL / FEASIBLE / HEURISTIC など
    solver_gap = Column(Numeric(6, 4))  # 相対最適性ギャップ（0.0123=1.23%）。ヒューリスティックはNULL
    solve_seconds = Column(Numeric(8, 2))  # 求解にかかった実時間（秒）


class OptimizationAssignment(Base):
    __tablename__ = "optimization_assignments"

    assignment_id = Column(Text, primary_key=True)
    result_id = Column(Text, ForeignKey("optimization_results.result_id"), nullable=False)
    employee_id = Column(Text, ForeignKey("employees.employee_id"), nullable=False)
    process_id = Column(Text, ForeignKey("processes.process_id"), nullable=True)
    time_slot_start = Column(Text, nullable=False)
    slot_type = Column(Text, nullable=False)
    is_overtime = Column(Integer, nullable=False, default=0)
    slot_cost = Column(Numeric(8, 4), nullable=False, default=0)
