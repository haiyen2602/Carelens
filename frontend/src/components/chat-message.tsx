import { User } from "lucide-react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import type { ChatMessage as ChatMessageT } from "@/types/chat";

const CHATBOT_AVATAR_URL = "/favicon-128.png";

export function ChatMessage({ message, at }: { message: ChatMessageT; at?: string }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}>
      {isUser ? (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <User className="h-4 w-4" />
        </div>
      ) : (
        <div
          aria-label="CapyMedi"
          className="h-8 w-8 shrink-0 rounded-full border border-accent bg-white bg-no-repeat shadow-sm"
          role="img"
          style={{
            backgroundImage: `url(${CHATBOT_AVATAR_URL})`,
            backgroundPosition: "center",
            backgroundSize: "cover",
          }}
        />
      )}
      <div className={`flex max-w-[80%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`px-4 py-2.5 text-sm ${
            isUser
              ? "rounded-[20px_20px_6px_20px] bg-primary text-primary-foreground"
              : "rounded-[20px_20px_20px_6px] text-foreground"
          }`}
          style={isUser ? undefined : { backgroundColor: "var(--capy-lavender)" }}
        >
          <MarkdownRenderer content={message.content} />
        </div>
        {at && <p className="px-1 text-[11px] text-muted-foreground">{at}</p>}
      </div>
    </div>
  );
}
