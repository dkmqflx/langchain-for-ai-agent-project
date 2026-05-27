# 프로젝트 1. 기업 문서 기반 AI 고객 지원 에이전트

> 제품 매뉴얼, FAQ, 정책 PDF를 업로드하면 고객 문의에 자동 답변하는 B2B SaaS.  
> RAG + Agentic RAG + Guardrail + Memory를 모두 결합한 풀스택 AI 에이전트.

---

## 1. 최종 목표 (완성 시 동작)

1. 관리자가 제품 문서(PDF, TXT 등)를 업로드한다.
2. 시스템이 문서를 자동으로 청킹 → 임베딩 → PostgreSQL(pgvector)에 저장한다.
3. 고객이 채팅창에 질문을 입력한다.
4. 에이전트가 필요 시 문서를 검색(Agentic RAG)하거나 외부 API를 호출해 답변한다.
5. 민감 작업(환불 처리 등)은 Human-in-the-loop로 관리자 승인 후 실행된다.
6. 개인정보(이메일, 카드번호)는 자동 마스킹된다.
7. LLM 답변이 할루시네이션인지 After Agent Guardrail이 검증·교정한다.
8. 재방문 고객의 선호도는 Long-term Memory로 유지된다.

---

## 2. 기술 스택

| 영역 | 기술 |
| :--- | :--- |
| **LLM** | OpenAI GPT-4o (메인), GPT-4o-mini (Guardrail 감시자) |
| **Agent 프레임워크** | LangChain |
| **Vector DB** | pgvector (PostgreSQL extension) |
| **키워드 검색** | BM25 (Hybrid Search) |
| **임베딩** | OpenAI text-embedding-3-small + CacheBackedEmbeddings |
| **백엔드** | FastAPI + Python |
| **프론트엔드** | Next.js 15 (App Router) + Tailwind CSS |
| **배포 - 백엔드** | AWS EC2 + RDS PostgreSQL + pgvector |
| **배포 - 프론트엔드** | Vercel |
| **모니터링** | LangSmith + CloudWatch |
| **CI/CD** | GitHub Actions |

---

## 3. 프로젝트 폴더 구조

```
customer-support-agent/
├── backend/
│   ├── main.py                  # FastAPI 진입점
│   ├── agent/
│   │   ├── agent.py             # create_agent 설정
│   │   ├── tools.py             # 검색 Tool, 환불 Tool 등
│   │   ├── middleware.py        # PII, Guardrail, Memory 미들웨어
│   │   └── context.py           # Context dataclass 정의
│   ├── rag/
│   │   ├── loader.py            # PDF/TXT 로딩
│   │   ├── splitter.py          # 청크 분할
│   │   ├── embedder.py          # 임베딩 + 캐싱
│   │   └── vectorstore.py       # pgvector 저장/조회
│   ├── api/
│   │   ├── chat.py              # POST /chat 엔드포인트
│   │   ├── upload.py            # POST /upload 엔드포인트
│   │   └── approve.py           # POST /approve 엔드포인트 (Human-in-the-loop)
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # 채팅 메인 화면
│   │   ├── admin/page.tsx       # 문서 업로드 관리자 화면
│   │   └── approve/page.tsx     # Human-in-the-loop 승인 화면
│   └── ...
└── README.md
```

---

## 4. 시스템 아키텍처 (데이터 흐름)

### 4.1 문서 인덱싱 흐름 (관리자)

```
PDF 업로드
  ↓
Load (PDFPlumber / PyMuPDF)
  ↓
Split (RecursiveCharacterTextSplitter, chunk_size=500, overlap=50)
  ↓
Embed (OpenAIEmbeddings + CacheBackedEmbeddings)
  ↓
Store (PostgreSQL + pgvector)
```

### 4.2 고객 질문 처리 흐름 (런타임)

```
고객 질문 입력
  ↓
Before Agent Guardrail (욕설/PII 차단)
  ↓
에이전트 추론 시작
  ├── 외부 정보 필요? → RAG Tool 호출 (Agentic RAG)
  │     ├── Hybrid Search (BM25 + Vector)
  │     └── MMR로 다양한 문서 검색
  ├── 환불/계정 변경? → Human-in-the-loop 발동 (일시정지)
  │     └── 관리자 승인 후 재개
  └── 일반 질문? → 직접 답변 생성
  ↓
After Agent Guardrail (할루시네이션 검증 → 교정)
  ↓
PII 마스킹 (이메일, 카드번호)
  ↓
최종 답변 반환
```

---

## 5. 구현 단계별 계획

### Phase 1. RAG 파이프라인 구축

**목표**: 문서를 PostgreSQL(pgvector)에 저장하고 검색하는 기반 구축

- [ ] PDFPlumber / PyMuPDF 로더 구현 (`rag/loader.py`)
- [ ] RecursiveCharacterTextSplitter 설정 (`rag/splitter.py`)
  - `chunk_size=500`, `chunk_overlap=50`
- [ ] OpenAIEmbeddings + CacheBackedEmbeddings 연결 (`rag/embedder.py`)
- [ ] pgvector 저장/조회 함수 구현 (`rag/vectorstore.py`)
  ```python
  from langchain_postgres import PGVector

  vectorstore = PGVector(
      embeddings=embeddings,
      collection_name="documents",
      connection=DATABASE_URL,
  )
  ```
- [ ] 문서 업로드 API 구현 (`api/upload.py`)
  - `POST /upload` → 파일 수신 → RAG 파이프라인 실행
- **검증**: 샘플 PDF 업로드 후 PostgreSQL `langchain_pg_embedding` 테이블에 청크가 저장되는지 확인

---

### Phase 2. 기본 Agent + RAG Tool 연결

**목표**: 에이전트가 질문을 받으면 문서에서 검색해 답변

- [ ] RAG 검색 Tool 구현 (`agent/tools.py`)
  ```python
  @tool
  def search_documents(query: str) -> str:
      """회사 문서(매뉴얼, FAQ, 정책)에서 관련 내용을 검색합니다."""
  ```
- [ ] Hybrid Search 구현: BM25 + Vector 결과 합산 (RRF 알고리즘)
- [ ] MMR 검색 설정: `search_type="mmr"`, `k=5`
- [ ] `create_agent` 기본 설정 (`agent/agent.py`)
- [ ] 채팅 API 구현 (`api/chat.py`)
  - `POST /chat` → `{ message, thread_id, user_id }` 수신
- **검증**: "환불 정책이 어떻게 돼요?" 질문 시 문서에서 검색해 답변하는지 확인

---

### Phase 3. Short-term Memory + Long-term Memory

**목표**: 대화 맥락 유지 + 고객 선호도 기억

- [ ] InMemorySaver로 Short-term Memory 연결
  - `thread_id` 기반 대화 세션 유지
- [ ] InMemoryStore(또는 Redis)로 Long-term Memory 구현
- [ ] `get_user_preference` / `save_user_preference` Tool 구현
  ```python
  @tool
  def save_user_preference(preference: str, runtime: ToolRuntime) -> str:
      """고객의 선호도나 중요 정보를 장기 기억에 저장합니다."""
  ```
- [ ] Context dataclass 정의 (`agent/context.py`)
  ```python
  @dataclass
  class Context:
      user_id: str
      user_tier: str  # "guest" | "member" | "vip"
  ```
- [ ] `inject_memory` Middleware: 장기 메모리를 system prompt에 자동 주입
- **검증**: 두 번째 방문 시 "저번에 말씀하신 것처럼..." 식의 개인화 답변 확인

---

### Phase 4. Middleware (PII + Guardrail)

**목표**: 안전하고 신뢰할 수 있는 에이전트 구축

- [ ] PII Detection Middleware 적용 (`middleware.py`)
  - 이메일: `redact` 전략
  - 카드번호: `mask` 전략 (마지막 4자리만 노출)
- [ ] Before Agent Guardrail: 욕설/부적절 키워드 차단
  ```python
  @before_agent(can_jump_to=["end"])
  def input_guardrail(state, runtime): ...
  ```
- [ ] After Agent Guardrail: LLM 기반 할루시네이션 검증
  ```python
  @after_agent
  def hallucination_guardrail(state, runtime):
      # 감시자 모델(GPT-4o-mini)에게 답변 검증 요청
      # "HALLUCINATION" 감지 시 답변 교정
  ```
- **검증**: 신용카드 번호 입력 시 마스킹, 문서에 없는 내용 질문 시 교정 답변 확인

---

### Phase 5. Human-in-the-loop

**목표**: 민감 작업(환불, 계정 변경)은 관리자 승인 필요

- [ ] `process_refund` Tool 구현 (실제 환불 처리 시뮬레이션)
- [ ] HumanInTheLoopMiddleware 설정
  ```python
  HumanInTheLoopMiddleware(
      interrupt_on={
          "process_refund": {"allowed_decisions": ["approve", "reject"]},
      }
  )
  ```
- [ ] 승인 대기 API 구현 (`api/approve.py`)
  - `GET /pending`: 승인 대기 목록
  - `POST /approve`: `{ thread_id, decision }` → 에이전트 재개
- [ ] 관리자 승인 화면 구현 (`frontend/app/approve/page.tsx`)
- **검증**: 환불 요청 시 에이전트 일시정지 → 관리자 승인 후 처리 완료 확인

---

### Phase 6. 프론트엔드 + LangSmith 연동

**목표**: 실제 배포 가능한 UI 완성 + 모니터링

- [ ] 채팅 UI 구현 (`frontend/app/page.tsx`)
  - 스트리밍 응답 (SSE 또는 WebSocket)
  - Human-in-the-loop 발동 시 "관리자 검토 중" 상태 표시
- [ ] 문서 업로드 관리자 화면 (`frontend/app/admin/page.tsx`)
  - 드래그앤드롭 파일 업로드
  - 업로드된 문서 목록 표시
- [ ] LangSmith 연동
  - 에이전트 추론 과정 추적
  - Guardrail 발동 횟수 모니터링
- **검증**: 전체 플로우 E2E 테스트

---

### Phase 7. AWS 인프라 구축 (EC2 + RDS)

**목표**: EC2에 FastAPI 배포, RDS PostgreSQL + pgvector 연동

#### 7-1. AWS 사전 준비

- [ ] AWS 계정 생성 및 프리티어 확인
- [ ] IAM 사용자 생성 (루트 계정 대신 사용)
  - 권한: EC2, RDS, VPC, CloudWatch 접근

#### 7-2. VPC 및 네트워크 설정

- [ ] VPC 생성 또는 기본 VPC 사용
- [ ] Subnet 확인 (퍼블릭 + 프라이빗)
- [ ] Internet Gateway 생성 및 VPC에 연결
- [ ] Route Table에서 외부 트래픽 허용 (0.0.0.0/0 → IGW)

#### 7-3. 보안그룹 생성

- [ ] **FastAPI 보안그룹** (EC2용)
  ```
  Inbound:
    - HTTP (80): 0.0.0.0/0 (Vercel에서 접근)
    - HTTPS (443): 0.0.0.0/0
    - SSH (22): Your_IP/32 (개인 IP만 - 보안!)
  Outbound:
    - 모든 트래픽 허용
  ```

- [ ] **RDS 보안그룹** (데이터베이스용)
  ```
  Inbound:
    - PostgreSQL (5432): FastAPI 보안그룹 선택
      (EC2에서만 RDS 접근 가능)
  Outbound:
    - 필요 없음 (데이터베이스는 수신만)
  ```

#### 7-4. RDS PostgreSQL 인스턴스 생성

- [ ] RDS 콘솔에서 PostgreSQL 데이터베이스 생성
  ```
  엔진: PostgreSQL
  버전: 15 이상
  인스턴스 클래스: t3.micro (프리티어) 또는 t3.small
  스토리지: 20GB
  DB 이름: customer_support_db
  마스터 사용자명: postgres
  마스터 암호: [강력한 암호 설정]
  ```

- [ ] **VPC 보안그룹**: RDS 보안그룹 선택
- [ ] **퍼블릭 액세스**: OFF (EC2에서만 접근)
- [ ] **백업**: 7일 유지
- [ ] **Multi-AZ**: OFF (개발 환경)

#### 7-5. RDS pgvector Extension 활성화

- [ ] RDS 인스턴스가 running 상태 대기 (5-10분)
- [ ] PostgreSQL 클라이언트로 RDS 연결
  ```bash
  psql -h your-rds-endpoint.region.rds.amazonaws.com \
       -U postgres \
       -d customer_support_db
  ```

- [ ] pgvector extension 활성화
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
  
  -- 확인
  SELECT * FROM pg_extension;
  ```

#### 7-6. EC2 인스턴스 생성

- [ ] EC2 콘솔에서 인스턴스 시작
  ```
  AMI: Ubuntu 22.04 LTS
  인스턴스 타입: t3.micro 또는 t3.small
  VPC: RDS와 동일 VPC
  Subnet: 퍼블릭 서브넷
  퍼블릭 IP: 자동 할당 활성화
  보안그룹: FastAPI 보안그룹 선택
  ```

- [ ] 키페어 생성 및 다운로드 (`.pem` 파일 안전히 보관)
  ```bash
  # 파일 권한 설정 (Linux/Mac)
  chmod 400 your-key.pem
  ```

- [ ] Elastic IP 할당 (IP 주소가 고정되도록)

#### 7-7. EC2에 FastAPI 배포

- [ ] EC2에 SSH 접속
  ```bash
  ssh -i your-key.pem ubuntu@your-ec2-public-ip
  ```

- [ ] 시스템 패키지 업데이트
  ```bash
  sudo apt update && sudo apt upgrade -y
  sudo apt install -y python3.11 python3-pip git
  ```

- [ ] 프로젝트 클론 및 설치
  ```bash
  cd /home/ubuntu
  git clone https://github.com/your-username/customer-support-agent.git
  cd customer-support-agent/backend
  pip install -r requirements.txt
  ```

- [ ] 환경변수 설정
  ```bash
  sudo nano /etc/environment
  # 또는
  export OPENAI_API_KEY="sk-..."
  export DATABASE_URL="postgresql://postgres:password@rds-endpoint:5432/customer_support_db"
  export LANGSMITH_API_KEY="ls_..."
  ```

- [ ] Uvicorn 서버 실행 테스트
  ```bash
  python -m uvicorn main:app --host 0.0.0.0 --port 80
  ```

#### 7-8. systemd로 자동 실행 설정 (EC2 재부팅 시 자동 시작)

- [ ] systemd 서비스 파일 생성
  ```bash
  sudo nano /etc/systemd/system/fastapi.service
  ```

  ```ini
  [Unit]
  Description=FastAPI Customer Support Agent
  After=network.target
  
  [Service]
  User=ubuntu
  WorkingDirectory=/home/ubuntu/customer-support-agent/backend
  Environment="PATH=/usr/local/bin:/usr/bin:/bin"
  Environment="OPENAI_API_KEY=sk-..."
  Environment="DATABASE_URL=postgresql://..."
  ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 80
  Restart=always
  
  [Install]
  WantedBy=multi-user.target
  ```

- [ ] 서비스 활성화 및 시작
  ```bash
  sudo systemctl enable fastapi
  sudo systemctl start fastapi
  sudo systemctl status fastapi
  ```

#### 7-9. GitHub Actions CI/CD 설정

- [ ] `.github/workflows/deploy.yml` 생성
  ```yaml
  name: Deploy to EC2
  
  on:
    push:
      branches: [main]
  
  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        
        - name: Deploy to EC2
          uses: appleboy/ssh-action@master
          with:
            host: ${{ secrets.EC2_HOST }}
            username: ubuntu
            key: ${{ secrets.EC2_KEY }}
            script: |
              cd /home/ubuntu/customer-support-agent
              git pull origin main
              cd backend
              pip install -r requirements.txt
              sudo systemctl restart fastapi
  ```

- [ ] GitHub Secrets 설정
  - `EC2_HOST`: EC2 Elastic IP
  - `EC2_KEY`: 키페어 `.pem` 파일 내용

#### 7-10. 프론트엔드 Vercel 배포

- [ ] 프론트엔드 환경변수 설정
  ```
  NEXT_PUBLIC_API_URL=http://your-ec2-elastic-ip
  ```

- [ ] Vercel에 배포
  ```bash
  cd frontend
  npm install
  vercel --prod
  ```

#### 7-11. CloudWatch 모니터링 설정

- [ ] EC2 상세 모니터링 활성화
- [ ] CloudWatch 대시보드 생성
  - CPU 사용률
  - 네트워크 트래픽
  - 디스크 I/O

- [ ] 알람 생성
  - CPU > 80%일 때 이메일 알림
  - RDS 스토리지 90% 초과

#### 7-12. 검증 및 테스트

- [ ] Elastic IP로 API 접근 테스트
  ```bash
  curl http://your-ec2-elastic-ip/docs
  ```

- [ ] 문서 업로드 → pgvector 저장 확인
- [ ] 채팅 API 응답 테스트
- [ ] Vercel 프론트엔드 → EC2 백엔드 통신 확인

---

## 예상 월 비용 (AWS)

| 항목 | 예상 가격 |
|:---|:---|
| **EC2 t3.micro (프리티어)** | 무료 (12개월) |
| **RDS t3.micro (프리티어)** | 무료 (12개월) |
| **데이터 전송** | $0-5 |
| **Elastic IP** | 무료 (사용 중) |
| **CloudWatch** | 무료 (1M 요청까지) |
| **합계** | **무료~5달러** (프리티어) |

프리티어 만료 후:
| 항목 | 예상 가격 |
|:---|:---|
| **EC2 t3.small** | $10/월 |
| **RDS t3.small** | $20/월 |
| **기타** | $5/월 |
| **합계** | **~$35/월** |

---

## 6. API 설계

| Method | Endpoint | 설명 |
| :--- | :--- | :--- |
| `POST` | `/upload` | PDF/TXT 업로드 → RAG 인덱싱 |
| `POST` | `/chat` | 고객 메시지 전송 → 에이전트 응답 |
| `GET` | `/pending` | Human-in-the-loop 승인 대기 목록 |
| `POST` | `/approve` | 승인/거절 결정 후 에이전트 재개 |
| `GET` | `/documents` | 업로드된 문서 목록 조회 |

### POST /chat 요청/응답 예시

```json
// Request
{
  "message": "환불 신청하고 싶어요",
  "thread_id": "session-abc123",
  "user_id": "user-001"
}

// Response (일반)
{
  "reply": "환불 정책에 따르면 구매 후 30일 이내에 신청 가능합니다...",
  "status": "completed"
}

// Response (Human-in-the-loop 발동)
{
  "reply": "환불 처리를 위해 관리자 확인이 필요합니다. 잠시만 기다려 주세요.",
  "status": "pending_approval",
  "thread_id": "session-abc123"
}
```

---

## 7. 핵심 구현 포인트 (면접 대비)

| 질문 | 답변 포인트 |
| :--- | :--- |
| "왜 Agentic RAG를 썼나요?" | 단순 질문은 검색 없이 즉시 답변 → 비용 절감. 복잡한 질문은 반복 검색으로 정확도 향상 |
| "Hybrid Search를 쓴 이유는?" | 키워드 검색(BM25)은 정확한 용어 매칭에 강하고, 벡터 검색은 의미 유사도에 강함. 결합 시 커버리지 향상 |
| "Guardrail이 왜 필요한가?" | LLM은 학습 데이터에 없는 정보를 그럴듯하게 지어내는 할루시네이션 위험이 있음. 감시자 모델로 검증 후 교정 |
| "Human-in-the-loop 구현 방식은?" | HumanInTheLoopMiddleware로 Tool 실행 직전 일시정지 → thread_id로 상태 보존 → 승인 시 재개 |
| "PII를 왜 클라이언트가 아닌 서버에서 처리하나요?" | 클라이언트 필터는 우회 가능. 서버 미들웨어는 LLM 호출 전에 반드시 실행되므로 확실한 보호 가능 |
| "왜 ChromaDB 대신 pgvector를 썼나요?" | 고객 정보, 대화 이력, 임베딩 벡터를 PostgreSQL 하나로 관리 가능. SQL JOIN으로 벡터 검색과 관계형 데이터를 결합할 수 있고, ACID 트랜잭션으로 데이터 정합성 보장. 실무 프로덕션에서 더 많이 사용되는 스택 |
| "AWS 배포 구조를 설명해 주세요" | EC2에서 FastAPI를 실행하고, RDS PostgreSQL(pgvector)를 별도 관리. VPC 내에서 EC2-RDS를 보안그룹으로 격리. Elastic IP로 고정 IP 할당. systemd와 GitHub Actions로 배포 자동화. CloudWatch로 모니터링 |
| "EC2와 RDS를 분리한 이유는?" | 컴퓨트와 데이터베이스를 분리하면 독립적으로 스케일링 가능. RDS는 AWS의 관리형 서비스라서 자동 백업, 패치, 고가용성 구성 가능. 데이터 보호 관점에서도 더 안전 |
| "보안그룹 설정에서 중요한 점은?" | 최소 권한 원칙(Principle of Least Privilege) 적용. EC2-RDS 간 통신만 열고, SSH는 개인 IP로만 접근 제한. RDS는 외부 인터넷 접근 OFF. 데이터베이스 패스워드는 GitHub Secrets로 관리 |

---

## 8. 구현 일정 (예상)

| Phase | 내용 | 예상 기간 |
| :---: | :--- | :---: |
| 1 | RAG 파이프라인 구축 (pgvector) | 3일 |
| 2 | 기본 Agent + RAG Tool | 3일 |
| 3 | Short-term + Long-term Memory | 2일 |
| 4 | PII + Guardrail Middleware | 2일 |
| 5 | Human-in-the-loop | 2일 |
| 6 | 프론트엔드 + LangSmith | 4일 |
| 7 | AWS 인프라 구축 (EC2 + RDS) | **4일** |
|   | - VPC/보안그룹 설정 | 1일 |
|   | - RDS PostgreSQL + pgvector | 1일 |
|   | - EC2 배포 + systemd 자동화 | 1일 |
|   | - GitHub Actions CI/CD | 1일 |
| **합계** | | **약 20일** |

**추가 학습**: AWS VPC, 보안그룹, IAM, CloudWatch 이해 포함
