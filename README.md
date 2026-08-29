# LLM-hackathon

팀 성향 기반 모임 궁합 분석기 프로젝트

## 📁 프로젝트 구조

```
.
├── src/                              # 초기 RAG 프로토타입 (Bedrock + FAISS)
│   ├── app.py                        # 메인 애플리케이션
│   ├── bedrock_faiss_rag_chatbot.py  # RAG 챗봇
│   ├── bedrock_faiss_indexer.py      # FAISS 인덱서
│   ├── bedrock_simple_test.py        # Bedrock 테스트
│   └── test_embeddings.py            # 임베딩 테스트
│
├── backend/                          # FastAPI 서버 + AI 파이프라인
│   ├── app/                          # API · 서비스 · 모델
│   ├── ai/                           # LangGraph 체인 · 프롬프트 · 퀘스트 배정
│   ├── knowledge_base/               # 런타임 정본 데이터 (quests.json, *.yaml)
│   ├── evals/                        # 테스트 · 평가 스크립트
│   └── deploy/                       # Dockerfile · nginx · compose
│
├── frontend/                         # Next.js 앱 (설문 · 퀘스트 · 결과 화면)
│   ├── app/                          # 라우트별 페이지
│   ├── lib/                          # API 클라이언트 · 훅
│   └── public/                       # 이미지 · 아이콘
│
├── data/                             # 제작·검수용 원본 데이터 (런타임 아님)
│   ├── quest-catalog/                # 퀘스트 카탈로그 v5.2 저작 도구
│   │   ├── quests.json               # 퀘스트 29종
│   │   ├── quest.schema.json         # JSON Schema 계약
│   │   ├── patterns.enum.json        # rule_id 어휘집
│   │   ├── topics.json               # 제작·검수 전용 토픽
│   │   ├── validate_quests.py        # 카탈로그 검증기 CLI
│   │   ├── simulate_assignment.py    # 배정 시뮬레이터
│   │   ├── SPEC_V5_CONTEST_QUEST_AGENT.md
│   │   └── MIGRATION_v5.2.md
│   └── personality-scoring/          # 성향 점수 계산 로직 원본
│       ├── likert.py  chemistry_v2.py  faultline.py
│       ├── cases.py   verify_fixes.py
│       └── evidence_map.json
│
├── docs/                             # 문서
│   ├── SPEC.md                       # 상세 설계 명세서
│   ├── TEAM_GUIDE.html               # 팀 가이드
│   └── personality-analysis/         # 성향분석 설계·근거 문서 모음
│
├── config/                           # 시크릿 (git 미추적)
│   └── hackathon-e1-t02-key.pem      # AWS 키
│
├── requirements.txt                  # Python 의존성 (프로토타입용)
└── .gitignore
```

> `data/`와 `docs/`는 사람이 읽고 고치는 원본이고, 서버가 실제로 읽는 정본은
> `backend/knowledge_base/`입니다. 두 곳은 자동 동기화되지 않습니다.

## 🚀 시작하기

### 필요 사항
- Python 3.8+
- Node.js 20+ (frontend)
- AWS 계정 및 Bedrock 접근 권한

### 설치

```bash
pip install -r requirements.txt
```

### 실행

```bash
python src/app.py
```

백엔드·프론트엔드 실행 방법은 [FRONTEND_SERVER.md](FRONTEND_SERVER.md)를 참고하세요.

## 📖 문서

자세한 설계 명세는 [docs/SPEC.md](docs/SPEC.md)를 참조하세요.
퀘스트 카탈로그 규격은 [data/quest-catalog/SPEC_V5_CONTEST_QUEST_AGENT.md](data/quest-catalog/SPEC_V5_CONTEST_QUEST_AGENT.md)에 있습니다.

## 🔐 보안

- `config/` 폴더의 키 파일은 절대 공유하지 마세요
- `.gitignore`에 민감한 파일이 포함되어 있는지 확인하세요
