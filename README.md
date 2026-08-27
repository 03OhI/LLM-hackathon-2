# LLM-hackathon

팀 성향 기반 모임 궁합 분석기 프로젝트

## 📁 프로젝트 구조

```
.
├── src/                          # 소스 코드
│   ├── app.py                   # 메인 애플리케이션
│   ├── bedrock_faiss_rag_chatbot.py  # RAG 챗봇
│   ├── bedrock_faiss_indexer.py      # FAISS 인덱서
│   ├── bedrock_simple_test.py        # Bedrock 테스트
│   └── test_embeddings.py            # 임베딩 테스트
│
├── data/                         # 데이터 파일
│   └── RAG/                     # RAG 관련 데이터
│       └── RAG/                 # RAG 문서 및 설정
│           ├── AXIS_GROUNDING.md
│           ├── chemistry.py
│           ├── SPEC (1).md
│           ├── SURVEY24.md
│           ├── TYPES16.md
│           └── 설문_학술근거_기준표.md
│
├── docs/                         # 문서
│   ├── SPEC.md                  # 상세 설계 명세서
│   ├── TEAM_GUIDE.html          # 팀 가이드
│   └── [공지] 2026 호남권 SW중심대학 LLM해커톤 운영 계획안(2차수정).pdf
│
├── config/                       # 설정 파일
│   └── hackathon-e1-t02-key.pem # AWS 키
│
├── requirements.txt              # Python 의존성
└── .gitignore                   # Git 제외 파일

```

## 🚀 시작하기

### 필요 사항
- Python 3.8+
- AWS 계정 및 Bedrock 접근 권한

### 설치

```bash
pip install -r requirements.txt
```

### 실행

```bash
python src/app.py
```

## 📖 문서

자세한 설계 명세는 [docs/SPEC.md](docs/SPEC.md)를 참조하세요.

## 🔐 보안

- `config/` 폴더의 키 파일은 절대 공유하지 마세요
- `.gitignore`에 민감한 파일이 포함되어 있는지 확인하세요
