"""
Bedrock 퀘스트 배정 실호출 스모크 테스트 — EC2/팀 AWS 실행 환경 전용.

evals/test_quest_assignment.py는 Bedrock을 mock으로 대체해 로직만 검증한다.
이 스크립트는 그 반대다: 실제 ChatBedrockConverse로 Amazon Bedrock을 호출해
모델 접근·IAM 권한(bedrock:InvokeModel)·구조화 출력·장애 시 폴백을 검증한다.

기본 pytest 스위트에는 포함되지 않는다(파일명이 test_*가 아니다). 실행 방법:

    python -m evals.bedrock_quest_smoke

pytest로 개별 케이스만 돌리고 싶으면 evals/test_bedrock_live.py를 쓴다
(마커 bedrock_live, 기본 pytest에서는 backend/pytest.ini의
addopts=-m "not bedrock_live"로 제외된다).

이 스크립트는 카탈로그·DB를 변경하지 않고, AWS 자격 증명 값을 출력하지 않는다.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import socket
import sys
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.config import get_ai_settings
from ai.quest_assignment import assign_quest
from ai.quest_assignment.filter import matched_candidates
from ai.quest_assignment.nodes import select as select_module
from ai.quest_assignment.nodes.validate import (
    _check_grade_leak,
    _check_judgment,
    _check_numeric_score,
    _check_position_label_leak,
)
from ai.quest_assignment.schemas import QuestAssignmentDecision, QuestMatchContext, QuestSelectionOutput, QuestTemplate

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"

# SPEC_V5.2 §7 + 이 검증 작업 자체의 로그 안전성 요건 — 이 토큰들이 로그에
# 그대로 나타나면 안 된다. AWS 자격 증명 관련 토큰도 함께 감시한다.
FORBIDDEN_LOG_TOKENS = [
    "participant_id",
    "nickname",
    "self_positions",
    "team_grade",
    "internal_index",
    "caution",
    "survey",
    "aws_access_key_id",
    "aws_secret_access_key",
    "AKIA",
    "ASIA",
    "SecretAccessKey",
    "SessionToken",
]


# ──────────────────────────────────────────────
# fixture 헬퍼 (test_quest_assignment.py와 동일한 실제 카탈로그를 재사용)
# ──────────────────────────────────────────────


def load_real_catalog() -> list[QuestTemplate]:
    data = json.loads((KNOWLEDGE_BASE_DIR / "quests.json").read_text(encoding="utf-8"))
    return [QuestTemplate(**q) for q in data]


def make_context(**overrides) -> QuestMatchContext:
    base = dict(
        room_id="bedrock-smoke-test-room",
        team_size=4,
        matched_rule_ids=[],
        distribution={"agency": {"DRIVER": 1, "SUPPORTER": 1, "NEUTRAL": 2}},
        context_tags=["FIRST_MEETING"],
        completed_quest_ids=[],
    )
    base.update(overrides)
    return QuestMatchContext(**base)


def _eligible_pool(catalog: list[QuestTemplate]) -> list[QuestTemplate]:
    return [q for q in catalog if q.is_active and q.assignment == "AUTO" and not q.is_universal]


# ──────────────────────────────────────────────
# 결과 리포팅
# ──────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Reporter:
    results: list[CheckResult] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        condition = bool(condition)
        self.results.append(CheckResult(name, condition, detail))
        mark = "PASS" if condition else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
        return condition

    def section(self, title: str) -> None:
        print(f"\n=== {title} ===")

    def summary(self) -> bool:
        total = len(self.results)
        failed = [r for r in self.results if not r.passed]
        print(f"\n{'=' * 60}")
        print(f"{total - len(failed)}/{total} checks passed")
        if failed:
            print("FAILED:")
            for r in failed:
                print(f"  - {r.name}: {r.detail}")
        return not failed


# ──────────────────────────────────────────────
# 로그 캡처 + 금칙어 스캔
# ──────────────────────────────────────────────


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


@contextmanager
def capture_logs(logger_name: str = "ai.quest_assignment"):
    logger = logging.getLogger(logger_name)
    handler = _CaptureHandler()
    handler.setLevel(logging.DEBUG)
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def _scan_forbidden_expression(text: str) -> str | None:
    for checker in (_check_grade_leak, _check_numeric_score, _check_judgment, _check_position_label_leak):
        hit = checker(text)
        if hit:
            return hit
    return None


def _scan_log_safety(messages: list[str]) -> str | None:
    joined = "\n".join(messages)
    for token in FORBIDDEN_LOG_TOKENS:
        if token in joined:
            return token
    return None


# ──────────────────────────────────────────────
# 1. 실행 환경 확인 (자격 증명 값은 절대 출력하지 않는다)
# ──────────────────────────────────────────────


def check_environment(reporter: Reporter) -> tuple[str | None, str | None]:
    import os

    reporter.section("1. 실행 환경 확인")
    print(f"  AWS_REGION env: {os.environ.get('AWS_REGION') or '(unset)'}")
    print(f"  BEDROCK_REGION env: {os.environ.get('BEDROCK_REGION') or '(unset)'}")

    settings = get_ai_settings()
    print(f"  BEDROCK_MODEL_ID (설정값): {settings.bedrock_model_id}")
    print(
        f"  bedrock_timeout={settings.bedrock_timeout}s, "
        f"bedrock_max_tokens={settings.bedrock_max_tokens}, "
        f"quest_skip_bedrock_for_single_candidate={settings.quest_skip_bedrock_for_single_candidate}"
    )

    role_name: str | None = None
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        token = urllib.request.urlopen(token_req, timeout=2).read().decode()
        role_req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            headers={"X-aws-ec2-metadata-token": token},
        )
        role_name = urllib.request.urlopen(role_req, timeout=2).read().decode().strip()
        reporter.check("EC2 인스턴스 메타데이터(IMDSv2) 접근", True, f"IAM Role: {role_name}")
    except Exception as e:  # noqa: BLE001
        reporter.check("EC2 인스턴스 메타데이터(IMDSv2) 접근", False, f"{type(e).__name__} — EC2가 아니거나 IMDS 비활성")

    region: str | None = None
    try:
        import boto3

        region = boto3.Session().region_name
        reporter.check("boto3 기본 세션 리전 인식", region is not None, str(region))
    except Exception as e:  # noqa: BLE001
        reporter.check("boto3 세션 생성", False, f"{type(e).__name__}: {e}")

    for mod in ("boto3", "langchain_aws", "langchain_core", "langgraph", "pydantic", "pydantic_settings"):
        try:
            m = importlib.import_module(mod)
            reporter.check(f"의존성 {mod}", True, getattr(m, "__version__", "?"))
        except ImportError as e:  # noqa: BLE001
            reporter.check(f"의존성 {mod}", False, str(e))

    if region:
        host = f"bedrock-runtime.{region}.amazonaws.com"
        try:
            with socket.create_connection((host, 443), timeout=5):
                reporter.check(f"네트워크 연결 ({host}:443)", True)
        except OSError as e:
            reporter.check(f"네트워크 연결 ({host}:443)", False, type(e).__name__)
    else:
        reporter.check("네트워크 연결 확인", False, "리전을 확인할 수 없어 endpoint를 구성 못 함")

    return role_name, region


async def check_model_access(reporter: Reporter) -> bool:
    """bedrock:InvokeModel 권한 + 모델 액세스 + 구조화 출력 파싱을 최소 호출로 확인."""
    from langchain_core.messages import HumanMessage, SystemMessage

    reporter.section("1b. Bedrock 모델 액세스 probe (최소 실호출)")
    try:
        model = select_module.get_chat_model().with_structured_output(QuestSelectionOutput)
        start = time.monotonic()
        result = await asyncio.wait_for(
            model.ainvoke(
                [
                    SystemMessage(content="당신은 구조화 출력 형식을 확인하는 테스트용 도우미입니다."),
                    HumanMessage(
                        content=(
                            "quest_id 필드에 'PROBE_OK', reason과 intro_message에 짧은 아무 문장을, "
                            "used_rule_ids에 빈 배열을 채워 응답하세요."
                        )
                    ),
                ]
            ),
            timeout=get_ai_settings().bedrock_timeout,
        )
        elapsed = time.monotonic() - start
        ok = reporter.check(
            "bedrock:InvokeModel 성공 + 구조화 출력 파싱",
            isinstance(result, QuestSelectionOutput),
            f"{elapsed:.2f}s, quest_id={getattr(result, 'quest_id', None)!r}",
        )
        return ok
    except Exception as e:  # noqa: BLE001
        reporter.check("bedrock:InvokeModel 성공 + 구조화 출력 파싱", False, f"{type(e).__name__}: {e}")
        return False


# ──────────────────────────────────────────────
# 2. 실제 호출 시나리오
# ──────────────────────────────────────────────


async def run_agent_scenario(reporter: Reporter) -> tuple[QuestAssignmentDecision, float]:
    reporter.section("2-1. AGENT 경로 (맞춤 후보 2~3개 → 실제 Bedrock)")
    catalog = load_real_catalog()
    ctx = make_context(
        matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION", "TEAM_BALANCED_AGENCY"],
        team_size=4,
    )
    candidates = matched_candidates(_eligible_pool(catalog), ctx)
    print(f"  맞춤 후보: {[c.quest_id for c in candidates]}")
    reporter.check("맞춤 후보 2~3개 확보", 2 <= len(candidates) <= 3, str(len(candidates)))

    with capture_logs() as handler:
        start = time.monotonic()
        decision = await assign_quest(ctx, catalog)
        elapsed = time.monotonic() - start

    print(f"  응답 시간: {elapsed:.2f}s")
    print(f"  reason: {decision.reason}")
    print(f"  intro_message: {decision.intro_message}")
    print(f"  used_rule_ids: {decision.used_rule_ids}")

    reporter.check("assignment_source == AGENT", decision.assignment_source == "AGENT", decision.assignment_source)
    reporter.check(
        "quest_id가 후보 안에 있음", decision.quest_id in {c.quest_id for c in candidates}, decision.quest_id
    )
    reporter.check(
        "used_rule_ids가 matched_rule_ids의 부분집합",
        set(decision.used_rule_ids) <= set(ctx.matched_rule_ids),
        str(decision.used_rule_ids),
    )
    reporter.check("reason 길이 <= 120", len(decision.reason) <= 120, str(len(decision.reason)))
    reporter.check("intro_message 길이 <= 120", len(decision.intro_message) <= 120, str(len(decision.intro_message)))

    forbidden_hit = _scan_forbidden_expression(f"{decision.reason} {decision.intro_message}")
    reporter.check("금칙어(등급/포지션/성공확률 등) 미포함", forbidden_hit is None, forbidden_hit or "")

    reporter.check(
        "steps 필드가 산출 스키마에 없음(구조적으로 생성 불가)",
        "steps" not in QuestAssignmentDecision.model_fields,
    )
    reporter.check(
        "completion_condition 필드가 산출 스키마에 없음",
        "completion_condition" not in QuestAssignmentDecision.model_fields,
    )

    log_leak = _scan_log_safety(handler.messages)
    reporter.check("로그에 금지 토큰 없음", log_leak is None, log_leak or "")

    return decision, elapsed


class _BoomChatModel:
    """Bedrock이 호출되면 안 되는 경로(RULE/FALLBACK)에서 실제로 호출되지 않았음을
    증명하기 위한 가짜 모델 — 호출되면 즉시 AssertionError를 던진다."""

    class _BoomStructured:
        async def ainvoke(self, messages):  # noqa: ANN001
            raise AssertionError("이 경로에서는 Bedrock이 호출되면 안 된다")

    def with_structured_output(self, schema):  # noqa: ANN001
        return self._BoomStructured()


async def run_rule_scenario(reporter: Reporter) -> tuple[QuestAssignmentDecision, float]:
    reporter.section("2-2. RULE 경로 (맞춤 후보 1개 → Bedrock 생략)")
    catalog = load_real_catalog()
    ctx = make_context(matched_rule_ids=["TEAM_DRIVER_ENERGY"], team_size=4)
    candidates = matched_candidates(_eligible_pool(catalog), ctx)
    print(f"  맞춤 후보: {[c.quest_id for c in candidates]}")
    reporter.check("맞춤 후보 정확히 1개", len(candidates) == 1, str(len(candidates)))

    orig = select_module.get_chat_model
    select_module.get_chat_model = lambda: _BoomChatModel()
    try:
        start = time.monotonic()
        decision = await assign_quest(ctx, catalog)
        elapsed = time.monotonic() - start
    finally:
        select_module.get_chat_model = orig

    print(f"  응답 시간: {elapsed:.3f}s (Bedrock 미호출 확인됨)")
    reporter.check("assignment_source == RULE", decision.assignment_source == "RULE", decision.assignment_source)
    reporter.check(
        "quest_id가 단일 후보와 일치",
        bool(candidates) and decision.quest_id == candidates[0].quest_id,
        decision.quest_id,
    )
    return decision, elapsed


async def run_fallback_scenario(reporter: Reporter) -> tuple[QuestAssignmentDecision, float]:
    reporter.section("2-3. FALLBACK 경로 (맞춤 후보 없음 → 범용 퀘스트)")
    catalog = load_real_catalog()
    ctx = make_context(matched_rule_ids=[], team_size=4)
    candidates = matched_candidates(_eligible_pool(catalog), ctx)
    reporter.check("맞춤 후보 0개", len(candidates) == 0, str(len(candidates)))

    orig = select_module.get_chat_model
    select_module.get_chat_model = lambda: _BoomChatModel()
    try:
        start = time.monotonic()
        decision = await assign_quest(ctx, catalog)
        elapsed = time.monotonic() - start
    finally:
        select_module.get_chat_model = orig

    print(f"  응답 시간: {elapsed:.3f}s (Bedrock 미호출 확인됨)")
    reporter.check(
        "assignment_source == FALLBACK", decision.assignment_source == "FALLBACK", decision.assignment_source
    )
    reporter.check(
        "범용 퀘스트(is_universal) 선택",
        decision.quest_id == "TEAM_SIGNATURE_REACTION",
        decision.quest_id,
    )
    return decision, elapsed


# ──────────────────────────────────────────────
# 3. 장애 검증 — 실제 Bedrock 실패를 유도한다 (구조화 출력 실패만 mock)
# ──────────────────────────────────────────────


def patch_invalid_model() -> None:
    """select_with_bedrock의 try 블록 안에서 실제 select.get_chat_model()이 호출되는
    시점과 동일하게, 모델 생성 자체를 lambda 안으로 지연시킨다 — 즉시 생성하면
    자격 증명/리전 검증 오류가 그래프의 예외 처리를 우회해 그대로 터진다."""
    from langchain_aws import ChatBedrockConverse

    select_module.get_chat_model = lambda: ChatBedrockConverse(
        model_id="global.anthropic.this-model-id-does-not-exist", temperature=0, max_tokens=800
    )


def patch_blocked_model() -> None:
    """TEAM_GUIDE가 명시한, 팀 권한으로 명시적 차단된 모델 — 실제 AccessDenied를 유도한다."""
    from langchain_aws import ChatBedrockConverse

    select_module.get_chat_model = lambda: ChatBedrockConverse(
        model_id="global.anthropic.claude-opus-5", temperature=0, max_tokens=800
    )


def patch_timeout() -> None:
    settings = get_ai_settings()
    fast_fail_settings = settings.model_copy(update={"bedrock_timeout": 0})
    select_module.get_ai_settings = lambda: fast_fail_settings


def patch_structured_output_failure() -> None:
    """구조화 출력 파싱 실패는 실제 Bedrock으로 안정적으로 재현하기 어려워 mock한다
    (요청사항에 명시된 유일한 mock 케이스)."""

    class _FakeStructuredModel:
        async def ainvoke(self, messages):  # noqa: ANN001
            raise ValueError("simulated structured-output parse failure (mock)")

    class _FakeChatModel:
        def with_structured_output(self, schema):  # noqa: ANN001
            return _FakeStructuredModel()

    select_module.get_chat_model = lambda: _FakeChatModel()


async def run_failure_scenario(
    reporter: Reporter, title: str, patch_fn
) -> tuple[QuestAssignmentDecision | None, float, list[str]]:
    """assign_quest()가 그래프 내부에서 처리하지 못하는 무언가가 생기더라도(설계상
    있어서는 안 되지만) 스모크 스크립트 전체가 죽지 않고 실패를 기록하고 계속
    진행하도록 이 함수 전체를 보호한다."""
    reporter.section(title)
    catalog = load_real_catalog()
    ctx = make_context(
        matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION", "TEAM_BALANCED_AGENCY"],
        team_size=4,
    )

    orig_chat_model = select_module.get_chat_model
    orig_settings = select_module.get_ai_settings
    decision: QuestAssignmentDecision | None = None
    elapsed = 0.0
    handler = _CaptureHandler()
    try:
        patch_fn()
        with capture_logs() as handler:
            start = time.monotonic()
            decision = await assign_quest(ctx, catalog)
            elapsed = time.monotonic() - start
    except Exception as e:  # noqa: BLE001 — 그래프가 흡수하지 못한 예외까지 스모크 결과로 남긴다
        reporter.check(
            "폴백 또는 명시적 처리로 최종 decision 반환",
            False,
            f"그래프 밖으로 예외가 그대로 전파됨: {type(e).__name__}: {e}",
        )
        return None, elapsed, []
    finally:
        select_module.get_chat_model = orig_chat_model
        select_module.get_ai_settings = orig_settings

    print(f"  응답 시간: {elapsed:.2f}s")
    error_lines = [m for m in handler.messages if "LLM_ERROR" in m or "select_with_bedrock failed" in m]
    for line in error_lines[:2]:
        print(f"  캡처된 오류 로그: {line}")

    reporter.check("폴백 또는 명시적 처리로 최종 decision 반환", decision is not None)
    if decision is not None:
        reporter.check(
            "assignment_source == FALLBACK", decision.assignment_source == "FALLBACK", decision.assignment_source
        )
    log_leak = _scan_log_safety(handler.messages)
    reporter.check("로그에 금지 토큰 없음", log_leak is None, log_leak or "")

    return decision, elapsed, error_lines


# ──────────────────────────────────────────────
# main
# ──────────────────────────────────────────────


async def _safe_run(reporter: Reporter, label: str, coro):
    """개별 시나리오 함수가 예상 밖 예외를 던지더라도 나머지 시나리오와 최종
    리포트는 계속 진행되도록 감싼다."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        reporter.check(f"{label} 실행", False, f"{type(e).__name__}: {e}")
        return None, 0.0


def _decision_summary(decision: QuestAssignmentDecision | None, elapsed: float) -> dict:
    if decision is None:
        return {"quest_id": None, "source": None, "elapsed_sec": round(elapsed, 3)}
    return {
        "quest_id": decision.quest_id,
        "source": decision.assignment_source,
        "elapsed_sec": round(elapsed, 3),
    }


async def main() -> int:
    reporter = Reporter()

    role_name, region = check_environment(reporter)
    await check_model_access(reporter)

    reporter.section("2. 실제 호출 시나리오")
    agent_decision, agent_elapsed = await _safe_run(reporter, "AGENT 시나리오", run_agent_scenario(reporter))
    rule_decision, rule_elapsed = await _safe_run(reporter, "RULE 시나리오", run_rule_scenario(reporter))
    fallback_decision, fallback_elapsed = await _safe_run(
        reporter, "FALLBACK 시나리오", run_fallback_scenario(reporter)
    )

    await run_failure_scenario(reporter, "3-1. 잘못된 모델 ID (실호출)", patch_invalid_model)
    await run_failure_scenario(
        reporter, "3-2. InvokeModel 권한 없음 — 차단된 모델로 실제 AccessDenied 유도", patch_blocked_model
    )
    await run_failure_scenario(reporter, "3-3. Timeout (실호출, timeout=0 강제)", patch_timeout)
    await run_failure_scenario(reporter, "3-4. 구조화 출력 실패 (mock)", patch_structured_output_failure)

    ok = reporter.summary()

    report = {
        "region": region,
        "iam_role": role_name,
        "model_id": get_ai_settings().bedrock_model_id,
        "agent": _decision_summary(agent_decision, agent_elapsed),
        "rule": _decision_summary(rule_decision, rule_elapsed),
        "fallback": _decision_summary(fallback_decision, fallback_elapsed),
    }
    print("\n=== 요약(JSON) ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
