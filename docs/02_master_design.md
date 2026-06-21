# 倉庫人員配置最適化システム 設計書
## 第2章 マスタ設計

---

### 2.1 人員マスタ（Employee Master）

#### 2.1.1 概要
倉庫で働く人員の属性・スキル・勤務可能条件を管理する。

#### 2.1.2 テーブル定義

**employees（人員基本）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| employee_id | UUID | ○ | 人員ID（PK） |
| name | VARCHAR(100) | ○ | 氏名 |
| hourly_wage | DECIMAL(8,2) | ○ | 通常時給（円） |
| is_active | BOOLEAN | ○ | 有効フラグ |
| created_at | TIMESTAMP | ○ | 作成日時 |
| updated_at | TIMESTAMP | ○ | 更新日時 |

**employee_process_skills（人員×工程スキル）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| skill_id | UUID | ○ | スキルID（PK） |
| employee_id | UUID | ○ | 人員ID（FK） |
| process_id | UUID | ○ | 工程ID（FK） |
| skill_level | TINYINT | ○ | 習熟レベル（1:見習い / 2:一人前 / 3:熟練） |

> スキルレコードが存在しない工程には配置不可。

**employee_work_conditions（人員×勤務条件）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| condition_id | UUID | ○ | 条件ID（PK） |
| employee_id | UUID | ○ | 人員ID（FK） |
| day_of_week | TINYINT | ○ | 曜日（0=日,1=月,...,6=土） |
| work_start_time | TIME | ○ | 出勤可能開始時刻 |
| work_end_time | TIME | ○ | 退勤可能終了時刻（通常） |
| overtime_available | BOOLEAN | ○ | 残業可否 |
| min_work_minutes | INT | ○ | 最低労働時間（分） |

> overtime_available=false の場合、work_end_time を超えた配置は不可。

---

### 2.2 工程マスタ（Process Master）

#### 2.2.1 概要
倉庫内の作業工程とその接続関係・生産性・バッファを管理する。
入庫ライン・出庫ラインは独立したラインとして登録する。

#### 2.2.2 テーブル定義

**processes（工程基本）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| process_id | UUID | ○ | 工程ID（PK） |
| process_name | VARCHAR(100) | ○ | 工程名 |
| line_type | ENUM | ○ | ラインタイプ（INBOUND/OUTBOUND） |
| base_productivity | DECIMAL(10,3) | ○ | 基準生産性（個/人/時間） |
| buffer_capacity | INT | ○ | 工程前バッファ容量（個、0=バッファなし） |
| display_order | INT | ○ | 表示順 |
| is_active | BOOLEAN | ○ | 有効フラグ |

> base_productivity：スキルレベル2（一人前）基準の生産性を設定する。
> スキルレベル補正は条件マスタで定義。

**process_connections（工程接続）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| connection_id | UUID | ○ | 接続ID（PK） |
| from_process_id | UUID | ○ | 前工程ID（FK） |
| to_process_id | UUID | ○ | 後工程ID（FK） |

> 工程チェーン：接続を辿ることで工程の順序を解決する。
> 末端工程（to_process_idに出現しない工程）が「終了時刻制約」の対象となる。

---

### 2.3 物量マスタ（Volume Conversion Master）

#### 2.3.1 概要
入庫量・出庫量を各工程の処理量へ変換するための係数を定義する。

#### 2.3.2 テーブル定義

**volume_conversion_rules（物量変換ルール）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| rule_id | UUID | ○ | ルールID（PK） |
| source_type | ENUM | ○ | 物量種別（INBOUND / OUTBOUND） |
| process_id | UUID | ○ | 対象工程ID（FK） |
| conversion_rate | DECIMAL(8,4) | ○ | 変換係数（例：1.0, 0.3, 2.5） |
| unit_description | VARCHAR(100) | - | 単位補足説明（例：「入庫個数×1.0=検品個数」） |

> 計算式：工程処理量 = 入庫量（または出庫量） × conversion_rate

---

### 2.4 条件マスタ（Condition Master）

#### 2.4.1 概要
最適化計算に必要な各種パラメータを管理する。

#### 2.4.2 テーブル定義

**process_deadline_conditions（工程完了期限条件）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| deadline_id | UUID | ○ | 条件ID（PK） |
| process_id | UUID | ○ | 末端工程ID（FK） |
| must_finish_by | TIME | ○ | 完了しなければならない時刻 |
| is_active | BOOLEAN | ○ | 有効フラグ |

> 末端工程（工程チェーンの最後）に対して設定する。
> 最適化の第1優先制約として使用する。

**skill_level_productivity_rates（習熟レベル別生産性補正）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| skill_level | TINYINT | ○ | 習熟レベル（1/2/3） |
| productivity_rate | DECIMAL(5,3) | ○ | 生産性補正率（例：1=0.70, 2=1.00, 3=1.20） |

> 実生産性 = base_productivity × productivity_rate

**system_conditions（システム全体条件）**

| カラム名 | 型 | 必須 | 説明 |
|---------|-----|------|------|
| condition_key | VARCHAR(50) | ○ | 条件キー（PK） |
| condition_value | VARCHAR(200) | ○ | 条件値 |
| description | VARCHAR(200) | - | 説明 |

> 登録するキーの例：

| condition_key | condition_value | description |
|---------------|-----------------|-------------|
| overtime_wage_rate | 1.20 | 残業時の時給倍率 |
| overtime_threshold_minutes | 480 | 残業開始の閾値（分）、8時間=480分 |
| lunch_break_start | 11:30 | 昼休憩開始可能時刻 |
| lunch_break_end | 13:00 | 昼休憩終了必須時刻 |
| lunch_break_duration_minutes | 60 | 昼休憩時間（分） |
| legal_break_threshold_minutes | 360 | 法定休憩が必要な労働時間閾値（分）、6時間=360分 |
| legal_break_minutes | 45 | 法定休憩時間（分） |
| time_slot_minutes | 15 | 時間粒度（分） |

---

### 2.5 マスタ間の関連図

```
employees ──────────────────────────────────────────┐
    │                                               │
    ├─[1:N]─ employee_process_skills ──[N:1]─ processes
    │                                               │
    └─[1:N]─ employee_work_conditions               ├─[1:N]─ process_connections
                                                    │
                                          volume_conversion_rules
                                                    │
                                         process_deadline_conditions

system_conditions（グローバル設定）
skill_level_productivity_rates（習熟レベル補正テーブル）
```

