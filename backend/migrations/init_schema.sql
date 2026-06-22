-- 人員基本
CREATE TABLE IF NOT EXISTS employees (
    employee_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    hourly_wage   NUMERIC(8,2) NOT NULL CHECK (hourly_wage > 0),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 工程基本
CREATE TABLE IF NOT EXISTS processes (
    process_id        TEXT PRIMARY KEY,
    process_name      TEXT NOT NULL,
    line_type         TEXT NOT NULL CHECK (line_type IN ('INBOUND','OUTBOUND')),
    base_productivity NUMERIC(10,3) NOT NULL CHECK (base_productivity > 0),
    buffer_capacity   INTEGER NOT NULL DEFAULT 0,
    display_order     INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1
);

-- 人員×工程スキル
CREATE TABLE IF NOT EXISTS employee_process_skills (
    skill_id      TEXT PRIMARY KEY,
    employee_id   TEXT NOT NULL REFERENCES employees(employee_id),
    process_id    TEXT NOT NULL REFERENCES processes(process_id),
    skill_level   INTEGER NOT NULL CHECK (skill_level IN (1, 2, 3)),
    UNIQUE (employee_id, process_id)
);

-- 人員×勤務条件
CREATE TABLE IF NOT EXISTS employee_work_conditions (
    condition_id        TEXT PRIMARY KEY,
    employee_id         TEXT NOT NULL REFERENCES employees(employee_id),
    day_of_week         INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    work_start_time     TEXT NOT NULL,
    work_end_time       TEXT NOT NULL,
    overtime_available  INTEGER NOT NULL DEFAULT 0,
    min_work_minutes    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (employee_id, day_of_week)
);

-- 工程接続
CREATE TABLE IF NOT EXISTS process_connections (
    connection_id   TEXT PRIMARY KEY,
    from_process_id TEXT NOT NULL REFERENCES processes(process_id),
    to_process_id   TEXT NOT NULL REFERENCES processes(process_id),
    UNIQUE (from_process_id, to_process_id)
);

-- 物量変換ルール
CREATE TABLE IF NOT EXISTS volume_conversion_rules (
    rule_id          TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL CHECK (source_type IN ('INBOUND','OUTBOUND')),
    process_id       TEXT NOT NULL REFERENCES processes(process_id),
    conversion_rate  NUMERIC(8,4) NOT NULL CHECK (conversion_rate > 0),
    unit_description TEXT,
    UNIQUE (source_type, process_id)
);

-- 工程完了期限条件
CREATE TABLE IF NOT EXISTS process_deadline_conditions (
    deadline_id    TEXT PRIMARY KEY,
    process_id     TEXT NOT NULL REFERENCES processes(process_id),
    must_finish_by TEXT NOT NULL,
    is_active      INTEGER NOT NULL DEFAULT 1
);

-- 習熟レベル別生産性補正
CREATE TABLE IF NOT EXISTS skill_level_productivity_rates (
    skill_level      INTEGER PRIMARY KEY CHECK (skill_level IN (1, 2, 3)),
    productivity_rate NUMERIC(5,3) NOT NULL CHECK (productivity_rate > 0)
);

-- システム全体条件
CREATE TABLE IF NOT EXISTS system_conditions (
    condition_key   TEXT PRIMARY KEY,
    condition_value TEXT NOT NULL,
    description     TEXT
);

-- 物量計画
CREATE TABLE IF NOT EXISTS volume_plans (
    volume_plan_id  TEXT PRIMARY KEY,
    plan_date       TEXT NOT NULL,
    volume_type     TEXT NOT NULL CHECK (volume_type IN ('INBOUND','OUTBOUND')),
    time_slot_start TEXT NOT NULL,
    volume          NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (plan_date, volume_type, time_slot_start)
);

-- 物量展開結果
CREATE TABLE IF NOT EXISTS volume_expansions (
    expansion_id          TEXT PRIMARY KEY,
    plan_date             TEXT NOT NULL,
    process_id            TEXT NOT NULL REFERENCES processes(process_id),
    time_slot_start       TEXT NOT NULL,
    process_volume        NUMERIC(10,2) NOT NULL DEFAULT 0,
    carry_over_volume     NUMERIC(10,2) NOT NULL DEFAULT 0,
    required_person_slots NUMERIC(8,3) NOT NULL DEFAULT 0,
    calculated_at         TEXT NOT NULL,
    UNIQUE (plan_date, process_id, time_slot_start)
);

-- 最適化結果ヘッダ
CREATE TABLE IF NOT EXISTS optimization_results (
    result_id             TEXT PRIMARY KEY,
    plan_date             TEXT NOT NULL,
    result_type           TEXT NOT NULL CHECK (result_type IN ('FASTEST','CHEAPEST','LEAST_MOVE')),
    total_cost            NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_overtime_cost   NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_process_moves   INTEGER NOT NULL DEFAULT 0,
    is_deadline_met       INTEGER NOT NULL DEFAULT 0,
    deadline_violations   TEXT,
    calculated_at         TEXT NOT NULL,
    is_selected           INTEGER NOT NULL DEFAULT 0,
    patterns_evaluated    INTEGER NOT NULL DEFAULT 0
);

-- 最適化結果明細
CREATE TABLE IF NOT EXISTS optimization_assignments (
    assignment_id   TEXT PRIMARY KEY,
    result_id       TEXT NOT NULL REFERENCES optimization_results(result_id),
    employee_id     TEXT NOT NULL REFERENCES employees(employee_id),
    process_id      TEXT REFERENCES processes(process_id),
    time_slot_start TEXT NOT NULL,
    slot_type       TEXT NOT NULL CHECK (slot_type IN ('WORK','LUNCH_BREAK','LEGAL_BREAK','OFF')),
    is_overtime     INTEGER NOT NULL DEFAULT 0,
    slot_cost       NUMERIC(8,4) NOT NULL DEFAULT 0
);

-- 初期データ
INSERT OR IGNORE INTO skill_level_productivity_rates (skill_level, productivity_rate) VALUES (1, 0.70);
INSERT OR IGNORE INTO skill_level_productivity_rates (skill_level, productivity_rate) VALUES (2, 1.00);
INSERT OR IGNORE INTO skill_level_productivity_rates (skill_level, productivity_rate) VALUES (3, 1.20);

INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) VALUES
    ('overtime_wage_rate', '1.20', '残業割増率'),
    ('overtime_threshold_minutes', '480', '残業開始閾値（分）'),
    ('lunch_break_start', '11:30', '昼休憩開始時刻'),
    ('lunch_break_end', '13:00', '昼休憩終了時刻'),
    ('lunch_break_duration_minutes', '60', '昼休憩時間（分）'),
    ('legal_break_threshold_minutes', '360', '法定休憩が必要な労働時間閾値（分）'),
    ('legal_break_minutes', '45', '法定休憩時間（分）'),
    ('time_slot_minutes', '15', 'タイムスロット単位（分）');
