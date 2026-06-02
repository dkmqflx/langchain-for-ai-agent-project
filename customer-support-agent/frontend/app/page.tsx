"use client";

import { useRef, useState } from "react";
import {
  ChatEvent,
  confirmChat,
  streamChat,
} from "@/lib/chat";

type Role = "user" | "assistant";
interface Message {
  role: Role;
  content: string;
}
interface Pending {
  tool: string;
  args: Record<string, unknown>;
}

const USER_ID = "demo-user"; // 학습용 고정 사용자

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const threadId = useRef<string>(crypto.randomUUID());

  // 마지막 assistant 말풍선의 content에 텍스트를 누적/설정
  function upsertAssistant(updater: (prev: string) => string) {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === "assistant") {
        const copy = [...prev];
        copy[copy.length - 1] = { role: "assistant", content: updater(last.content) };
        return copy;
      }
      return [...prev, { role: "assistant", content: updater("") }];
    });
  }

  function handleEvent(e: ChatEvent) {
    switch (e.type) {
      case "token":
        upsertAssistant((prev) => prev + e.content);
        break;
      case "message":
        upsertAssistant(() => e.response);
        break;
      case "blocked":
        upsertAssistant(() => `⚠️ ${e.response}`);
        break;
      case "confirmation_required":
        setPending({ tool: e.tool, args: e.args });
        break;
      case "error":
        upsertAssistant(() => `❌ 오류: ${e.detail}`);
        break;
      case "done":
        break;
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setBusy(true);
    try {
      await streamChat(
        { message: text, thread_id: threadId.current, user_id: USER_ID },
        handleEvent,
      );
    } catch (err) {
      upsertAssistant(() => `❌ 연결 오류: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: "approve" | "reject") {
    if (!pending) return;
    setBusy(true);
    try {
      const { response } = await confirmChat({
        thread_id: threadId.current,
        decision,
        user_id: USER_ID,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ 오류: ${String(err)}` },
      ]);
    } finally {
      setPending(null);
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <h1 className="mb-4 text-xl font-bold">고객 지원 챗봇</h1>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-gray-200 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-gray-400">메시지를 입력해 대화를 시작하세요.</p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={
                "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm " +
                (m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900")
              }
            >
              {m.content || "…"}
            </div>
          </div>
        ))}
      </div>

      {pending && (
        <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="mb-2 text-sm font-medium">
            환불 신청을 접수할까요? ({JSON.stringify(pending.args)})
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => decide("approve")}
              disabled={busy}
              className="rounded-md bg-amber-600 px-3 py-1 text-sm text-white disabled:opacity-50"
            >
              확인(접수)
            </button>
            <button
              onClick={() => decide("reject")}
              disabled={busy}
              className="rounded-md bg-gray-300 px-3 py-1 text-sm disabled:opacity-50"
            >
              취소
            </button>
          </div>
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
          placeholder="메시지를 입력하세요"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          전송
        </button>
      </div>
    </main>
  );
}
