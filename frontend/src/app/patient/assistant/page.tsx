"use client";

// Tab "Capy AI" - port tu capyphone.js::renderAI(). Giu NGUYEN toan bo
// logic chat that dang chay (useChatMessage -> API that, lich su hoi thoai
// luu localStorage qua lib/chat-history, luong "bao khong on" tu tab Hom
// nay); chi thay lop giao dien.
//
// Ban mau tra loi bang regex hard-code ("Tuan nay 23/25 lieu, 92%") - o day
// van la mo hinh that tra loi, nen khong co cau tra loi dung san nao.

import { useEffect, useRef, useState } from "react";
import { History, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ChatMessage } from "@/components/chat-message";
import { ChatError } from "@/components/chat-error";
import { useChatMessage } from "@/hooks/use-chat";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";
import {
  type Conversation,
  createConversation,
  formatConversationTime,
  formatMessageTime,
  loadActiveId,
  loadConversations,
  saveActiveId,
  saveConversations,
  titleFromMessage,
} from "@/lib/chat-history";

const SUGGESTED_PROMPTS = [
  "Liều tiếp theo lúc mấy giờ?",
  "Tôi đã uống thuốc sáng chưa?",
  "Tuần này tôi làm tốt không?",
  "Tôi tăng liều được không?",
];

export default function AssistantPage() {
  const { symptomCheckPending, clearSymptomCheck } = useProto();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [plusOpen, setPlusOpen] = useState(false);
  const [input, setInput] = useState("");
  const lastQuestion = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const { user, accessToken } = useAuth();
  const { mutate, isPending, isError, error, reset } = useChatMessage(accessToken);

  useEffect(() => {
    const stored = loadConversations();
    const storedActive = loadActiveId();
    if (stored.length === 0) {
      const first = createConversation();
      setConversations([first]);
      setActiveId(first.id);
      saveConversations([first]);
      saveActiveId(first.id);
    } else {
      setConversations(stored);
      const fallback = stored[0]?.id ?? null;
      setActiveId(
        storedActive && stored.some((c) => c.id === storedActive) ? storedActive : fallback,
      );
    }
  }, []);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const messages = active?.messages ?? [];

  const appendMessage = (convId: string, role: "user" | "assistant", content: string) => {
    const now = new Date().toISOString();
    setConversations((prev) => {
      const next = prev.map((c) => {
        if (c.id !== convId) return c;
        const newMessages = [...c.messages, { id: crypto.randomUUID(), role, content, at: now }];
        const title =
          c.title === "Hội thoại mới" && role === "user" ? titleFromMessage(content) : c.title;
        return { ...c, messages: newMessages, updatedAt: now, title };
      });
      saveConversations(next);
      return next;
    });
  };

  useEffect(() => {
    if (!symptomCheckPending || !activeId) return;
    appendMessage(
      activeId,
      "assistant",
      "Bạn vừa cho biết hôm nay cảm thấy không ổn. Hãy mô tả chi tiết triệu chứng bạn đang gặp (vị trí, mức độ, từ khi nào, kèm dấu hiệu gì khác) để tôi hỗ trợ và báo cho bác sĩ nhé.",
    );
    clearSymptomCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symptomCheckPending, activeId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, isPending]);

  const submit = (content: string) => {
    if (!content.trim() || isPending || !activeId) return;
    lastQuestion.current = content;
    appendMessage(activeId, "user", content);
    setInput("");
    reset();
    mutate(
      { patient_id: user?.patient_id ?? "", message: content },
      {
        onSuccess: (data) => {
          appendMessage(activeId, "assistant", data.reply);
        },
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const newConversation = () => {
    if (active && active.messages.length === 0) {
      setHistoryOpen(false);
      return;
    }
    const conv = createConversation();
    const next = [conv, ...conversations];
    setConversations(next);
    saveConversations(next);
    setActiveId(conv.id);
    saveActiveId(conv.id);
    setHistoryOpen(false);
  };

  const selectConversation = (id: string) => {
    setActiveId(id);
    saveActiveId(id);
    setHistoryOpen(false);
  };

  const sortedHistory = [...conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  return (
    <div className="flex h-full min-h-0 flex-col gap-3.5">
      <header className="flex shrink-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display m-0 text-[26px] font-extrabold leading-[1.1] text-[#16386E]">
            Capy AI
          </h1>
          <p className="m-0 mt-0.5 text-[12px] text-[#62708A]">
            Đọc lịch thuốc &amp; ghi chú của bạn
          </p>
        </div>
        <button
          onClick={() => setHistoryOpen(true)}
          aria-label="Lịch sử hội thoại"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white text-[#62708A]"
        >
          <History className="h-4 w-4" />
        </button>
      </header>

      <div
        ref={scrollRef}
        className="capy-scroll flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto"
      >
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} at={formatMessageTime(m.at)} />
        ))}

        {isPending && (
          <div
            className="font-mono self-start px-[15px] py-[13px] text-[13px]"
            style={{ background: "#E4DDFB", color: "#4B3E86", borderRadius: "20px 20px 20px 6px" }}
          >
            Capy đang xem lịch của bạn…
          </div>
        )}

        {isError && (
          <ChatError
            error={error instanceof Error ? error.message : "Không thể kết nối tới trợ lý AI."}
            onRetry={() => submit(lastQuestion.current)}
          />
        )}
      </div>

      <div className="mt-3 flex shrink-0 gap-2 border-t border-border pt-3">
        <Textarea
          rows={1}
          placeholder="Nhập câu hỏi..."
          aria-label="Nhập câu hỏi cho trợ lý AI"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isPending}
          className="resize-none"
        />
        <Button
          size="icon"
          aria-label="Gửi câu hỏi"
          disabled={isPending || !input.trim()}
          onClick={() => submit(input)}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>

      {historyOpen && (
        <div className="absolute inset-0 z-50">
          <div
            className="absolute inset-0 bg-[rgba(15,26,45,.42)]"
            onClick={() => setHistoryOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 right-0 flex w-[85%] max-w-[320px] flex-col bg-[#F1F1F6] shadow-2xl">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#E7EBF3] bg-white p-4">
              <p className="font-display m-0 font-bold text-[#16386E]">Lịch sử hội thoại</p>
              <button onClick={() => setHistoryOpen(false)} aria-label="Đóng">
                <X className="h-4 w-4 text-[#62708A]" />
              </button>
            </div>

            <div className="shrink-0 p-4 pb-2">
              <Button className="w-full rounded-2xl" onClick={newConversation}>
                <Plus className="mr-1 h-4 w-4" /> Hội thoại mới
              </Button>
            </div>

            <div className="capy-scroll flex-1 space-y-1.5 overflow-y-auto p-4 pt-2">
              {sortedHistory.length === 0 && (
                <p className="text-[13px] text-[#5B6A85]">Chưa có hội thoại nào.</p>
              )}
              {sortedHistory.map((c) => (
                <button
                  key={c.id}
                  onClick={() => selectConversation(c.id)}
                  className="block w-full rounded-2xl px-3 py-2.5 text-left text-[13px] transition-colors"
                  style={
                    c.id === activeId
                      ? { background: "#CFE6FF", color: "#16386E", fontWeight: 600 }
                      : { background: "#FFFFFF" }
                  }
                >
                  <p className="m-0 truncate">{c.title}</p>
                  <p className="font-mono m-0 mt-0.5 text-[10px] text-[#62708A]">
                    {formatConversationTime(c.updatedAt)} · {c.messages.length} tin nhắn
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
