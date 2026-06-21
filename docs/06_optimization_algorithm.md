# 倉庫人員配置最適化システム 設計書
## 第6章 最適化アルゴリズム詳細設計

---

### 6.1 アルゴリズム選定根拠

| 観点 | 内容 |
|------|------|
| 規模 | 人員50人×スロット数最大64（15分×16時間）×工程数（最大10程度） |
| 制約 | スキル制約・勤務時間制約・休憩制約・バッファ制約・完了期限制約 |
| 選定 | **優先度付き貪欲法＋局所探索（Greedy + Local Search）** |
| 理由 | 厳密MIPは変数数が多く計算時間が長い（数分〜数十分）ため実用性に欠ける。貪欲法＋局所探索であれば数秒〜30秒以内で良質な解が得られる。 |

---

### 6.2 共通前処理

```python
# 入力データ準備
available_employees = [
    {
        employee_id, name, hourly_wage,
        available_slots: [TIME, ...],   # 出勤可能15分スロット一覧
        overtime_available: bool,
        skills: {process_id: skill_level, ...}
    }
]

required_person_slots = {
    (process_id, time_slot): float  # 必要人員数（小数含む）
}

process_deadlines = {
    process_id: TIME  # 末端工程の完了期限
}

process_chains = [
    [process_id_1, process_id_2, ..., terminal_process_id]
]
```

---

### 6.3 休憩スロットの事前確保

各人員の配置可能スロットから休憩スロットを事前に除外する。

```
【昼休憩の挿入ルール】
1. 各人員の勤務スロット内で 11:30〜13:00 の範囲に60分（4スロット）を割り当てる
2. 個人ごとに開始時刻を11:30〜12:00の間でずらすことで工程の穴を最小化する
   （全員同時に昼休みに入らないよう分散）
3. 割り当てたスロットは「LUNCH_BREAK」として確定し、配置候補から除外する

【法定休憩チェック】
1. 最終的な配置結果で、勤務時間が6時間（360分=24スロット）超の人員をチェック
2. 昼休憩の60分で45分以上を充足しているため、通常は追加不要
3. 昼休憩を取らなかった場合（例：出勤時刻が13:00以降）は別途45分を追加
```

---

### 6.4 案A：最速完了案のアルゴリズム

**目的：** 末端工程の完了時刻を最も早くする

```
Step1: 必要人員を高スキル・低コスト順に並べ替え
  sort_key = (-skill_level, hourly_wage)

Step2: 各スロットに対して前詰めで配置
  for time_slot in all_slots_ascending:
    for process in chains_by_deadline_priority:
      need = required_person_slots[(process, time_slot)]
      assigned = 0
      for employee in sorted_employees:
        if can_assign(employee, process, time_slot):
          assign(employee, process, time_slot)
          assigned += 1
          if assigned >= ceil(need): break

Step3: 完了時刻の評価
  for each terminal_process:
    last_active_slot = max(slot where assigned_count > 0)
    completion_time[process] = last_active_slot + 15min

Step4: 局所探索（完了時刻の改善）
  for iteration in range(MAX_ITER):
    find swap: 空きスロットに別人員を追加配置 → 完了時刻が早まるか確認
    if improvement: apply swap
    else: break
```

---

### 6.5 案B：最低コスト案のアルゴリズム

**目的：** 完了期限制約を守りつつ総人件費を最小化

```
Step1: 案Aの配置を初期解とする

Step2: コスト最小化のための再配置
  for time_slot in all_slots_ascending:
    for process:
      need = required_person_slots[(process, time_slot)]
      
      # 安い人員から優先配置（同スキル内で時給昇順）
      candidates = sorted(available_employees, key=lambda e: effective_wage(e, time_slot))
      
      # effective_wage: 残業スロットなら hourly_wage * 1.2
      
      assigned = 0
      for employee in candidates:
        if can_assign(employee, process, time_slot):
          assign(employee, process, time_slot)
          assigned += 1
          if assigned >= ceil(need): break

Step3: 完了期限の検証
  for each terminal_process:
    if completion_time[process] > deadline[process]:
      # 制約違反 → ペナルティスロットに追加人員を補充してリトライ

Step4: 局所探索（コスト削減）
  for iteration in range(MAX_ITER):
    候補スワップ：高い人 → 安い人 に変えてコスト削減
    if コスト改善 AND 完了期限維持: apply swap
    else: try next swap
```

---

### 6.6 案C：最小移動案のアルゴリズム

**目的：** 完了期限制約を守りつつ人員の工程移動回数を最小化

```
Step1: 案Bの配置を初期解とする

Step2: 工程移動回数のカウント
  for each employee:
    moves[employee] = count_process_switches(assignment_timeline[employee])
    # A→A→B→B→A = スイッチ2回（A→B, B→A）

Step3: 局所探索（移動削減）
  for iteration in range(MAX_ITER):
    # 「飛び地」配置の解消
    find case: employee assigned to [A, A, B, A, A]
              → try: reassign the lonely B-slot to another employee
              → if completion_time maintained AND cost not worsened:
                  apply → moves reduced by 2
    
    # 工程ブロックの連結
    find swap: swap two employees' slots to make longer consecutive blocks
              → if improvement in moves AND deadline/cost maintained:
                  apply swap

Step4: 最終スコア計算
  total_moves = sum(moves[e] for e in all_employees)
```

---

### 6.7 配置可否の判定ロジック（can_assign）

```python
def can_assign(employee, process, time_slot) -> bool:
    # 1. そのスロットがその人員の出勤可能時間内か
    if time_slot not in employee.available_slots:
        return False
    
    # 2. そのスロットがすでに別工程や休憩に割り当て済みでないか
    if time_slot in employee.assigned_slots:
        return False
    
    # 3. スキルがあるか
    if process not in employee.skills:
        return False
    
    # 4. 残業スロットの場合、残業可能か
    if is_overtime_slot(employee, time_slot) and not employee.overtime_available:
        return False
    
    # 5. 残業スロットの場合、残業可能者のみ配置
    #    （残業時間の上限制約は今回なし）
    
    return True

def is_overtime_slot(employee, time_slot) -> bool:
    # 当該時点までの累積労働時間が8時間（480分）を超えているか
    worked_minutes = count_worked_minutes(employee, up_to=time_slot)
    return worked_minutes >= 480
```

---

### 6.8 スコア計算式

```
【完了遵守ペナルティ】
  P_deadline = Σ_{process in terminal_processes}
               max(0, completion_time[process] - deadline[process]) × 10,000
  # 10,000は1分超過あたりのペナルティ係数（総コストに対して圧倒的に大きく設定）

【総人件費】
  C_total = Σ_{employee} (
      normal_minutes[employee] / 60 × hourly_wage[employee]
    + overtime_minutes[employee] / 60 × hourly_wage[employee] × 1.2
  )
  
  normal_minutes   = min(worked_minutes, 480)  # 8時間まで
  overtime_minutes = max(0, worked_minutes - 480)

【工程移動回数】
  M_total = Σ_{employee} count_process_switches(employee)

【案ごとの最適化目標】
  案A: minimize P_deadline → minimize C_total → minimize M_total
  案B: satisfy P_deadline=0 → minimize C_total → minimize M_total
  案C: satisfy P_deadline=0 → minimize M_total → minimize C_total
```

---

### 6.9 バッファ制約の扱い

```
【バッファあり工程の処理タイミング計算】

前工程がスロットTに処理した物量は、スロットT+1以降に後工程へ流入する。
バッファ容量を超えた分は即時処理が必要（待機不可）。

available_for_next[T] = processed[prev][T]
backlog[process][T] = backlog[process][T-1] + available_for_next[T]
  - ただし backlog[process][T-1] ≦ buffer_capacity

actual_required[process][T] = max(0, backlog[process][T] - buffer_capacity)
                            + (new_inflow[process][T] を超えたバッファオーバー分)
```

---

### 6.10 計算時間の目安

| 条件 | 想定計算時間 |
|------|------------|
| 人員20人・工程5・スロット48 | 〜3秒 |
| 人員50人・工程10・スロット64 | 〜15秒 |
| 局所探索MAX_ITER=500の場合 | 上記×2〜3倍 |

> フロントエンドでプログレスバーを表示し、非同期で計算結果を受信する設計とする。

