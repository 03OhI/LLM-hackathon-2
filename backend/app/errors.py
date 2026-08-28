"""
에러 코드 정의 (design.md §5)

FastAPI 전역 예외 핸들러(app/main.py)가 AppError를
{"error": {"code": ..., "message": ...}} 형태의 JSON으로 변환한다.
"""

from __future__ import annotations


class AppError(Exception):
    """API 계층에서 사용하는 표준 에러.

    code: 클라이언트가 분기할 수 있는 안정적 식별자
    message: 사람이 읽는 설명 (민감 정보 포함 금지)
    status_code: HTTP 상태 코드
    """

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ──────────────────────────────────────────────
# 에러 코드 상수 — design.md §5
# ──────────────────────────────────────────────

UNAUTHORIZED = "UNAUTHORIZED"  # 401 — 시크릿 누락/불일치
FORBIDDEN = "FORBIDDEN"  # 403 — 본인 소유가 아닌 리소스 접근
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"  # 404
PARTICIPANT_NOT_FOUND = "PARTICIPANT_NOT_FOUND"  # 404
INVALID_INVITE_TOKEN = "INVALID_INVITE_TOKEN"  # 404
ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"  # 404
VALIDATION_ERROR = "VALIDATION_ERROR"  # 422
INVALID_MEMBER_COUNT = "INVALID_MEMBER_COUNT"  # 422
MEMBER_COUNT_BELOW_SUBMITTED = "MEMBER_COUNT_BELOW_SUBMITTED"  # 422
DUPLICATE_SUBMISSION_METHOD = "DUPLICATE_SUBMISSION_METHOD"  # 409
SUBMISSION_LOCKED = "SUBMISSION_LOCKED"  # 409
ANALYSIS_ALREADY_RUNNING = "ANALYSIS_ALREADY_RUNNING"  # 409
ANALYSIS_NOT_READY = "ANALYSIS_NOT_READY"  # 409
SESSION_EXPIRED = "SESSION_EXPIRED"  # 410
INTERNAL_ERROR = "INTERNAL_ERROR"  # 500


# ──────────────────────────────────────────────
# 코드 → 기본 HTTP 상태 매핑 (편의 헬퍼)
# ──────────────────────────────────────────────

_STATUS_BY_CODE: dict[str, int] = {
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    SESSION_NOT_FOUND: 404,
    PARTICIPANT_NOT_FOUND: 404,
    INVALID_INVITE_TOKEN: 404,
    ANALYSIS_NOT_FOUND: 404,
    VALIDATION_ERROR: 422,
    INVALID_MEMBER_COUNT: 422,
    MEMBER_COUNT_BELOW_SUBMITTED: 422,
    DUPLICATE_SUBMISSION_METHOD: 409,
    SUBMISSION_LOCKED: 409,
    ANALYSIS_ALREADY_RUNNING: 409,
    ANALYSIS_NOT_READY: 409,
    SESSION_EXPIRED: 410,
    INTERNAL_ERROR: 500,
}


def app_error(code: str, message: str) -> AppError:
    """코드에 대응하는 기본 상태 코드로 AppError를 만드는 헬퍼."""
    return AppError(code=code, message=message, status_code=_STATUS_BY_CODE.get(code, 500))
