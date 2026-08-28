"""
백엔드 애플리케이션 설정 (pydantic-settings)

Bedrock 클라이언트에 region_name을 하드코딩하지 않는다 (ai/config.py와 동일 원칙).
AWS Access Key는 여기에 두지 않는다 — boto3 기본 자격 증명 체인(EC2 인스턴스 프로파일)을 사용한다.
쿠키 서명 키 등 시크릿도 코드에 넣지 않는다 — 시크릿 자체는 발급 시 무작위 생성해 해시만
저장하므로(app/auth.py) 여기 설정에는 애초에 비밀값이 없다.

배포 구조와 쿠키/CORS 정책
──────────────────────────
1. 프론트와 백엔드가 같은 origin으로 배포되는 경우 (Nginx 리버스 프록시나 Next.js
   rewrites로 /api를 백엔드로 프록시) — 브라우저 기준으로는 same-origin 요청이라
   CORS preflight 자체가 발생하지 않고 쿠키도 SameSite=Lax로 정상 전달된다.
   FRONTEND_ORIGINS는 이 경우에도 안전망으로 유지한다(예: 로컬 개발 시 프론트를
   별도 포트로 띄우는 상황 등).
2. 프론트와 백엔드가 다른 origin으로 배포되는 경우 (별도 도메인/포트에서 직접 fetch) —
   다음이 모두 필요하다:
   - CORSMiddleware(allow_credentials=True)와 FRONTEND_ORIGINS에 정확한 origin만 명시
     (와일드카드 "*" 금지 — allow_credentials=True와 "*"는 브라우저가 애초에 허용하지 않는다).
   - 쿠키는 SameSite=None + Secure=True로 발급해야 브라우저가 cross-site fetch에도
     쿠키를 실어 보낸다(SameSite=Lax는 cross-site fetch/XHR에는 전송되지 않는다).
   - 배포가 HTTPS라면 Secure=True(COOKIE_SECURE), 로컬 HTTP 개발이면 False.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

_ALLOWED_SAMESITE = {"lax", "strict", "none"}


class Settings(BaseSettings):
    database_url: str = "sqlite:///./chemistry.db"

    # FRONTEND_ORIGINS=https://app.example.com,https://admin.example.com 처럼
    # 콤마로 구분한 명시적 origin 목록만 허용한다. 와일드카드는 금지한다.
    # NoDecode: pydantic-settings가 list 필드를 기본 JSON으로 파싱하려는 것을 막고
    # 아래 _parse_comma_separated(모드="before")가 원본 문자열을 그대로 받게 한다.
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    cookie_secure: bool = True  # 로컬 HTTP 개발 시 .env로 False
    # lax: same-origin 배포 기본값. none: cross-origin 배포 시 필수(Secure와 함께 사용).
    cookie_samesite: str = "lax"

    session_ttl_days: int = 30

    # ai/config.py의 AISettings와 동일 키를 공유 (문서화 목적, 실제 조회는 ai.config가 담당)
    bedrock_model_id: str = "global.anthropic.claude-sonnet-5"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def _parse_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("frontend_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError(
                "FRONTEND_ORIGINS에 와일드카드(*)를 사용할 수 없습니다. "
                "allow_credentials=True와 함께 쓰면 브라우저가 거부합니다."
            )
        return value

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in _ALLOWED_SAMESITE:
            raise ValueError(f"COOKIE_SAMESITE는 {_ALLOWED_SAMESITE} 중 하나여야 합니다: {value!r}")
        return normalized

    @model_validator(mode="after")
    def _samesite_none_requires_secure(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SAMESITE=none이면 COOKIE_SECURE=true여야 합니다 "
                "(Secure 없는 SameSite=None 쿠키는 최신 브라우저가 거부합니다)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
