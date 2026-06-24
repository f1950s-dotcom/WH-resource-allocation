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

        # シードデータ（工程構成・従業員）は「初回のみ」投入する。
        # 一度投入したら system_conditions の seed_data_loaded フラグを立て、
        # 以降は完全にスキップ。これにより利用者による変更・削除がすべて維持される
        # （初期値として一度だけ植え、その後は変更後のデータを使い続けられる）。
        already = conn.execute(text(
            "SELECT condition_value FROM system_conditions WHERE condition_key='seed_data_loaded'"
        )).fetchone()
        seed_path = os.path.join(os.path.dirname(__file__), "migrations", "seed_data.sql")
        if not already and os.path.exists(seed_path):
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
                "VALUES ('seed_data_loaded', '1', 'シードデータ投入済みフラグ（再投入防止）')"
            ))
            conn.commit()

        # Lightweight migrations for existing databases
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(optimization_results)"))]
        if "patterns_evaluated" not in cols:
            conn.execute(text(
                "ALTER TABLE optimization_results ADD COLUMN patterns_evaluated INTEGER NOT NULL DEFAULT 0"
            ))
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
