"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ChatMessage } from "@/components/chat-message";
import { ChatError } from "@/components/chat-error";
import { useChatMessage } from "@/hooks/use-chat";
import { useProto } from "@/lib/proto-store";
import type { ChatMessage as ChatMessageT } from "@/types/chat";

export default function AssistantPage() {
  const { symptomCheckPending, clearSymptomCheck } = useProto();
  const [messages, setMessages] = useState<ChatMessageT[]>([]);
  const [input, setInput] = useState("");
  const lastQuestion = useRef("");
  const { mutate, isPending, isError, error, reset } = useChatMessage();

  useEffect(() => {
    if (!symptomCheckPending) return;
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content:
          "Bạn vừa cho biết hôm nay cảm thấy không ổn. Hãy mô tả chi tiết triệu chứng bạn đang gặp (vị trí, mức độ, từ khi nào, kèm dấu hiệu gì khác) để tôi hỗ trợ và báo cho bác sĩ nhé.",
      },
    ]);
    clearSymptomCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symptomCheckPending]);

  const submit = (content: string) => {
    if (!content.trim() || isPending) return;
    lastQuestion.current = content;
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content }]);
    setInput("");
    reset();
    mutate(
      { message: content },
      {
        onSuccess: (data) => {
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "assistant", content: data.response },
          ]);
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

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col">
      <header>
        <h1 className="text-xl font-extrabold">Trợ lý AI</h1>
        <p className="text-sm text-muted-foreground">
          Hỏi về triệu chứng, thuốc đang dùng hoặc cách chăm sóc.
        </p>
      </header>

      <div className="mt-4 flex-1 space-y-4 overflow-y-auto">
        {messages.length === 0 && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Gửi câu hỏi để bắt đầu trò chuyện.
          </p>
        )}
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        {isPending && <p className="text-sm text-muted-foreground">Đang suy nghĩ...</p>}
        {isError && (
          <ChatError
            error={error instanceof Error ? error.message : "Không thể kết nối tới trợ lý AI."}
            onRetry={() => submit(lastQuestion.current)}
          />
        )}
      </div>

      <div className="mt-3 flex gap-2 border-t border-border pt-3">
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
    </div>
  );
}
