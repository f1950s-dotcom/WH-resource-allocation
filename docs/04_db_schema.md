# 倉庫人員配置最適化システム 設計書
## 第4章 データベーススキーマ（ER図・DDL）

---

### 4.1 ER図

```
┌─────────────────┐        ┌──────────────────────────┐
│   employees      │        │  employee_process_skills  │
│─────────────────│        │──────────────────────────│
│ employee_id (PK)│◄──1:N──│ skill_id (PK)            │
│ name            │        │ employee_id (FK)          │──N:1──►┐
│ hourly_wage     │        │ process_id (FK)           │        │
│ is_active       │        │ skill_level               │        │
└─────────────────┘        └──────────────────────────┘        │
        │                                                        │
        │1:N                                             ┌───────▼──────┐
        ▼                                                │   processes   │
┌─────────────────────────┐                             │──────────────│
│ employee_work_conditions│                             │ process_id(PK)│
│─────────────────────────│                             │ process_name  │
│ condition_id (PK)       │                             │ line_type     │
│ employee_id (FK)        │                             │ base_productiv│
│ day_of_week             │                             │ buffer_capacity│
│ work_start_time         │                             │ display_order │
│ work_end_time           │                             │ is_active     │
│ overtime_available      │                             └──────┬────────┘
│ min_work_minutes        │                                    │
└─────────────────────────┘                                    │
                                                               │1:N
                                        ┌──────────────────────▼──────────┐
                                        │      process_connections         │
                                        │─────────────────────────────────│
                                        │ connection_id (PK)              │
                                        │ from_process_id (FK→processes)  │
                                        │ to_process_id (FK→processes)    │
                                        └─────────────────────────────────┘

┌──────────────────────────────┐        ┌──────────────────────────────┐
│   volume_conversion_rules    │        │  process_deadline_conditions  │
│──────────────────────────────│        │──────────────────────────────│
│ rule_id (PK)                 │        │ deadline_id (PK)             │
│ source_type (INBOUND/OUTBOUND│        │ process_id (FK→processes)    │
│ process_id (FK→processes)    │        │ must_finish_by               │
│ conversion_rate              │        │ is_active                    │
│ unit_description             │        └──────────────────────────────┘
└──────────────────────────────┘

┌────────────────────────────┐          ┌──────────────────────────────┐
│      volume_plans          │          │ skill_level_productivity_rates│
│────────────────────────────│          │──────────────────────────────│
│ volume_plan_id (PK)        │          │ skill_level (PK)             │
│ plan_date                  │          │ productivity_rate            │
│ volume_type                │          └──────────────────────────────┘
│ time_slot_start            │
│ volume                     │          ┌──────────────────────────────┐
└────────────────────────────┘          │      system_conditions       │
                                        │──────────────────────────────│
┌────────────────────────────┐          │ condition_key (PK)           │
│     volume_expansions      │          │ condition_value              │
│────────────────────────────│          │ description                  │
│ expansion_id (PK)          │          └──────────────────────────────┘
│ plan_date                  │
│ process_id (FK→processes)  │
│ time_slot_start            │
│ process_volume             │
│ carry_over_volume          │
│ required_person_slots      │
│ calculated_at              │
└────────────────────────────┘

┌────────────────────────────┐          ┌─────────────────────────────────┐
│   optimization_results     │          │    optimization_assignments      │
│────────────────────────────│          │─────────────────────────────────│
│ result_id (PK)             │◄──1:N────│ assignment_id (PK)              │
│ plan_date                  │          │ result_id (FK)                  │
│ result_type                │          │ employee_id (FK→employees)      │
│ total_cost                 │          │ process_id (FK→processes, NULL) │
│ total_overtime_cost        │          │ time_slot_start                 │
│ total_process_moves        │          │ slot_type (WORK/LUNCH/LEGAL)    │
│ is_deadline_met            │          │ is_overtime                     │
│ deadline_violations (JSON) │          │ slot_cost                       │
│ calculated_at              │          └─────────────────────────────────┘
│ is_selected                │
└────────────────────────────┘
```

---

### 4.2 DDL（SQLite / PostgreSQL 互換）

```sql
-- 人員基本
CREATE TABLE employees (
    employee_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    hourly_wage   NUMERIC(8,2) NOT NULL CHECK (hourly_wage > 0),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- 人員×工程スキル
CREATE TABLE employee_process_skills (
    skill_id      TEXT PRIMARY KEY,
    employee_id   TEXT NOT NULL REFERENCES employees(employee_id),
    process_id    TEXT NOT NULL REFERENCES processes(process_id),
    skill_level   INTEGER NOT NULL CHECK (skill_level IN (1, 2, 3)),
    UNIQUE (employee_id, process_id)
);

-- 人員×勤務条件
CREATE TABLE employee_work_conditions (
    condition_id        TEXT PRIMARY KEY,
    employee_id         TEXT NOT NULL REFERENCES employees(employee_id),
    day_of_week         INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    work_start_time     TEXT NOT NULL,
    work_end_time       TEXT NOT NULL,
    overtime_available  INTEGER NOT NULL DEFAULT 0,
    min_work_minutes    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (employee_id, day_of_week)
);

-- 工程基本
CREATE TABLE processes (
    process_id        TEXT PRIMARY KEY,
    process_name      TEXT NOT NULL,
    line_type         TEXT NOT NULL CHECK (line_type IN ('INBOUND','OUTBOUND')),
    base_productivity NUMERIC(10,3) NOT NULL CHECK (base_productivity > 0),
    buffer_capacity   INTEGER NOT NULL DEFAULT 0,
    display_order     INTEGER NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1
);

-- 工程接続
CREATE TABLE process_connections (
    connection_id   TEXT PRIMARY KEY,
    from_process_id TEXT NOT NULL REFERENCES processes(process_id),
    to_process_id   TEXT NOT NULL REFERENCES processes(process_id),
    UNIQUE (from_process_id, to_process_id)
);

-- 物量変換ルール
CREATE TABLE volume_conversion_rules (
    rule_id          TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL CHECK (source_type IN ('INBOUND','OUTBOUND')),
    process_id       TEXT NOT NULL REFERENCES processes(process_id),
    conversion_rate  NUMERIC(8,4) NOT NULL CHECK (conversion_rate > 0),
    unit_description TEXT,
    UNIQUE (source_type, process_id)
);

-- 工程完了期限条件
CREATE TABLE process_deadline_conditions (
    deadline_id    TEXT PRIMARY KEY,
    process_id     TEXT NOT NULL REFERENCES processes(process_id),
    must_finish_by TEXT NOT NULL,
    is_active      INTEGER NOT NULL DEFAULT 1
);

-- 習熟レベル別生産性補正
CREATE TABLE skill_level_productivity_rates (
    skill_level      INTEGER PRIMARY KEY CHECK (skill_level IN (1, 2, 3)),
    productivity_rate NUMERIC(5,3) NOT NULL CHECK (productivity_rate > 0)
);

-- システム全体条件
CREATE TABLE system_conditions (
    condition_key   TEXT PRIMARY KEY,
    condition_value TEXT NOT NULL,
    description     TEXT
);

-- 物量計画
CREATE TABLE volume_plans (
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
CREATE TABLE volume_expansions (
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
CREATE TABLE optimization_results (
    result_id           TEXT PRIMARY KEY,
    plan_date           TEXT NOT NULL,
    result_type         TEXT NOT NULL CHECK (result_type IN ('FASTEST','CHEAPEST','LEAST_MOVE')),
    total_cost          NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_overtime_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_process_moves INTEGER NOT NULL DEFAULT 0,
    is_deadline_met     INTEGER NOT NULL DEFAULT 0,
    deadline_violations TEXT,
    calculated_at       TEXT NOT NULL,
    is_selected         INTEGER NOT NULL DEFAULT 0
);

-- 最適化結果明細（配置）
CREATE TABLE optimization_assignments (
    assignment_id   TEXT PRIMARY KEY,
    result_id       TEXT NOT NULL REFERENCES optimization_results(result_id),
    employee_id     TEXT NOT NULL REFERENCES employees(employee_id),
    process_id      TEXT REFERENCES processes(process_id),
    time_slot_start TEXT NOT NULL,
    slot_type       TEXT NOT NULL CHECK (slot_type IN ('WORK','LUNCH_BREAK','LEGAL_BREAK','OFF')),
    is_overtime     INTEGER NOT NULL DEFAULT 0,
    slot_cost       NUMERIC(8,2) NOT NULL DEFAULT 0
);

-- インデックス
CREATE INDEX idx_volume_plans_date ON volume_plans(plan_date);
CREATE INDEX idx_volume_expansions_date ON volume_expansions(plan_date);
CREATE INDEX idx_opt_results_date ON optimization_results(plan_date);
CREATE INDEX idx_opt_assignments_result ON optimization_assignments(result_id);
CREATE INDEX idx_opt_assignments_employee ON optimization_assignments(employee_id);
```

---

### 4.3 初期データ（system_conditionsのシード）

```sql
INSERT INTO system_conditions VALUES
('overtime_wage_rate',           '1.20',  '残業時の時給倍率'),
('overtime_threshold_minutes',   '480',   '残業閾値（分）'),
('lunch_break_start',            '11:30', '昼休憩開始可能時刻'),
('lunch_break_end',              '13:00', '昼休憩終了必須時刻'),
('lunch_break_duration_minutes', '60',    '昼休憩時間（分）'),
('legal_break_threshold_minutes','360',   '法定休憩が必要な労働時間閾値（分）'),
('legal_break_minutes',          '45',    '法定休憩時間（分）'),
('time_slot_minutes',            '15',    '時間粒度（分）');

INSERT INTO skill_level_productivity_rates VALUES
(1, 0.70),
(2, 1.00),
(3, 1.20);
```

