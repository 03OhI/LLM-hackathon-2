"""
인증 — secret 발급/해시/검증, 요청에서 시크릿 추출, FastAPI 의존성

시크릿 원문은 발급 시 1회만 응답으로 반환하고 DB에는 sha256 해시만 저장한다.
전달 방식: Authorization: Bearer <secret> 헤더 우선, 없으면 HttpOnly 쿠키.
쿼리 파라미터로 시크릿을 받지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, Request
from sqlmodel import Session as DBSession
from sqlmodel import select

from .db import get_session
from .errors import app_error
from .errors import FORBIDDEN, PARTICIPANT_NOT_FOUND, SESSION_NOT_FOUND, UNAUTHORIZED
from .models import Participant
from .models import Session as SessionModel


# ──────────────────────────────────────────────
# secret 발급/해시/검증
# ──────────────────────────────────────────────


def generate_secret() -> str:
    """URL-safe 무작위 시크릿을 생성한다."""
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """시크릿의 sha256 hex digest를 반환한다. 원문은 저장하지 않는다."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(secret: str, hashed: str) -> bool:
    """상수 시간 비교로 시크릿을 검증한다 (타이밍 공격 방지)."""
    candidate = hash_secret(secret)
    return hmac.compare_digest(candidate, hashed)


# ──────────────────────────────────────────────
# 요청에서 시크릿 추출
# ──────────────────────────────────────────────


def extract_secret(request: Request, cookie_name: str) -> str | None:
    """Authorization: Bearer 헤더를 우선 확인하고, 없으면 쿠키에서 읽는다.

    쿼리 파라미터는 절대 확인하지 않는다.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        if token:
            return token

    return request.cookies.get(cookie_name)


# ──────────────────────────────────────────────
# FastAPI 의존성
# ──────────────────────────────────────────────


async def assert_host(session_id: str, request: Request, db: DBSession = Depends(get_session)) -> SessionModel:
    """host_secret을 검증하고 세션을 반환한다.

    - 세션이 없으면 SESSION_NOT_FOUND (404)
    - 시크릿이 없거나 불일치하면 UNAUTHORIZED (401)
    """
    session = db.get(SessionModel, session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, f"세션을 찾을 수 없습니다: {session_id}")

    secret = extract_secret(request, cookie_name="host_secret")
    if not secret or not verify_secret(secret, session.host_secret_hash):
        raise app_error(UNAUTHORIZED, "주최자 인증에 실패했습니다.")

    return session


async def assert_participant(
    participant_id: str, request: Request, db: DBSession = Depends(get_session)
) -> Participant:
    """participant_secret을 검증하고 본인 소유의 participant를 반환한다.

    - 참여자가 없으면 PARTICIPANT_NOT_FOUND (404)
    - 시크릿이 없거나 불일치하면 UNAUTHORIZED (401)
    - 시크릿은 유효하지만 다른 participant_id를 요청하면 FORBIDDEN (403)
      (extract_secret은 요청자 본인의 쿠키/헤더만 읽으므로, 해시 불일치가 곧 FORBIDDEN 조건이다.
       참여자 존재 자체는 확인됐으나 시크릿이 그 참여자 것이 아니면 UNAUTHORIZED로 통일한다.)
    """
    participant = db.get(Participant, participant_id)
    if participant is None:
        raise app_error(PARTICIPANT_NOT_FOUND, f"참여자를 찾을 수 없습니다: {participant_id}")

    secret = extract_secret(request, cookie_name="participant_secret")
    if not secret:
        raise app_error(UNAUTHORIZED, "참여자 인증 정보가 없습니다.")

    if not verify_secret(secret, participant.participant_secret_hash):
        raise app_error(FORBIDDEN, "본인의 참여자 정보에만 접근할 수 있습니다.")

    return participant


def set_secret_cookie(response, cookie_name: str, secret: str, *, secure: bool, max_age_days: int = 30) -> None:
    """HttpOnly 쿠키로 시크릿을 설정한다."""
    response.set_cookie(
        key=cookie_name,
        value=secret,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age_days * 24 * 60 * 60,
    )


async def resolve_participant_by_secret(request: Request, db: DBSession = Depends(get_session)) -> Participant:
    """URL에 participant_id가 없는 엔드포인트(예: /results/me)에서 시크릿만으로 본인을 찾는다.

    participant_secret_hash는 참여자별로 유일하므로 시크릿 하나로 정확히 1명을 특정할 수 있다.
    시크릿이 없거나 일치하는 참여자가 없으면 UNAUTHORIZED (401).
    """
    secret = extract_secret(request, cookie_name="participant_secret")
    if not secret:
        raise app_error(UNAUTHORIZED, "참여자 인증 정보가 없습니다.")

    candidate_hash = hash_secret(secret)
    participant = db.exec(
        select(Participant).where(Participant.participant_secret_hash == candidate_hash)
    ).first()

    if participant is None:
        raise app_error(UNAUTHORIZED, "참여자 인증에 실패했습니다.")

    return participant
