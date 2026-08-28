"""
백엔드 애플리케이션 설정 (pydantic-settings)

Bedrock 클라이언트에 region_name을 하드코딩하지 않는다 (ai/config.py와 동일 원칙).
AWS Access Key는 여기에 두지 않는다 — boto3 기본 자격 증명 체인(EC2 인스턴스 프로파일)을 사용한다.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./chemistry.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool = True  # 로컬 HTTP 개발 시 .env로 False
    session_ttl_days: int = 30

    # 퀘스트 배정 개수 (분석당 lazy 배정 시 카탈로그 후보 중 상위 N개)
    team_quest_count: int = 3
    personal_quest_count: int = 2

    # ai/config.py의 AISettings와 동일 키를 공유 (문서화 목적, 실제 조회는 ai.config가 담당)
    bedrock_model_id: str = "global.anthropic.claude-sonnet-5"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
