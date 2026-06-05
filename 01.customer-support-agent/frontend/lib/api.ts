/**
 * FastAPI 백엔드 호출용 공통 헬퍼.
 *
 * 스트리밍 채팅(/chat/stream)은 AI SDK의 useChat이 직접 다루므로 여기서 처리하지 않는다.
 * 이 모듈은 JSON 응답을 주는 비스트리밍 엔드포인트
 * (/upload, /documents, /chat/confirm, /pending, /approve, /refunds)용이다.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * 백엔드 공통 응답 봉투.
 * 모든 엔드포인트가 { data, isSuccess, code, message } 형태로 응답한다.
 */
export interface ApiEnvelope<T> {
  data: T;
  isSuccess: boolean;
  code: string;
  message: string;
}

/** apiFetch가 실패 시 던지는 에러 (백엔드 message/code 보존). */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * JSON 엔드포인트를 호출하고 봉투를 벗겨 data만 반환한다.
 * 네트워크/HTTP 오류나 isSuccess=false면 ApiError를 던진다.
 *
 * @example
 *   const docs = await apiFetch<{ documents: Doc[] }>("/documents");
 */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  let body: ApiEnvelope<T> | { detail?: string } | null = null;
  try {
    body = await res.json();
  } catch {
    // JSON이 아닌 응답 (예: 502) — 아래에서 status로 처리
  }

  if (!res.ok) {
    const detail =
      (body && "detail" in body && body.detail) || `요청 실패 (${res.status})`;
    throw new ApiError(detail, res.status);
  }

  const envelope = body as ApiEnvelope<T>;
  if (!envelope?.isSuccess) {
    throw new ApiError(
      envelope?.message ?? "알 수 없는 오류",
      res.status,
      envelope?.code,
    );
  }

  return envelope.data;
}
