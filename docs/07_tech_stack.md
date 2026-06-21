# 倉庫人員配置最適化システム 設計書
## 第7章 技術スタック・アーキテクチャ

---

### 7.1 技術スタック

| 層 | 技術 | 理由 |
|----|------|------|
| フロントエンド | React + TypeScript | コンポーネント型UI、型安全 |
| UIライブラリ | Tailwind CSS + shadcn/ui | 素早いUI構築 |
| ガントチャート | react-gantt-chart または カスタム実装 | 15分粒度対応 |
| バックエンド | Python + FastAPI | 最適化ロジックをPythonで実装しやすい |
| ORM | SQLAlchemy | DB抽象化 |
| DB | SQLite（開発・シングルユーザー） | シンプル・ゼロ設定 |
| Excel出力 | openpyxl | Pythonから柔軟なExcel生成 |
| 最適化 | 純Pythonまたは scipy.optimize | 外部ソルバー不要 |

---

### 7.2 システムアーキテクチャ

```
┌──────────────────────────────────────────────────────┐
│                    Browser                            │
│  React SPA                                           │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │マスタ画面  │  │物量登録/展開│  │最適化/シフト │  │
│  └────────────┘  └─────────────┘  └──────────────┘  │
└─────────────────────┬────────────────────────────────┘
                      │ HTTP/REST (JSON)
┌─────────────────────▼────────────────────────────────┐
│                FastAPI Server                         │
│  ┌──────────────────────────────────────────────┐    │
│  │ Router                                        │    │
│  │  /api/master/*   マスタCRUD                  │    │
│  │  /api/volume/*   物量登録・展開               │    │
│  │  /api/optimize   最適化実行（非同期）          │    │
│  │  /api/shift/*    シフト取得・Excel出力        │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Service Layer                                 │    │
│  │  VolumeExpansionService  物量展開計算         │    │
│  │  OptimizationService     最適化アルゴリズム   │    │
│  │  ShiftService            シフト生成           │    │
│  │  ExcelExportService      Excel出力            │    │
│  └──────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────┐    │
│  │ Repository Layer（SQLAlchemy）                │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────┬────────────────────────────────┘
                      │
              ┌───────▼──────┐
              │  SQLite DB   │
              │  wh_alloc.db │
              └──────────────┘
```

---

### 7.3 API エンドポイント一覧

#### マスタ系

| Method | Path | 説明 |
|--------|------|------|
| GET | /api/employees | 人員一覧 |
| POST | /api/employees | 人員登録 |
| PUT | /api/employees/{id} | 人員更新 |
| DELETE | /api/employees/{id} | 人員削除 |
| GET | /api/employees/{id}/skills | スキル一覧 |
| PUT | /api/employees/{id}/skills | スキル一括更新 |
| GET | /api/employees/{id}/conditions | 勤務条件一覧 |
| PUT | /api/employees/{id}/conditions | 勤務条件一括更新 |
| GET | /api/processes | 工程一覧 |
| POST | /api/processes | 工程登録 |
| PUT | /api/processes/{id} | 工程更新 |
| GET | /api/processes/connections | 工程接続一覧 |
| PUT | /api/processes/connections | 工程接続一括更新 |
| GET | /api/volume-rules | 物量変換ルール一覧 |
| PUT | /api/volume-rules | 物量変換ルール一括更新 |
| GET | /api/conditions | 条件マスタ一覧 |
| PUT | /api/conditions | 条件マスタ更新 |

#### 日次業務系

| Method | Path | 説明 |
|--------|------|------|
| GET | /api/volume-plans/{date} | 物量計画取得 |
| PUT | /api/volume-plans/{date} | 物量計画一括保存 |
| POST | /api/volume-plans/{date}/expand | 物量展開実行 |
| GET | /api/volume-expansions/{date} | 物量展開結果取得 |
| POST | /api/optimize/{date} | 最適化実行（非同期） |
| GET | /api/optimize/{date}/results | 最適化結果一覧取得 |
| GET | /api/optimize/{date}/results/{result_id} | 最適化結果詳細取得 |
| POST | /api/optimize/{date}/results/{result_id}/select | 案を選択 |
| GET | /api/shifts/{date} | シフト取得（選択済み案） |
| GET | /api/shifts/{date}/export | Excelダウンロード |

---

### 7.4 ディレクトリ構成

```
wh-resource-allocation/
├── backend/
│   ├── main.py                    # FastAPIアプリ起動
│   ├── database.py                # DB接続・セッション
│   ├── models/                    # SQLAlchemyモデル
│   │   ├── employee.py
│   │   ├── process.py
│   │   ├── volume.py
│   │   └── optimization.py
│   ├── schemas/                   # Pydanticスキーマ（API型定義）
│   │   ├── employee.py
│   │   ├── process.py
│   │   ├── volume.py
│   │   └── optimization.py
│   ├── routers/                   # APIルーター
│   │   ├── master.py
│   │   ├── volume.py
│   │   ├── optimize.py
│   │   └── shift.py
│   ├── services/                  # ビジネスロジック
│   │   ├── volume_expansion.py    # 物量展開計算
│   │   ├── optimizer/
│   │   │   ├── base.py            # 共通前処理・評価関数
│   │   │   ├── fastest.py         # 案A：最速完了
│   │   │   ├── cheapest.py        # 案B：最低コスト
│   │   │   └── least_move.py      # 案C：最小移動
│   │   ├── shift_generator.py     # シフト生成
│   │   └── excel_exporter.py      # Excel出力
│   ├── migrations/
│   │   └── init_schema.sql        # 初期DDL
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── master/
│   │   │   │   ├── EmployeeList.tsx
│   │   │   │   ├── EmployeeDetail.tsx
│   │   │   │   ├── ProcessList.tsx
│   │   │   │   ├── ProcessConnections.tsx
│   │   │   │   ├── VolumeRules.tsx
│   │   │   │   └── Conditions.tsx
│   │   │   ├── VolumePlan.tsx
│   │   │   ├── VolumeExpansion.tsx
│   │   │   ├── Optimization.tsx
│   │   │   ├── OptimizationDetail.tsx
│   │   │   └── Shift.tsx
│   │   ├── components/
│   │   │   ├── GanttChart.tsx
│   │   │   ├── HeatMap.tsx
│   │   │   ├── TimeSlotGrid.tsx
│   │   │   └── OptimizationCard.tsx
│   │   ├── api/                   # APIクライアント
│   │   └── types/                 # 型定義
│   ├── package.json
│   └── tsconfig.json
└── docs/                          # 設計書（本ドキュメント群）
```

---

### 7.5 非同期処理の設計

最適化計算は数秒〜30秒かかるため、非同期で実行する。

```
Client                    FastAPI
  |                          |
  |-- POST /optimize/{date} →|
  |← 202 Accepted            |  job_id を返す
  |   { job_id: "xxx" }      |
  |                     [バックグラウンドタスク開始]
  |                          |
  |-- GET /optimize/{date}/results → (ポーリング)
  |← 200 { status: "running" }
  |                          |
  |-- GET /optimize/{date}/results → (ポーリング)
  |← 200 { status: "done", results: [...] }
```

> FastAPI の BackgroundTasks または asyncio を使用。
> 計算完了フラグは optimization_results テーブルで管理。

