"""
DB 엔진과 세션 관리

SQLite 파일 기반. FastAPI Depends로 세션을 주입받아 사용한다.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


def init_db() -> None:
    """모든 테이블을 생성한다 (이미 존재하면 무시)."""
    # models 모듈을 import해야 SQLModel.metadata에 테이블이 등록된다.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends용 DB 세션 제너레이터."""
    with Session(engine) as session:
        yield session
