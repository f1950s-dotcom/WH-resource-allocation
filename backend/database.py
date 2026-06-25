from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./warehouse.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database with schema and seed data."""
    sql_path = os.path.join(os.path.dirname(__file__), "migrations", "init_schema.sql")
    with engine.connect() as conn:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()
        # Execute each statement
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()

        # シードデータ（工程構成・従業員）はバージョン管理で投入する。
        # system_conditions の seed_version に投入済みバージョンを記録し、
        # SEED_VERSION（コード側）の方が新しい時だけ seed_data.sql を流す。
        #   - 投入は INSERT OR IGNORE なので、利用者が編集・追加した既存行は壊さない
        #   - シードを更新（例：スキル追加）したら SEED_VERSION を上げることで、
        #     既存DBにも不足分（新スキル等）が次回起動時に補充される
        #   - 利用者が消した行のうち、シードに含まれるものは再補充される点に注意
        SEED_VERSION = 2
        ver_row = conn.execute(text(
            "SELECT condition_value FROM system_conditions WHERE condition_key='seed_version'"
        )).fetchone()
        # 旧フラグ(seed_data_loaded)しか無い既存DBはバージョン1扱いにする
        if ver_row is not None:
            current_ver = int(ver_row[0])
        else:
            legacy = conn.execute(text(
                "SELECT condition_value FROM system_conditions WHERE condition_key='seed_data_loaded'"
            )).fetchone()
            current_ver = 1 if legacy else 0

        seed_path = os.path.join(os.path.dirname(__file__), "migrations", "seed_data.sql")
        if current_ver < SEED_VERSION and os.path.exists(seed_path):
            with open(seed_path, "r", encoding="utf-8") as f:
                seed_content = f.read()
            for raw in seed_content.split(";"):
                # 行頭コメント(--)を除去してからステートメント化
                stmt = "\n".join(
                    ln for ln in raw.splitlines() if not ln.strip().startswith("--")
                ).strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.execute(text(
                "INSERT OR REPLACE INTO system_conditions (condition_key, condition_value, description) "
                "VALUES ('seed_version', :v, 'シードデータ投入済みバージョン')"
            ), {"v": str(SEED_VERSION)})
            conn.execute(text(
                "INSERT OR REPLACE INTO system_conditions (condition_key, condition_value, description) "
                "VALUES ('seed_data_loaded', '1', 'シードデータ投入済みフラグ（後方互換）')"
            ))
            conn.commit()

        # overtime_max_end_time が無い既存DBには挿入する
        conn.execute(text(
            "INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) "
            "VALUES ('overtime_max_end_time', '20:00', '残業可能な場合の最大勤務終了時刻')"
        ))
        # 工程移動時の習熟ペナルティ設定（既存DBへ追加）
        conn.execute(text(
            "INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) "
            "VALUES ('process_transition_penalty_enabled', '1', "
            "'工程移動直後スロットの生産性ペナルティ有効フラグ（1=有効, 0=無効）')"
        ))
        conn.execute(text(
            "INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) "
            "VALUES ('process_transition_penalty_rate', '0.30', "
            "'工程移動直後スロットの生産性低下率（0.30=30%低下）')"
        ))
        # 最低勤務時間・1工程の最低配置時間（既存DBへ追加）
        conn.execute(text(
            "INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) "
            "VALUES ('min_work_minutes', '240', "
            "'1人を配置する場合の最低勤務時間（分）。これ未満しか働けない人は配置しない')"
        ))
        conn.execute(text(
            "INSERT OR IGNORE INTO system_conditions (condition_key, condition_value, description) "
            "VALUES ('min_process_assignment_minutes', '60', "
            "'1工程への最低連続配置時間（分）。ただしその工程の当日作業が完了する場合は適用しない')"
        ))
        conn.commit()

        # Lightweight migrations for existing databases
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(optimization_results)"))]
        if "patterns_evaluated" not in cols:
            conn.execute(text(
                "ALTER TABLE optimization_results ADD COLUMN patterns_evaluated INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        # 計算エンジン・ソルバー実行記録の列（既存DBへ追加）
        if "calculation_method" not in cols:
            conn.execute(text(
                "ALTER TABLE optimization_results ADD COLUMN calculation_method TEXT NOT NULL DEFAULT 'GREEDY'"
            ))
            conn.commit()
        if "solver_status" not in cols:
            conn.execute(text("ALTER TABLE optimization_results ADD COLUMN solver_status TEXT"))
            conn.commit()
        if "solver_gap" not in cols:
            conn.execute(text("ALTER TABLE optimization_results ADD COLUMN solver_gap NUMERIC(6,4)"))
            conn.commit()
        if "solve_seconds" not in cols:
            conn.execute(text("ALTER TABLE optimization_results ADD COLUMN solve_seconds NUMERIC(8,2)"))
            conn.commit()

        # Skill level 1 was 0.70; correct to 0.80 for existing databases
        row = conn.execute(text(
            "SELECT productivity_rate FROM skill_level_productivity_rates WHERE skill_level=1"
        )).fetchone()
        if row and abs(float(row[0]) - 0.70) < 0.01:
            conn.execute(text(
                "UPDATE skill_level_productivity_rates SET productivity_rate=0.80 WHERE skill_level=1"
            ))
            conn.commit()
