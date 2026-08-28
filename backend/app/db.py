"""
DB 엔진과 세션 관리

SQLite 파일 기반. FastAPI Depends로 세션을 주입받아 사용한다.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


# 기존 sqlite 개발 DB 파일에 신규 컬럼만 추가하는 최소 마이그레이션.
# Alembic 없이 create_all()만으로는 이미 존재하는 테이블에 컬럼을 더하지 못하므로,
# 데모/개발 단계에서 데이터 손실 없이 스키마를 진화시키기 위한 용도다.
_ADDITIVE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "session": [
        ("host_participant_id", "VARCHAR"),
        ("workspace_status", "VARCHAR DEFAULT 'LOCKED'"),
    ],
}


def _run_additive_sqlite_migration() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        existing_tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            existing_cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for col_name, col_def in columns:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def init_db() -> None:
    """모든 테이블을 생성한다 (이미 존재하면 무시)."""
    # models 모듈을 import해야 SQLModel.metadata에 테이블이 등록된다.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _run_additive_sqlite_migration()

    from app.services.quests.catalog import sync_catalog_to_db

    with Session(engine) as db:
        sync_catalog_to_db(db)


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends용 DB 세션 제너레이터."""
    with Session(engine) as session:
        yield session
