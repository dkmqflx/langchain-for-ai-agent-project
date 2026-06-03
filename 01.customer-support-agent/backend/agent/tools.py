"""
Phase 2 Step 1: 검색 도구 (Search Tool)

목적:
  - Agent가 문서를 검색할 때 사용하는 도구 정의
  - Hybrid Search = BM25(키워드) + Vector(의미) 혼합 검색

왜 Hybrid Search인가:
  BM25만 쓰면:
    - "환불" 이라는 단어가 정확히 있어야 검색됨
    - "반품" 이라고 하면 못 찾음 (키워드 불일치)

  Vector만 쓰면:
    - 의미로 찾으므로 "반품"도 "환불"과 연결됨
    - 하지만 고유명사(제품번호, 주문번호)는 의미가 없어서 못 찾음

  Hybrid (BM25 + Vector):
    - 키워드도 되고, 의미도 됨 → 두 방식의 장점을 합침
    - RRF(Reciprocal Rank Fusion): 두 검색 결과를 순위 기반으로 합산

RRF 알고리즘:
  BM25 결과:   [A(1위), B(2위), C(3위)]
  Vector 결과: [B(1위), C(2위), D(3위)]
  RRF 합산:    B가 양쪽에서 높은 순위 → 최종 1위

BM25 인덱스 관리:
  - 앱 시작 시: pgvector 전체 문서 로드 → BM25 인덱스 빌드
  - 새 문서 업로드 시: rebuild_bm25() 호출 → 인덱스 재빌드
  - 문서가 없을 경우: Vector만 사용 (graceful fallback)

제네릭 타입 어노테이션 (ToolRuntime[AgentContext]):
  - ToolRuntime은 LangChain이 제공하는 제네릭 클래스 (Generic[T])
    class ToolRuntime(Generic[T]):
        context: T           # T는 어떤 타입이든 가능
        store: InMemoryStore

  - [AgentContext]는 우리가 제네릭 파라미터를 구체화한 것
    ToolRuntime[AgentContext] = "context를 AgentContext 타입으로 지정"
    마치 List[str], Dict[str, int]처럼 generic을 구체화하는 것과 동일

  - Python은 TypeScript와 달리 제네릭을 <> 대신 [] 문법 사용
    (Python은 <, >를 이미 비교 연산자로 사용 중이라 불가능)

  - 효과: IDE 자동완성 + 타입 체크
    runtime: ToolRuntime[AgentContext]
    → runtime.context.user_id 등이 IDE에서 인식됨 (AgentContext의 속성을 알 수 있음)
"""

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from agent.context import AgentContext
from agent.refund_store import create_request
from rag.bm25 import BM25Retriever
from rag.vectorstore import vectorstore

# [모듈 레벨 상태] BM25 인덱스 (None이면 아직 빌드 안 됨)
# 참고: 모듈 레벨에서는 그냥 변수 선언만 함. global 키워드는 함수 내에서 "이 변수를 변경하려면" 필요
# 함수에서 읽기만 할 때는 global 불필요, 쓰기(할당)할 때는 반드시 필요
_bm25_retriever: BM25Retriever | None = None


def build_bm25():
    """
    pgvector의 전체 문서를 로드해서 BM25 인덱스 빌드.

    이 함수는 두 곳에서 호출됨:
      1. main.py @app.on_event("startup") → 앱 시작 시 초기 빌드
      2. upload.py POST /upload 성공 후 → 새 문서 반영

    문서가 없을 때 (DB가 비어있음):
      → _bm25_retriever = None 유지
      → search_documents Tool에서 Vector만 사용
    """
    # global 키워드: 이 함수 내에서 모듈 레벨의 _bm25_retriever를 "변경(할당)"하려면 필수
    # 없으면 Python이 이를 로컬 변수로 해석해서 모듈 변수는 변경 안 됨
    global _bm25_retriever

    # pgvector에서 전체 문서 로드 (최대 10000개)
    # 빈 쿼리("") + 높은 k로 사실상 전체 조회
    docs = vectorstore.similarity_search("", k=10000)

    if docs:
        _bm25_retriever = BM25Retriever.from_documents(docs, k=5)
    else:
        # 문서가 없으면 BM25 인덱스 불필요
        _bm25_retriever = None


def _get_ensemble_retriever():
    """
    Hybrid Retriever 반환.

    BM25 인덱스가 있으면:
      → EnsembleRetriever (BM25 40% + Vector 60%)
    BM25 인덱스가 없으면 (문서 없음):
      → Vector Retriever만 사용

    가중치 설정 (weights=[0.4, 0.6]):
      - BM25 0.4: 키워드 검색 (정확한 단어 매칭)
      - Vector 0.6: 의미 검색 (더 중요)
      - 의미 검색에 더 높은 가중치를 두는 이유:
        고객 지원에서는 "반품"="환불" 같은 동의어 처리가 중요
    """
    vector_retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 5},
    )

    if _bm25_retriever is None:
        # BM25 인덱스가 없으면 Vector만 반환
        return vector_retriever

    return EnsembleRetriever(
        retrievers=[_bm25_retriever, vector_retriever],
        weights=[0.4, 0.6],  # BM25: 40%, Vector: 60%
    )


@tool
def search_documents(query: str) -> str:
    """
    업로드된 회사 문서에서 관련 내용을 검색합니다.

    고객 질문에 답변하기 위해 정책, 매뉴얼, FAQ 등을 검색할 때 사용하세요.
    문서에 없는 내용은 검색 결과가 비어 있을 수 있습니다.

    Args:
        query: 검색할 내용 (자연어)
              예: "환불 신청 방법", "배송 기간", "반품 정책"

    Returns:
        관련 문서 청크들 (출처 포함)
        문서가 없으면 "관련 문서를 찾을 수 없습니다." 반환
    """
    retriever = _get_ensemble_retriever()
    results = retriever.invoke(query)

    if not results:
        return "관련 문서를 찾을 수 없습니다."

    # 검색 결과를 출처와 함께 하나의 문자열로 합침
    # Agent가 이 내용을 읽고 답변을 생성함
    parts = []
    for doc in results:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "")
        parts.append(f"[출처: {source}, 페이지: {page}]\n{doc.page_content}")

    return "\n\n---\n\n".join(parts)


@tool
def save_user_preference(
    key: str,
    value: str,
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    사용자 선호도를 장기 기억에 저장합니다.

    언어 설정, 응답 스타일, 알림 방식 등 고객이 원하는 선호도를 저장할 때 사용하세요.
    저장된 선호도는 대화가 끊겨도 다음 대화에서 자동으로 반영됩니다.

    Args:
        key: 선호도 이름 (예: "language", "response_style", "notification")
        value: 선호도 값 (예: "한국어", "간결하게", "이메일")
        runtime: ToolRuntime[AgentContext]
                 - create_agent에서 자동 주입됨 (수동으로 전달 X)
                 - runtime.context: AgentContext 타입 (user_id, user_tier 접근 가능)
                 - runtime.store: InMemoryStore (선호도 저장소)

    예시:
        고객: "앞으로는 영어로만 답변해줘"
        → save_user_preference(key="language", value="English")
        → 다음 대화부터 자동으로 영어로 답변
    """
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    namespace = ("user_preferences", user_id)
    runtime.store.put(namespace, key, {"value": value})
    return f"선호도 저장 완료: {key} = {value}"


@tool
def get_user_preferences(runtime: ToolRuntime[AgentContext]) -> str:
    """
    저장된 사용자 선호도를 모두 조회합니다.

    현재 고객의 저장된 모든 선호도를 확인할 때 사용하세요.
    선호도가 없으면 그 사실을 알려줍니다.

    Args:
        runtime: ToolRuntime[AgentContext]
                 - create_agent에서 자동 주입됨 (수동으로 전달 X)
                 - runtime.context: AgentContext 타입 (user_id, user_tier 접근 가능)
                 - runtime.store: InMemoryStore (선호도 저장소)
    """
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    namespace = ("user_preferences", user_id)
    items = runtime.store.search(namespace)

    if not items:
        return "저장된 선호도가 없습니다."

    return "\n".join(f"{item.key}: {item.value['value']}" for item in items)


@tool
def submit_refund_request(
    order_id: str,
    amount: float,
    reason: str,
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    고객의 환불·결제 취소 '신청'을 접수합니다.

    환불, 결제 취소 등 금전이 오가는 작업에 사용하세요.
    이 도구는 실제 환불을 즉시 실행하지 않고, 환불 '신청'을 접수만 합니다 (status=pending).
    HumanInTheLoopMiddleware가 이 도구 실행 직전에 일시정지시켜 고객 본인의 확인을 받고,
    고객이 확인하면 이 함수가 실행되어 신청 레코드가 생성됩니다.
    실제 환불 여부는 이후 관리자가 비동기로 승인/거절합니다.

    Args:
        order_id: 환불 대상 주문번호 (예: "ORD-123")
        amount: 환불 금액 (원 단위, 예: 50000)
        reason: 환불 사유 (예: "제품 불량", "단순 변심")
        runtime: ToolRuntime[AgentContext] — user_id 추출용 (자동 주입)

    Returns:
        신청 접수 결과 메시지 (신청번호 포함)
    """
    user_id = runtime.context.user_id if runtime.context else "anonymous"
    req = create_request(user_id=user_id, order_id=order_id, amount=amount, reason=reason)
    return (
        f"환불 신청이 접수되었습니다. 신청번호: {req.id}, 주문번호: {order_id}, "
        f"금액: {amount:,.0f}원. 관리자 검토 후 결과를 알려드리겠습니다."
    )
