"""
Bedrock 실호출 pytest 진입점 (마커: bedrock_live).

기본 `pytest`에서는 backend/pytest.ini의 addopts(-m "not bedrock_live")가 이
파일의 테스트를 전부 제외한다. 실제 AWS 호출을 검증하려면 다음 중 하나로
명시적으로 실행한다.

    pytest -m bedrock_live
    python -m evals.bedrock_quest_smoke

AWS 자격 증명이 있는 환경(EC2 인스턴스 프로파일 등)에서만 통과한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals import bedrock_quest_smoke as smoke

pytestmark = pytest.mark.bedrock_live


@pytest.mark.asyncio
async def test_agent_path_real_bedrock():
    reporter = smoke.Reporter()
    decision, _elapsed = await smoke.run_agent_scenario(reporter)
    assert decision.assignment_source == "AGENT"
    assert all(r.passed for r in reporter.results)


@pytest.mark.asyncio
async def test_rule_path_skips_bedrock():
    reporter = smoke.Reporter()
    decision, _elapsed = await smoke.run_rule_scenario(reporter)
    assert decision.assignment_source == "RULE"
    assert all(r.passed for r in reporter.results)


@pytest.mark.asyncio
async def test_fallback_path_no_bedrock():
    reporter = smoke.Reporter()
    decision, _elapsed = await smoke.run_fallback_scenario(reporter)
    assert decision.assignment_source == "FALLBACK"
    assert all(r.passed for r in reporter.results)


@pytest.mark.asyncio
async def test_invalid_model_id_falls_back():
    reporter = smoke.Reporter()
    decision, _elapsed, _errs = await smoke.run_failure_scenario(
        reporter, "invalid_model_id", smoke.patch_invalid_model
    )
    assert decision.assignment_source == "FALLBACK"


@pytest.mark.asyncio
async def test_blocked_model_access_denied_falls_back():
    reporter = smoke.Reporter()
    decision, _elapsed, _errs = await smoke.run_failure_scenario(
        reporter, "blocked_model", smoke.patch_blocked_model
    )
    assert decision.assignment_source == "FALLBACK"


@pytest.mark.asyncio
async def test_timeout_falls_back():
    reporter = smoke.Reporter()
    decision, _elapsed, _errs = await smoke.run_failure_scenario(reporter, "timeout", smoke.patch_timeout)
    assert decision.assignment_source == "FALLBACK"


@pytest.mark.asyncio
async def test_structured_output_failure_mock_falls_back():
    reporter = smoke.Reporter()
    decision, _elapsed, _errs = await smoke.run_failure_scenario(
        reporter, "structured_output_failure", smoke.patch_structured_output_failure
    )
    assert decision.assignment_source == "FALLBACK"
