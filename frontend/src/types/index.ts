export type LineType = 'INBOUND' | 'OUTBOUND';
export type SlotType = 'WORK' | 'LUNCH_BREAK' | 'LEGAL_BREAK' | 'OFF';
export type ResultType = 'FASTEST' | 'CHEAPEST' | 'LEAST_MOVE';
export type SkillLevel = 1 | 2 | 3;

export interface Employee {
  employee_id: string;
  name: string;
  hourly_wage: number;
  is_active: boolean;
}

export interface EmployeeSkill {
  skill_id: string;
  employee_id: string;
  process_id: string;
  skill_level: SkillLevel;
}

export interface WorkCondition {
  condition_id: string;
  employee_id: string;
  day_of_week: number;
  work_start_time: string;
  work_end_time: string;
  overtime_available: boolean;
  min_work_minutes: number;
}

export interface Process {
  process_id: string;
  process_name: string;
  line_type: LineType;
  base_productivity: number;
  buffer_capacity: number;
  display_order: number;
  is_active: boolean;
}

export interface ProcessConnection {
  connection_id: string;
  from_process_id: string;
  to_process_id: string;
}

export interface VolumeConversionRule {
  rule_id: string;
  source_type: LineType;
  process_id: string;
  conversion_rate: number;
  unit_description: string;
}

export interface DeadlineCondition {
  deadline_id: string;
  process_id: string;
  must_finish_by: string;
  is_active: boolean;
}

export interface VolumePlan {
  volume_plan_id: string;
  plan_date: string;
  volume_type: LineType;
  time_slot_start: string;
  volume: number;
}

export interface VolumeExpansion {
  expansion_id: string;
  plan_date: string;
  process_id: string;
  time_slot_start: string;
  process_volume: number;
  carry_over_volume: number;
  required_person_slots: number;
}

export interface OptimizationResult {
  result_id: string;
  plan_date: string;
  result_type: ResultType;
  total_cost: number;
  total_overtime_cost: number;
  total_process_moves: number;
  is_deadline_met: boolean;
  deadline_violations: Record<string, number> | null;
  calculated_at: string;
  is_selected: boolean;
}

export interface OptimizationAssignment {
  assignment_id: string;
  result_id: string;
  employee_id: string;
  process_id: string | null;
  time_slot_start: string;
  slot_type: SlotType;
  is_overtime: boolean;
  slot_cost: number;
}
