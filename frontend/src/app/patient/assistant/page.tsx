"use client";

import { useEffect, useRef, useState } from "react";
import { History, Plus, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ChatMessage } from "@/components/chat-message";
import { ChatError } from "@/components/chat-error";
import { useChatMessage } from "@/hooks/use-chat";
import { DEMO_PATIENT_ID } from "@/lib/api";
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

export default function AssistantPage() {
  const { symptomCheckPending, clearSymptomCheck } = useProto();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [input, setInput] = useState("");
  const lastQuestion = useRef("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const { accessToken } = useAuth();
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
      { patient_id: DEMO_PATIENT_ID, message: content },
      {
        onSuccess: (data) => {
          appendMessage(activeId, "assistant", data.reply);
        },
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
    <div className="flex h-full min-h-0 flex-col">
      <header className="mb-4 flex shrink-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold">Trợ lý AI</h1>
          <p className="text-sm text-muted-foreground">
            Hỏi về triệu chứng, thuốc đang dùng hoặc cách chăm sóc.
          </p>
        </div>
        <button
          onClick={() => setHistoryOpen(true)}
          aria-label="Lịch sử hội thoại"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground"
        >
          <History className="h-4 w-4" />
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Gửi câu hỏi để bắt đầu trò chuyện.
          </p>
        )}
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} at={formatMessageTime(m.at)} />
        ))}
        {isPending && <p className="text-sm text-muted-foreground">Đang suy nghĩ...</p>}
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
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isPending}
          className="resize-none"
        />
        <Button size="icon" disabled={isPending || !input.trim()} onClick={() => submit(input)}>
          <Send className="h-4 w-4" />
        </Button>
      </div>

      {historyOpen && (
        <div className="fixed inset-0 z-50 flex justify-center px-0 py-0 sm:px-4 sm:py-8">
          {/* Mirrors PhoneShell's own frame sizing so the drawer lines up with the phone card on desktop. */}
          <div className="relative h-full w-full max-w-[430px] sm:h-[min(860px,calc(100dvh-4rem))]">
            <div
              className="absolute inset-0 bg-foreground/40 sm:rounded-[2.25rem]"
              onClick={() => setHistoryOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute inset-y-0 right-0 flex w-[85%] max-w-[320px] flex-col bg-background shadow-2xl sm:rounded-r-[1.5rem]">
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border p-4">
                <p className="font-bold">Lịch sử hội thoại</p>
                <button onClick={() => setHistoryOpen(false)} aria-label="Đóng">
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>

              <div className="shrink-0 p-4 pb-2">
                <Button className="w-full" onClick={newConversation}>
                  <Plus className="mr-1 h-4 w-4" /> Hội thoại mới
                </Button>
              </div>

              <div className="flex-1 space-y-1 overflow-y-auto p-4 pt-2">
                {sortedHistory.length === 0 && (
                  <p className="text-sm text-muted-foreground">Chưa có hội thoại nào.</p>
                )}
                {sortedHistory.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => selectConversation(c.id)}
                    className={`block w-full rounded-xl px-3 py-2.5 text-left text-sm ${
                      c.id === activeId
                        ? "bg-primary/10 font-semibold text-primary"
                        : "hover:bg-muted"
                    }`}
                  >
                    <p className="truncate">{c.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatConversationTime(c.updatedAt)} · {c.messages.length} tin nhắn
                    </p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
