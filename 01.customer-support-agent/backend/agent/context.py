"""
Phase 3 Step 1: 요청 컨텍스트 (AgentContext)

목적:
  - 요청마다 전달되는 사용자 정보를 담는 데이터 클래스
  - user_id: 장기 기억(Long-term Memory) 조회/저장 시 사용자 식별
  - user_tier: (Phase 5 이후) 프리미엄 고객 우선 처리 등 비즈니스 로직에 활용

왜 dataclass를 쓰는가:
  dict보다 타입이 명확하고 IDE 자동완성 지원.
  context["user_id"] → context.user_id (오타 방지)
"""

from dataclasses import dataclass


@dataclass
class AgentContext:
    """Agent 실행 시 요청별로 전달되는 컨텍스트."""
    user_id: str = "anonymous"
    user_tier: str = "standard"   # standard, premium
