// Bong bong chat - port tu capyphone.js::renderAI() (v.chat.map): khong co
// avatar 2 ben, bong bong bam sat le, bo goc lech ve phia nguoi noi.
// Mau/kich thuoc lay nguyen tu ban thiet ke.

import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ReportMessageDialog } from "@/components/report-message-dialog";
import type { StoredChatMessage } from "@/lib/chat-history";

export function ChatMessage({
  message,
  at,
  conversationId,
  accessToken,
}: {
  message: StoredChatMessage;
  at?: string;
  // BUILD-29: chi can khi message.role === "assistant" (nut bao cao chi
  // hien voi assistant) - optional de khong bat buoc moi noi dang dung
  // component nay phai truyen them 2 prop moi.
  conversationId?: string;
  accessToken?: string | null;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div
        className="max-w-[82%] px-[15px] py-[13px] text-[14px] leading-[1.5]"
        style={
          isUser
            ? { background: "#16386E", color: "#FFFFFF", borderRadius: "20px 20px 6px 20px" }
            : { background: "#E4DDFB", color: "#2E2456", borderRadius: "20px 20px 20px 6px" }
        }
      >
        <MarkdownRenderer content={message.content} />
      </div>
      {at && <p className="font-mono m-0 mt-1 px-1 text-[10px] text-[#62708A]">{at}</p>}
      {!isUser && conversationId && (
        <ReportMessageDialog
          conversationId={conversationId}
          message={message}
          accessToken={accessToken}
        />
      )}
    </div>
  );
}
