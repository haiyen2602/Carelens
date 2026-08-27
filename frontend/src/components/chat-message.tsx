// Bong bong chat - port tu capyphone.js::renderAI() (v.chat.map): khong co
// avatar 2 ben, bong bong bam sat le, bo goc lech ve phia nguoi noi.
// Mau/kich thuoc lay nguyen tu ban thiet ke.

import { ActivityTimeline } from "@/components/activity-timeline";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { ReportMessageDialog } from "@/components/report-message-dialog";
import type { StoredChatMessage } from "@/lib/chat-history";
import type { SuggestedAction } from "@/types/chat";

export function ChatMessage({
  message,
  at,
  conversationId,
  accessToken,
  onSelectAction,
  onConfirmDrugCandidate,
  onRejectDrugCandidates,
  actionsDisabled = false,
}: {
  message: StoredChatMessage;
  at?: string;
  // BUILD-29: chi can khi message.role === "assistant" (nut bao cao chi
  // hien voi assistant) - optional de khong bat buoc moi noi dang dung
  // component nay phai truyen them 2 prop moi.
  conversationId?: string;
  accessToken?: string | null;
  onSelectAction?: (action: SuggestedAction) => void;
  onConfirmDrugCandidate?: (attemptId: string, actionId: string, label: string) => void;
  // B-08 enablement: candidate list co the khong chua dung thuoc (anh chup
  // lech goc/nguoc sang/mo). Nut nay la loi thoat ro rang, tranh nguoi dung
  // buoc phai chon dai 1 trong cac goi y sai.
  onRejectDrugCandidates?: (attemptId: string) => void;
  actionsDisabled?: boolean;
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
        <>
          {message.drugImage && message.drugImage.candidates.length > 0 && (
            <div className="mt-2 flex max-w-[82%] flex-col gap-2" aria-label="Các thuốc cần xác nhận">
              {message.drugImage.candidates.map((candidate) => (
                <button
                  key={candidate.action_id}
                  type="button"
                  disabled={actionsDisabled}
                  onClick={() => onConfirmDrugCandidate?.(message.drugImage!.attemptId, candidate.action_id, candidate.product_display_name)}
                  className="min-h-10 rounded-lg border border-[#B7C2D6] bg-white px-3 py-2 text-left text-[13px] font-medium text-[#16386E] transition-colors hover:bg-[#F4F7FC] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#16386E] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="block">{candidate.product_display_name}</span>
                  {candidate.strength_text && <span className="block text-xs font-normal text-[#62708A]">{candidate.strength_text}</span>}
                  <span className="mt-1 block">Đúng thuốc này</span>
                </button>
              ))}
              <button
                type="button"
                disabled={actionsDisabled}
                onClick={() => onRejectDrugCandidates?.(message.drugImage!.attemptId)}
                className="min-h-10 rounded-lg border border-dashed border-[#B7C2D6] bg-transparent px-3 py-2 text-left text-[13px] font-medium text-[#62708A] transition-colors hover:bg-[#F4F7FC] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#16386E] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Không phải thuốc nào ở trên — nhập tên thuốc
              </button>
            </div>
          )}
          {message.suggestedActions && message.suggestedActions.length > 0 && (
            <div className="mt-2 flex max-w-[82%] flex-wrap gap-2" aria-label="Gợi ý câu hỏi tiếp theo">
              {message.suggestedActions.map((action) => (
                <button
                  key={action.action_id}
                  type="button"
                  disabled={actionsDisabled}
                  onClick={() => onSelectAction?.(action)}
                  className="min-h-10 rounded-lg border border-[#B7C2D6] bg-white px-3 py-2 text-left text-[13px] font-medium text-[#16386E] transition-colors hover:bg-[#F4F7FC] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#16386E] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
          <ActivityTimeline traceId={message.traceId} accessToken={accessToken} />
          <ReportMessageDialog
            conversationId={conversationId}
            message={message}
            accessToken={accessToken}
          />
        </>
      )}
    </div>
  );
}
