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

        # Lightweight migrations for existing databases
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(optimization_results)"))]
        if "patterns_evaluated" not in cols:
            conn.execute(text(
                "ALTER TABLE optimization_results ADD COLUMN patterns_evaluated INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
