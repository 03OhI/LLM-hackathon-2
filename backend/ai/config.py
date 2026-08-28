"""
AI 설정 모듈

Amazon Bedrock 모델 설정과 LangChain ChatBedrockConverse 초기화를 담당한다.
- 환경 변수 기반 모델 ID 관리
- Bedrock 클라이언트에 region_name을 하드코딩하지 않음
- EC2 인스턴스 프로파일의 기본 자격 증명 체인 사용
- botocore Config로 timeout/retry 실제 연결
"""

from __future__ import annotations

from functools import lru_cache
from typing import Type

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class AISettings(BaseSettings):
    """AI 관련 환경 변수 설정"""

    # 글로벌 추론 프로파일 ID. 팀 계정 권한에 따라 BEDROCK_MODEL_ID 환경변수로 교체 가능.
    bedrock_model_id: str = "global.anthropic.claude-sonnet-4-20250514-v1:0"
    bedrock_temperature: float = 0
    bedrock_max_tokens: int = 800
    bedrock_timeout: int = 30  # seconds — read timeout
    bedrock_connect_timeout: int = 10  # seconds — connect timeout
    bedrock_max_retries: int = 1

    # 프롬프트 버전 관리
    team_prompt_version: str = "team_snapshot_v2"
    private_prompt_version: str = "private_card_v2"

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
    - botocore Config로 timeout/retry를 실제 적용한다.
    """
    from botocore.config import Config as BotoConfig
    from langchain_aws import ChatBedrockConverse

    settings = get_ai_settings()

    boto_config = BotoConfig(
        read_timeout=settings.bedrock_timeout,
        connect_timeout=settings.bedrock_connect_timeout,
        retries={"max_attempts": settings.bedrock_max_retries, "mode": "standard"},
    )

    chat_model = ChatBedrockConverse(
        model_id=settings.bedrock_model_id,
        temperature=settings.bedrock_temperature,
        max_tokens=settings.bedrock_max_tokens,
        config=boto_config,
    )

    return chat_model


def get_structured_model(output_schema: Type[BaseModel] | None = None):
    """구조화 출력을 지원하는 모델 인스턴스를 반환한다.

    Args:
        output_schema: 출력 Pydantic 모델. None이면 TeamSnapshot을 기본 사용.
    """
    from .schemas import TeamSnapshot

    if output_schema is None:
        output_schema = TeamSnapshot

    chat_model = get_chat_model()
    return chat_model.with_structured_output(output_schema)
