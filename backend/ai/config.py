"""
AI 설정 모듈

Amazon Bedrock 모델 설정과 LangChain ChatBedrockConverse 초기화를 담당한다.
- 환경 변수 기반 모델 ID 관리
- Bedrock 클라이언트에 region_name을 하드코딩하지 않음
- EC2 인스턴스 프로파일의 기본 자격 증명 체인 사용
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """AI 관련 환경 변수 설정"""

    # 팀 가이드의 허용 글로벌 추론 프로파일. 환경변수 BEDROCK_MODEL_ID로 교체 가능.
    bedrock_model_id: str = "global.anthropic.claude-sonnet-5"
    bedrock_temperature: float = 0
    bedrock_max_tokens: int = 800
    bedrock_timeout: int = 30  # seconds
    bedrock_max_retries: int = 1

    # 프롬프트 버전 관리
    team_prompt_version: str = "team_comment_v1"
    private_prompt_version: str = "private_insight_v1"
    quest_prompt_version: str = "quest_select_v1"

    # 퀘스트 배정: 후보가 1개면 Bedrock 호출을 생략하고 결정론적으로 선택
    quest_skip_bedrock_for_single_candidate: bool = True

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_ai_settings() -> AISettings:
    """싱글톤 설정 인스턴스 반환"""
    return AISettings()


def get_chat_model():
    """LangChain ChatBedrockConverse 인스턴스를 생성한다.

    - region_name을 하드코딩하지 않고 boto3 기본 체인을 따른다.
    - EC2에서는 인스턴스 프로파일이 자동으로 자격 증명을 제공한다.
    """
    from langchain_aws import ChatBedrockConverse

    settings = get_ai_settings()

    chat_model = ChatBedrockConverse(
        model_id=settings.bedrock_model_id,
        temperature=settings.bedrock_temperature,
        max_tokens=settings.bedrock_max_tokens,
    )

    return chat_model


def get_structured_model():
    """구조화 출력을 지원하는 모델 인스턴스를 반환한다."""
    from .schemas import GeneratedInsight

    chat_model = get_chat_model()
    return chat_model.with_structured_output(GeneratedInsight)
