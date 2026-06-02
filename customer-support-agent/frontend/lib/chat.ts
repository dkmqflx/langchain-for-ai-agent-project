// 백엔드 /chat/stream SSE 호출 + 파싱. UI(page.tsx)와 분리.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// 백엔드 이벤트 프로토콜과 1:1 대응
export type ChatEvent =
  | { type: "token"; content: string }
  | { type: "message"; response: string; status: string }
  | { type: "blocked"; response: string }
  | { type: "confirmation_required"; tool: string; args: Record<string, unknown> }
  | { type: "done"; status: string }
  | { type: "error"; detail: string };

// 한 개의 SSE 블록("event: x\ndata: {...}")을 ChatEvent로 변환
function parseSseBlock(block: string): ChatEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { type: event, ...data } as ChatEvent;
  } catch {
    return null;
  }
}

// /chat/stream 을 호출하고 각 이벤트를 onEvent 콜백으로 전달
export async function streamChat(
  body: { message: string; thread_id: string; user_id: string },
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 이벤트는 빈 줄로 구분. sse-starlette는 CRLF(\r\n)를 쓰므로
    // 구분자가 "\r\n\r\n"이다. LF 전용("\n\n") 환경도 함께 처리.
    const blocks = buffer.split(/\r\n\r\n|\n\n/);
    buffer = blocks.pop() ?? ""; // 마지막 미완성 블록은 보관
    for (const block of blocks) {
      if (!block.trim()) continue;
      const evt = parseSseBlock(block);
      if (evt) onEvent(evt);
    }
  }
}

// 환불 확인/취소 (기존 비스트리밍 엔드포인트)
export async function confirmChat(body: {
  thread_id: string;
  decision: "approve" | "reject";
  user_id: string;
}): Promise<{ response: string; status: string }> {
  const res = await fetch(`${API_URL}/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  return { response: json.data.response, status: json.data.status };
}
