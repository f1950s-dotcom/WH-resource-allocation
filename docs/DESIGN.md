# 倉庫 人員配置最適化システム 設計書

> 別のエージェント／開発者がゼロから再構築できることを目的とした設計仕様。
> 本書だけで「何を・なぜ・どう作るか」が追えるように、業務要件・データモデル・
> 最適化アルゴリズム・API・画面・設計判断（教訓）を網羅する。

---

## 1. システムの目的

倉庫の1日分の作業（入庫・出庫）について、**時間帯ごとの物量**と**従業員のスキル・勤務条件**を
入力として、**「誰を・いつ・どの工程に配置するか」を自動で最適化**する。目的は次の2案を提示すること。

- **最速案（FASTEST）**：締切内に作業を終えることを最優先し、完了を早める配置。
- **最低コスト案（CHEAPEST）**：締切を満たしつつ人件費を最小化する配置。

いずれも「当日の作業を必ず終わらせる」ことを最優先とし、足りなければ残業、それでも足りなければ
作業残（未処理）を最小化する、という優先順位で解く（第6章）。

---

## 2. 全体アーキテクチャ

クライアント・サーバー構成。**重い計算はすべてバックエンドで行う**。

```
┌─────────────┐    HTTP/JSON    ┌──────────────────────────────┐
│ フロントエンド    │ ─────────────▶ │ バックエンド (FastAPI / Python)      │
│ React + Vite   │ ◀───────────── │  ├ routers/  … REST API          │
│ (ブラウザで動作)  │                 │  ├ services/optimizer/ … 最適化本体 │
└─────────────┘                 │  ├ services/ … 物量展開・シフト生成    │
                                │  └ models/ … SQLAlchemy ORM       │
                                │        ↓                          │
                                │   SQLite (warehouse.db)           │
                                │        ↑                          │
                                │  MIP求解は子プロセスに隔離 (fork)     │
                                └──────────────────────────────┘
```

- **計算はバックエンドが動くマシンのCPU/RAMを使う**（ローカル実行ならPC、Render実行ならRenderのコンテナ）。
- 本番ではフロントをビルドし、FastAPIが静的配信する（単一プロセスで完結）。

---

## 3. 技術スタック

| 層 | 採用技術 |
|---|---|
| バックエンド | Python 3.11+, FastAPI 0.115, Uvicorn, SQLAlchemy 2.0, Pydantic 2.9 |
| 最適化 | Google OR-Tools 9.11（`pywraplp` の **CBC** ソルバーを使用。CP-SATではない） |
| Excel出力 | openpyxl 3.1 |
| DB | SQLite（ファイルベース。`DATABASE_URL` で差し替え可） |
| フロントエンド | React + TypeScript + Vite + Tailwind CSS, React Query, React Router |

**CBCを使う理由**：処理量を連続量（NumVar）で扱う混合整数計画のため CP-SAT（整数専用）ではなく
線形緩和に強い CBC が適している（第6章のMcCormick緩和と併せて）。

---

## 4. データモデル（DBスキーマ）

すべて `backend/models/*.py` に SQLAlchemy で定義。主キーは基本 UUID 文字列、時刻は `"HH:MM"`、
日付は `"YYYY-MM-DD"` の文字列で保持する。

### 4-1. マスタ系

| テーブル | 主な列 | 意味 |
|---|---|---|
| `employees` | employee_id, name, hourly_wage, is_active | 従業員。時給は人件費計算の基礎 |
| `employee_process_skills` | employee_id, process_id, skill_level(1-3) | 誰がどの工程を、どの習熟レベルでできるか |
| `employee_work_conditions` | employee_id, **day_of_week(0=月…6=日)**, work_start_time, work_end_time, overtime_available, min_work_minutes | **曜日別**の勤務条件。※曜日規約は第9章の教訓を参照 |
| `processes` | process_id, process_name, line_type(INBOUND/OUTBOUND), base_productivity(個/人時), buffer_capacity, display_order | 工程マスタ。生産性＝標準1人時あたり処理個数 |
| `process_connections` | from_process_id, to_process_id | 工程の前後関係（有向グラフ。上流→下流） |
| `volume_conversion_rules` | source_type(INBOUND/OUTBOUND), process_id, conversion_rate | 入出庫物量→各工程の物量への換算率 |
| `process_deadline_conditions` | process_id, must_finish_by("HH:MM") | 工程の完了期限（**ソフト**。第6章） |
| `skill_level_productivity_rates` | skill_level, productivity_rate | 習熟レベル→生産性倍率（1:0.8, 2:1.0, 3:1.2） |
| `system_conditions` | condition_key, condition_value | 全体パラメータのkey-valueストア（第10章） |

### 4-2. トランザクション系

| テーブル | 主な列 | 意味 |
|---|---|---|
| `volume_plans` | plan_date, volume_type, time_slot_start, volume | 対象日・時間帯ごとの入出庫物量（入力） |
| `volume_expansions` | plan_date, process_id, time_slot_start, process_volume, carry_over_volume, required_person_slots | 物量を工程別に展開した中間結果（自動生成） |
| `optimization_results` | result_id, plan_date, result_type(FASTEST/CHEAPEST), total_cost, total_overtime_cost, total_process_moves, is_deadline_met, deadline_violations, calculation_method, solver_status, solver_gap, solve_seconds, process_moves_before_repair, completion_time, available_headcount, assigned_headcount, total_work_hours, total_unprocessed | 最適化結果のサマリ＋計算ログ |
| `optimization_assignments` | result_id, employee_id, process_id(NULL可), time_slot_start, slot_type(WORK/LUNCH/BREAK), is_overtime, slot_cost | 配置の明細（1人×1スロット×1行） |

---

## 5. 処理フロー（業務ロジック）

```
① 物量登録        volume_plans に時間帯別の入出庫物量を入力
      ↓
② 物量展開        expand_volume(): 換算率で各工程の process_volume を算出
   (services/volume_expansion.py)         → volume_expansions
      ↓
③ 最適化          FastestOptimizer / CheapestOptimizer を並列実行
   (services/optimizer/*)                 → optimization_results / _assignments
      ↓
④ シフト表示       build_shift_data(): 配置を再シミュレートしガント/ヒートマップ表示
   (services/shift_generator.py, flow_report.py)
```

**重要**：③の直前で②を必ず再実行する（`_run_optimization`）。物量登録を変えても展開が
古いままだと「最適化は旧物量／シフト画面は新物量」で残務が出る不整合が起きるため。

---

## 6. 最適化エンジン設計（中核）

`backend/services/optimizer/` に実装。`BaseOptimizer` を `FastestOptimizer` / `CheapestOptimizer`
が継承。`least_move.py` は廃止済み（結果があれば起動時に除去）。

### 6-1. 時間・スロットモデル

- 1日を **15分スロット**に分割（`slot_minutes=15`）。
- 各従業員の配置可能スロットは勤務条件から生成。`overtime_available` なら `work_end_time` を
  `overtime_max_end_time`(既定20:00)まで延長。
- 昼休み（既定11:30-13:00 60分）と法定休憩を `_assign_lunch_breaks` で LUNCH/BREAK スロットとして確保。
- **当日の勤務条件がある従業員だけ**が配置候補（`active_employees`）。土日など条件が無ければ0人＝配置なし。

### 6-2. 2案 × 3計算手法

- **案（result_type）**：`FASTEST`（完了時刻最優先）／`CHEAPEST`（コスト最小）。
- **計算手法（calculation_method）**：`GREEDY`（貪欲＋局所改善）／`ANNEALING`／`ORTOOLS`。
  - **ANNEALING と ORTOOLS は内部で同一のMIP（CBC）を解く**。差は求解失敗時のフォールバック挙動のみ。
  - `GREEDY` はMIPを使わずヒューリスティックのみ（高速・近似）。

### 6-3. MIP定式化（`mip.py`）

**決定変数**
- `x[e,p,s] ∈ {0,1}`：従業員eがスロットsで工程pを担当（スキルのある(e,p)・稼働可能sのみ生成）。
- `proc[p,t] ≥ 0`：工程pが時刻tに処理する量（連続量）。
- `short_p ≥ 0`：工程pの当日未処理量（作業残）。**ソフト変数**。
- `pen[e,p,t]`：工程移動ペナルティ用（McCormick緩和で線形化）。
- `n[e], ot[e]`：従業員eの総勤務スロット数・残業スロット数。

**主な制約**
- 各(e,s)で高々1工程（`Σ_p x ≤ 1`）。稼働不可スロットは0。
- `proc[p,t] ≤` 配置人数×生産性×スキル率×（1−工程移動ペナルティ）。生産性は
  `base_productivity × skill_rate × transition_factor`。
- 在庫収支：`到着量（上流のproc累積＋初期物量）− proc累積 ≥ 0`、バッファ上限。
- `short_p = 当日総需要 − Σ_t proc[p,t]`（処理しきれなかった分）。

**目的関数（案ごとに重み付けで優先順位を表現）**
- 例（FASTEST/MAKESPAN系）：`Minimize( cost + 1e3·sum_late + 1e5·sum_short )`
- 例（CHEAPEST系）：`Minimize( cost + 1e5·sum_short )`
- 優先順位＝**作業残(short) ≫ 締切超過(late) ≫ 残業割増 ≫ 通常コスト**。
  重みは桁で階層化（`1e5`〜`1e8`）。※桁を上げ過ぎるとCBCの数値精度が落ち NOT_SOLVED に
  なるため、`sum_short` の重みは慎重に調整。

**設計上の要点（教訓の反映）**
- **締切はハード制約にしない**。`must_finish_by` 超過は `sum_late` ペナルティで表現（ソフト）。
  ハードにすると残業枠が空いていても最終工程を諦め残務を残す／INFEASIBLEになる。
- **工程移動ペナルティは big-M でなく McCormick 緩和**で線形化。big-Mは組合せ爆発でCBCが
  時間制限を無視して暴走・数値例外を起こしたため。
- **空配置（全x=0, short=全量）は常に実行可能**＝モデルは基本INFEASIBLEにならない設計。

### 6-4. 制限時間と規模適応

- 内部制限時間 `_adaptive_time_limit(n) = clamp(60 + 整数変数数/40, 60, 600)` 秒。
  - 旧式 `5 + n/150` は現実規模で数十秒にしかならず、上限を上げても無意味だった（教訓）。
- 早期終了は相対ギャップ（ratioGap 1%）で判定。
- 上限600秒 **<** ハード強制終了700秒（次項）。

### 6-5. プロセス隔離（`solve_mip_isolated`）

CBCは厳しいモデルで **(1)SetTimeLimitを無視して暴走、(2)C++層でクラッシュ**（Pythonで捕捉不能）
することがある。対策として **MIP求解を使い捨ての子プロセス(fork)に隔離**し、親が

- `hard_timeout_sec`（既定700秒）を超えたら**強制終了**して `None`（=フォールバック）を返す。
- 子がクラッシュしても親は生存。`last_solve_meta` に `TIMEOUT_KILLED` / `SOLVER_CRASHED` を記録。

`None` が返ったら `run()` はヒューリスティック（GREEDY相当）にフォールバックし、`solver_status`
は簡易計算系の値になる（画面に「簡易計算」と表示）。

### 6-6. 連続化リペア（`_repair_continuity`）— 後処理

MIP解は「15分ごとに工程が細切れに変わる」非現実的な配置になりがち。**ハード制約で縛らず**、
求解後に配置を組み替えて工程切替を減らす。3フェーズ構成：

- **フェーズ1**：同一スロット内で2人の担当工程を入れ替え（切替が減る場合）。習熟度差で
  **当日総未処理量が悪化したらフェーズ1を丸ごと取り消す**（オールオアナッシングの安全策）。
- **フェーズ2**：1人の担当を直前スロットと同じ工程へ付け替え。工程別人数（＝処理量）は変わるが
  **未処理量・締切が悪化しない場合のみ採用**。本人の勤務スロットは不変なので**コスト不変**。
- **フェーズ3**：**コスト許容枠つき**の席入れ替え。切替を起こす席を、その工程に連続で就ける
  別の人へ入れ替える。工程別人数は維持（処理量ほぼ不変）だが担当が変わり**コストが動く**。
  `未処理量・締切が悪化しない AND 総コスト増が repair_cost_budget_rate 以内`のときのみ採用。
  `0` なら無効（従来のコスト不変挙動）。

### 6-7. フロー・シミュレーション（`_run_flow` / `_simulate_fixed`）

配置を固定して工程グラフ上で在庫を前進させ、各工程・各スロットの実効処理量、総未処理量
（`_flow_backlog_fixed`）、完了時刻（`_completion_time`）を算出する。スコアリング・リペアの
採否判定・結果保存に共通で使う。

### 6-8. 並列実行（`routers/optimize.py::_run_optimization`）

- 物量展開・旧結果の除去を1セッションで実施後、**FASTEST と CHEAPEST を別スレッドで並列実行**
  （各スレッドが専用のDBセッションを持つ）。両スレッドの join で完了。
- 2案は独立（別サブプロセス・別700秒タイマー・別セッション）。**一方が他方を打ち切ることはない**。
- SQLiteの並行コミット競合に備え、接続に `timeout=30` を設定。
- **注意（CPU制約環境）**：CBCの制限時間は壁時計基準。CPUが絞られた環境（例：Render無料）で
  並列に走らせると各ソルバーの実計算量が半減し品質低下・簡易計算転落の恐れ。多コアなら有効。

---

## 7. API仕様（抜粋）

すべて `/api` プレフィクス想定。主要エンドポイント：

| メソッド/パス | 用途 |
|---|---|
| GET/POST/PUT/DELETE `/employees...` | 従業員・スキル・勤務条件のCRUD |
| GET/POST/PUT `/processes...`, `/processes/connections` | 工程・工程接続のCRUD |
| GET/PUT `/volume-rules`, `/conditions/deadlines`, `/conditions/system` | 換算率・締切・システム条件 |
| GET/PUT `/volume-plans/{date}` | 対象日の物量登録 |
| POST `/volume-plans/{date}/expand`, GET `/volume-expansions/{date}` | 物量展開の実行・取得 |
| POST `/optimize/{date}` | 最適化をバックグラウンド起動（`?method=GREEDY/ANNEALING/ORTOOLS`） |
| GET `/optimize/{date}/status` | 実行中フラグ（フロントがポーリング） |
| GET `/optimize/{date}/results`, `/results/{id}` | 結果サマリ・明細 |
| POST `/optimize/{date}/results/{id}/select` | 採用案の選択 |
| GET `/shifts/{date}`, `/shifts/{date}/flow`, `/shifts/{date}/export` | シフト表示・フロー・Excel出力 |

最適化は `BackgroundTasks` + `_running[date]` フラグで非同期実行し、フロントは status をポーリング。

---

## 8. フロントエンド構成

| 画面 | ファイル | 役割 |
|---|---|---|
| ホーム | pages/Home.tsx | 日付選択・全体導線 |
| 物量登録 | pages/VolumePlan.tsx | 入庫/出庫タブで時間帯別物量を入力・一括保存・CSV取込 |
| 物量展開 | pages/VolumeExpansion.tsx | 展開結果の確認 |
| 最適化 | pages/Optimization.tsx | 実行・エンジン別に結果カード比較・計算ログ表示 |
| 最適化詳細 | pages/OptimizationDetail.tsx | ガント/ヒートマップ/稼働率 |
| シフト | pages/Shift.tsx | 採用案のシフト表・Excel出力 |
| マスタ各種 | pages/master/*.tsx | 従業員・工程・接続・換算率・締切・システム条件 |

- 状態管理は React Query（APIキャッシュ）。日付の初期値は **JST**（`toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'})`）。
- 曜日ラベルは **月始まり**（`['月','火','水','木','金','土','日']`）＝バックエンドの `weekday()` と一致。

---

## 9. 設計上の重要判断・教訓（再構築時に必ず踏襲）

1. **ハード制約より重み付け（ソフト化）**：締切・最低連続配置などをハード制約にするとCBCが
   暴走・INFEASIBLE化。ペナルティ項＋桁階層で優先順位を表現し、後処理（リペア）で整える。
2. **外部ソルバーは隔離して監視**：CBCは制限時間無視・クラッシュがある前提で、子プロセス隔離＋
   親からの強制終了＋フォールバックを必ず用意する。
3. **「効いているパラメータ」を実測で確認**：時間の実効上限は計算式が支配し、クランプ上限は
   ほぼ効かない。数字を上げる前に実効値を確認する。
4. **規約（曜日・時刻・単位）のズレを最優先で疑う**：
   - 曜日：フロントは月始まり＝Python `weekday()`(月=0) に統一（JSの日=0と混ぜない）。
   - 日付：初期値・判定は **JST** で統一（UTCの `toISOString()` は使わない）。
5. **分母はマスタ確定値で固定**：出社可能人数などの集計は、最適化の途中で変化する配列
   （帰宅処理で縮む `active_employees` 等）から数えず、マスタ由来の確定値を使う。
6. **選定は単価でなく「処理1個あたりコスト」**：低時給＝低生産性のことがあり、時給順で選ぶと
   かえって高コスト・低速になる。コスト/処理量で評価する。
7. **ドキュメントも“テスト対象”**：マニュアルの記述と実装挙動は乖離しやすい。挙動を変えたら
   マニュアル（`docs/user_guide.html`）とGitHub Pagesの同期も忘れない。

---

## 10. 主要システム条件（`system_conditions`）

| key | 既定 | 意味 |
|---|---|---|
| overtime_wage_rate | 1.20 | 残業割増率 |
| overtime_threshold_minutes | 480 | 残業扱いになる勤務分数(=8h) |
| overtime_max_end_time | 20:00 | 残業可能者の最大終了時刻 |
| lunch_break_start / _end / _duration_minutes | 11:30 / 13:00 / 60 | 昼休み |
| legal_break_threshold_minutes / _minutes | 360 / 45 | 法定休憩 |
| process_transition_penalty_enabled / _rate | 1 / 0.30 | 工程移動ペナルティ |
| min_work_minutes | 0 | これ未満しか働けない人は配置しない(0=無効) |
| min_process_assignment_minutes | 60 | 1工程の最低連続配置(目安。完了時は不適用) |
| **repair_cost_budget_rate** | 0.03 | 連続化リペアで切替削減に許容する総コスト増率(0=不許可) |

習熟レベル→生産性：`skill_level_productivity_rates`（1:0.8 / 2:1.0 / 3:1.2）。

---

## 11. デプロイ・運用

- **ローカル**：`start.bat`（Uvicorn を localhost:8000 で起動）。計算はPCのCPUを使用。
- **Render**：バックエンドをコンテナで起動、フロントは静的配信。計算はRenderのCPUを使用
  （ローカルCPUは使わない）。**無料プランはCPU/RAM(512MB)が弱く、SQLiteは再起動で揮発**。
  永続化が必要ならボリューム付きホスト（Fly.io等）や外部DB（Neon等）へ。
- **アクセス**：公開URLは**利用者側のアカウント不要**。ただし認証は無いため、機微データを扱うなら
  前段に簡易認証（Cloudflare Access等）を検討。
- **DB初期化**：`database.py::init_db()` がテーブル作成＋既定システム条件を `INSERT OR IGNORE`。
  初期データは `backend/migrations/seed_data.sql`。

---

## 12. 再構築ステップ（推奨順）

1. **DBスキーマ**（第4章）を SQLAlchemy で定義し、`init_db()` と seed を用意。
2. **マスタCRUD API**（従業員/工程/接続/換算率/締切/システム条件）。
3. **物量登録 + 物量展開**（`expand_volume`）。工程グラフに沿った換算・展開を先に固める。
4. **フロー・シミュレーション**（配置→在庫前進→未処理量/完了時刻）。最適化前に単体で正しく。
5. **MIP定式化**（第6-3）。まずソフト制約と空配置=実行可能を担保し、INFEASIBLEを排除。
6. **プロセス隔離＋フォールバック**（第6-5）。暴走・クラッシュ耐性を最初から入れる。
7. **連続化リペア**（第6-6）を3フェーズで追加。
8. **並列実行**（第6-8）と結果保存・計算ログ。
9. **フロントエンド**（第8章）。日付=JST・曜日=月始まりを最初から徹底。
10. **教訓（第9章）を各所でレビュー**。特にハード制約回避・規約統一・分母固定。

---

---

## 13. 修正履歴・最終結論・落とし穴（★最重要）

> 本章は「作り直すと**再び同じ試行錯誤に陥る**」箇所の、**最終的な決着（値・式）**と
> **二度と踏まないための注意**をまとめたもの。再構築時は本章を先に読むこと。
> 各行は `症状 → 原因 → 最終結論 → 再発防止` で読む。

### 13-1. 最適化の定式化まわり

| # | 症状（当初） | 原因 | 最終結論（採用した形） | 再発防止 |
|---|---|---|---|---|
| 1 | 重い日に全案が「簡易計算」に落ちる | 「全量処理」を**ハード制約**(`cum_proc ≥ cum_arr`)にしていて、容量が厳しい日に**INFEASIBLE** | **未処理 `short_p ≥ 0` を許容し目的関数で重罰**（ソフト化）。空配置=常に実行可能に | 「必ず終わる」は制約でなく**ペナルティ**で表す。ヒューリスティックが解ける問題はMIPも解けるようにする |
| 2 | 「1工程に最低◯分連続配置」を入れるとCBCが**暴走/クラッシュ**、全案簡易計算 | 最低連続配置のハード制約が整数変数の**組合せ爆発** | **MIPに入れない**。求解後の**連続化リペア**（第6-6）で細切れ切替を後処理で解消 | 連続性・整数的な塊制約は**後処理**へ。MIP本体は緩和の強い形に保つ |
| 3 | 残業枠(17-20時)が空いても最終工程を諦め**残務**を残す | 締切を「以降は処理=0」の**ハード打ち切り**にしていた | 締切は**ソフト**。`late`ペナルティ＋優先順位 **残務 ≫ 締切後処理 ≫ 残業割増 ≫ 通常コスト** | 締切はKPI表示に使い、処理可否は**各人のavailableスロット**(残業可否反映)に委ねる |
| 4 | 最速案がmakespanを最小化しない | big-M型の「最遅スロット」最小化は**緩和が弱くNOT_SOLVED**。終了時刻重み付き総和も代理にならず | **在庫時間（各時刻の滞留量 `cum_arr−cum_proc` の総和）を最小化**。連続変数のみで高速 | makespanは**滞留総和**で代理。big-M最遅スロットは使わない |
| 5 | 未処理ペナルティを上げると**NOT_SOLVED** | 係数が大きすぎ**CBCの数値精度が悪化** | 目的別に**必要最小限の桁**：COST=`1e3·late + 1e5·short`／MAKESPAN=`1e8·short` | 重みは「その目的の最大スケールを上回る**最小限**」。無闇に桁を上げない |

### 13-2. ソルバー運用・性能まわり

| # | 症状 | 原因 | 最終結論 | 再発防止 |
|---|---|---|---|---|
| 6 | 本体プロセスごと落ちる／固まる | CBCが**SetTimeLimitを無視して暴走**・**C++層でクラッシュ**（Pythonで捕捉不能） | **求解を子プロセス(fork)に隔離**、親が**700秒で強制終了**→`None`→簡易計算フォールバック | 外部ソルバーは「制限無視・クラッシュ前提」で**隔離＋監視**する |
| 7 | 時間上限を300→600秒に上げても**簡易計算のまま** | 実効上限は式 `5 + n/150` が支配し、現実規模で**数十秒**。クランプ上限はほぼ**発動しない** | **式そのものを引き上げ**：`clamp(60 + n/40, 60, 600)`秒（例:5千変数→185秒） | 「上限」より**実効値**を実測で確認してから調整する |
| 8 | （並列化後）品質が落ちる懸念 | CBCの制限時間は**壁時計基準**。CPUが絞られた環境で並列だと各ソルバーの実計算量が半減 | 2案は**独立スレッド＋独立DBセッション＋独立700秒タイマー**で並列。SQLiteは`timeout=30`。**多コアなら有効／CPU制約環境では逐次が無難** | 並列はコア数に依存。Render無料等では逐次化も選択肢。**一方が他方を打ち切らない**設計を維持 |
| 9 | 連続化リペアで切替が減りきらない | リペアが**コストを一切動かさない**設計で、担当者を替えられなかった | **フェーズ3（コスト許容枠つき席入替）**を追加。`repair_cost_budget_rate`(既定0.03)以内で担当変更可。**習熟度均一は不要** | 「コスト不変」は安全策。緩めるなら**枠をシステム条件で明示**し、処理量・締切の非悪化は維持 |

### 13-3. 集計・規約・UIまわり（静かに壊れる系）

| # | 症状 | 原因 | 最終結論 | 再発防止 |
|---|---|---|---|---|
| 10 | 出社可能人数が計算手法で**バラつく** | 帰宅処理で縮む `active_employees` から人数を数えていた | **マスタ確定値**（その日の勤務条件を持つ人数 `available_headcount`）で固定 | 集計の分母は**最適化途中で変化しない確定値**を使う |
| 11 | 最低コスト案が最速案より**高コスト** | 「時給の安い順」で選び、低時給＝**低生産性**を多投入 | 選定は**処理1個あたりコスト**（コスト/生産性）で評価 | 単価でなく**単位あたりコスト**で比較する |
| 12 | 曜日が**1日ズレて**表示（月〜金が日〜木に見える） | フロント=**日曜0始まり(JS)**、バック=**月曜0始まり(Python `weekday()`)** の規約不一致 | フロントのラベルを**月始まり** `['月'..'日']` に統一（保存番号は不変・移行不要） | 曜日は**月=0(Python)**に統一。JSの`getDay()`(日=0)と混ぜない |
| 13 | 早朝に**前日**が初期表示 | 「今日」を**UTC**(`toISOString()`)で計算 | **JST**で計算 `toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'})` | 日付の初期値・判定は**JST**で統一。`toISOString().slice(0,10)`は使わない |
| 14 | 土日を指定すると**何も出ない**ように見える | その曜日に勤務条件のある人が**0人**（空結果が保存される） | 挙動は正常。最適化画面に**「配置できる従業員がいない」バナー**を表示 | 「候補0人」は**明示メッセージ**を出す。土日稼働は勤務条件の追加が前提 |

---

## 14. 実装仕様 付録（ほぼ同一再現のための式・定数）

> 第13章の「最終結論」を、再現に必要な粒度で式・定数として固定する。
> 値は実装（`mip.py` / `base.py` / `volume_expansion.py`）と一致させて保守すること。

### 14-1. 物量展開（`expand_volume`）

- 展開対象は**根元工程のみ**（`process_connections` の下流側になっていない工程）。
- `process_volume = 登録物量 × conversion_rate`（`rule.source_type == plan.volume_type` の工程だけ）。
- **キャリーオーバーは行わない**（`carry_over_volume=0`, `required_person_slots=0`）。
  下流工程は「いつ作業が発生するか」が配置依存のため展開せず、**最適化のフロー制約**（到着量 `arrived_expr`）で
  上流の処理結果が下流に流れる形で表現する。
- 対象日の既存 `volume_expansions` は毎回**全削除→再生成**。

### 14-2. 案と目的タイプの対応

| 案 (RESULT_TYPE) | 呼び出す objective_type |
|---|---|
| FASTEST | `MAKESPAN` |
| CHEAPEST | `COST` |

### 14-3. MIP 完全定式化（`solve_mip`）

**決定変数**
- `x[e,p,s] ∈ {0,1}`：eがスロットsで工程pに就労（スキルあり・稼働可能スロットのみ生成）。
- `proc[p,t] ≥ 0`：工程pの時刻tの処理量。
- `short_p ≥ 0`：工程pの未処理量（ソフト）。
- `pen[e,p,s] ∈ {0,1}`：移動直後スロット（McCormick）。
- `n_e, ot_e ≥ 0`：総就労スロット数・残業スロット数。

**制約**
1. **1スロット1工程**：各(e,s)で `Σ_p x[e,p,s] ≤ 1`。
2. **連続勤務1ブロック**：就労の立ち上がり(0→1)回数 `Σ ups ≤ 1`（昼休みは稼働枠から除外＝午前午後は連続扱い）。
3. **最低勤務**（`min_work_minutes>0`時）：`n_e = 0` か `≥ min_slots`（`worked_emp` boolで切替）。
4. **工程移動ペナルティ**（McCormick, `pen = x · other_sum`）：`pen ≤ x`, `pen ≤ other_sum`, `pen ≥ x + other_sum − 1`。
   （`other_sum = Σ_{p2≠p} x[e,p2,直前スロット]`）
5. **能力上限**：`proc[p,t] ≤ Σ_e cap[e,p]·x[e,p,s] − Σ_e cap[e,p]·penalty_rate·pen[e,p,s]`。
   `cap[e,p] = base_productivity_p × skill_rate(level) × slot_hours`（1スロットでeがpを処理できる量）。
6. **到着累積（ハード）**：各pで `Σ_{≤t} proc ≤ Σ_{≤t} arrived`。
   `arrived(p,t) = root_volume[p][s] + conv_rate[p]·proc[upstream(p), t−1]`。
7. **未処理（ソフト）**：`short_p ≥ (Σ arrived − Σ proc)`（最終時点）。
8. **残業**：`ot_e ≥ n_e − threshold_slots`（`threshold_slots = overtime_threshold_minutes / slot_minutes`）。

**コスト式**
```
cost_expr = Σ_e [ wage_e·slot_hours·n_e  +  wage_e·slot_hours·(rate_ot − 1)·ot_e ]
```
（`wage_e = hourly_wage`, `rate_ot = overtime_wage_rate`）

**目的関数（objective_type別）**
| type | 目的 |
|---|---|
| `COST` | `Minimize( cost_expr + 1e3·sum_late + 1e5·sum_short )` |
| `MAKESPAN` | `Minimize( inventory_expr + 0.001·cost_expr + 1e8·sum_short )` |
| `MOVES`(参考) | `Minimize( 1e4·moves_expr + cost_expr + 1e8·sum_short )` |
| その他 | `Minimize( cost_expr + 1e5·sum_short )` |

- `inventory_expr = Σ_{p,t} (Σ_{≤t}arrived − Σ_{≤t}proc)`（在庫時間＝滞留量総和。makespanの代理）。
- `sum_late = Σ proc[p,t]`（末端工程かつ `スロット終了 > 締切` のもの）。
- `sum_short = Σ_p short_p`。

### 14-4. 制限時間・隔離

- 内部制限：`limit = clamp(60 + 整数変数数 / 40, 60, 600)` 秒。早期終了は**相対ギャップ1%**（ratioGap）。
- ハード強制終了：`solve_mip_isolated(hard_timeout_sec=700)`。超過で子プロセスkill→`None`→簡易計算。
- 失敗記録：`last_solve_meta.status ∈ {TIMEOUT_KILLED, SOLVER_CRASHED, EXCEPTION:*, NOT_SOLVED, ...}`。

### 14-5. 連続化リペア（採用条件の要点）

- **フェーズ1**（同一スロット2人入替）：全パス後、総未処理量が悪化していれば**丸ごと取消**。コスト不変。
- **フェーズ2**（直前工程へ付替）：`moves↓ かつ backlog≤base かつ deadline_violations≤base`。コスト不変。
- **フェーズ3**（席をB へ入替）：上記に加え `総コスト ≤ base_cost × (1 + repair_cost_budget_rate)`。試行上限あり(budget)。

### 14-6. 主要定数一覧

| 定数 | 値 | 出所 |
|---|---|---|
| スロット長 | 15分 (`slot_minutes`) | base |
| ギャップ早期終了 | 1% (ratioGap) | mip |
| 内部制限時間 | `clamp(60 + n/40, 60, 600)`秒 | mip |
| ハード強制終了 | 700秒 | mip |
| 目的の重み | COST: 1e3(late)/1e5(short)、MAKESPAN: 1e8(short) | mip |
| 工程移動ペナルティ率 | 0.30 | system_conditions |
| 残業割増 / 閾値 | 1.20 / 480分 | system_conditions |
| 残業最大終了 | 20:00 | system_conditions |
| 昼休み | 11:30–13:00 (60分) | system_conditions |
| リペアコスト許容枠 | 0.03 | system_conditions |
| 習熟度→生産性 | 1:0.8 / 2:1.0 / 3:1.2 | skill_level_productivity_rates |

### 14-7. まだコード併読が要る箇所（明示）

以下は挙動が細部に依存するため、完全一致にはソースの参照を推奨：
`calc_score` の各指標の算出式（`total_process_moves` の数え方等）／`_run_flow`・`_simulate_fixed` の
在庫前進の順序と丸め／グリーディ本体・`_refine_annealing`・`_refine_ortools`・`_dismiss_expensive_workers`
の近傍操作／昼休み・法定休憩の割当ロジック／API の厳密な入出力 schema。

---

_本書は実装（`backend/services/optimizer/`, `backend/models/`, `frontend/src/`）と対で保守する。
挙動を変えたら本書・`docs/user_guide.html`・GitHub Pages を同期すること。
特に第13章は「同じ失敗を繰り返さない」ための記録なので、修正で新たな決着がついたら必ず追記すること。_
