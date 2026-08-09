import { Bot, User } from "lucide-react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import type { ChatMessage as ChatMessageT } from "@/types/chat";

export function ChatMessage({ message }: { message: ChatMessageT }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
          isUser
            ? "rounded-tr-sm bg-primary text-primary-foreground"
            : "rounded-tl-sm bg-muted text-foreground"
        }`}
      >
        <MarkdownRenderer content={message.content} />
      </div>
    </div>
  );
}
