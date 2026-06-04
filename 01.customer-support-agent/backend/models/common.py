from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """프로젝트 공통 에러 응답 형식.

    성공 응답과 동일한 {data, isSuccess, code, message} 봉투(envelope)를 유지한다.
    성공/실패가 같은 키 구조를 가지므로 클라이언트가 분기하기 쉽다.

      - data:      항상 null (에러 시 페이로드 없음)
      - isSuccess: 항상 False
      - code:      에러 분류 코드 (예: "HTTP_400", "HTTP_404", "VALIDATION_ERROR")
      - message:   사람이 읽을 수 있는 상세 메시지
    """

    data: None = None
    isSuccess: bool = False
    code: str
    message: str
