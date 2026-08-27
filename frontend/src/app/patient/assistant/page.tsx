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
import { CameraCapture } from "@/components/camera-capture";
import { toast } from "sonner";
import { ChatMessage } from "@/components/chat-message";
import { ChatError } from "@/components/chat-error";
import { useChatMessage } from "@/hooks/use-chat";
import type { SelectedAction, SuggestedAction } from "@/types/chat";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";
import { confirmDrugImageCandidate, recognizeDrugImage } from "@/lib/api";
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
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [selectedImagePreviewUrl, setSelectedImagePreviewUrl] = useState<string | null>(null);
  const [imagePending, setImagePending] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const lastQuestion = useRef("");
  const imageInputRef = useRef<HTMLInputElement>(null);
  const submitInFlight = useRef(false);
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

  useEffect(() => {
    if (!selectedImage) {
      setSelectedImagePreviewUrl(null);
      return;
    }
    const previewUrl = URL.createObjectURL(selectedImage);
    setSelectedImagePreviewUrl(previewUrl);
    return () => URL.revokeObjectURL(previewUrl);
  }, [selectedImage]);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const messages = active?.messages ?? [];

  const appendMessage = (
    convId: string,
    role: "user" | "assistant",
    content: string,
    // BUILD-29: chi assistant message can meta nay - trace_id/agent_run_id
    // that response da tra ve cho DUNG luot nay, va cau hoi cua nguoi dung
    // ngay truoc do (de nut "Báo cáo câu trả lời" khong bao gio phai doc
    // lai tu phan tu lien ke trong mang, tranh sai lech neu lich su sau nay
    // bi chinh sua).
    meta?: {
      traceId?: string;
      agentRunId?: string;
      userMessage?: string;
      suggestedActions?: SuggestedAction[];
      drugImage?: { attemptId: string; candidates: import("@/types/chat").DrugImageCandidate[] };
    },
  ) => {
    const now = new Date().toISOString();
    setConversations((prev) => {
      const next = prev.map((c) => {
        if (c.id !== convId) return c;
        const newMessages = [
          ...c.messages,
          { id: crypto.randomUUID(), role, content, at: now, ...meta },
        ];
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

  const submit = (content: string, selectedAction?: SelectedAction) => {
    if (!content.trim() || isPending || submitInFlight.current || !activeId) return;
    submitInFlight.current = true;
    lastQuestion.current = content;
    appendMessage(activeId, "user", content);
    setInput("");
    reset();
    mutate(
      // BUILD-26: conversation_id = this UI thread's own stable id, so
      // Agent V2's short-term memory scopes to the same thread the user
      // sees, instead of every message defaulting to one shared "one-shot"
      // conversation per account (backend/api/agent_v2_routes.py's own
      // fallback when conversation_id is omitted).
      {
        patient_id: user?.patient_id ?? "",
        message: content,
        conversation_id: activeId,
        ...(selectedAction ? { selected_action: selectedAction } : {}),
      },
      {
        onSuccess: (data) => {
          // BUILD-29: stash trace_id/agent_run_id (already returned by every
          // real Agent V2 response, see frontend/src/types/chat.ts) plus the
          // question that produced this reply, so "Báo cáo câu trả lời" never
          // needs the user to type an id by hand.
          appendMessage(activeId, "assistant", data.reply, {
            traceId: data.trace_id,
            agentRunId: data.agent_run_id,
            userMessage: content,
            suggestedActions: data.suggested_actions,
          });
        },
        onSettled: () => {
          submitInFlight.current = false;
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

  const selectImage = (file: File | null) => {
    if (!file) return;
    setSelectedImage(file);
  };

  const submitImage = async () => {
    if (!selectedImage || !activeId || imagePending || isPending) return;
    const image = selectedImage;
    const text = input.trim();
    setImagePending(true);
    try {
      const data = await recognizeDrugImage(
        { patientId: user?.patient_id ?? "", conversationId: activeId, message: text, file: image },
        accessToken,
      );
      // A File object is only a local selection. Persist a chat turn after
      // the server accepts the multipart request, never at selection time.
      appendMessage(activeId, "user", text || `Đã gửi ảnh: ${image.name}`);
      setInput("");
      setSelectedImage(null);
      appendMessage(activeId, "assistant", data.reply, {
        drugImage: data.recognition_attempt_id
          ? { attemptId: data.recognition_attempt_id, candidates: data.candidates }
          : undefined,
      });
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không thể gửi ảnh. Bạn vẫn có thể tiếp tục nhắn tin.");
    } finally {
      setImagePending(false);
    }
  };

  const confirmCandidate = async (attemptId: string, actionId: string, label: string) => {
    if (!activeId || imagePending || isPending) return;
    setImagePending(true);
    appendMessage(activeId, "user", `Đúng, đây là ${label}.`);
    try {
      const data = await confirmDrugImageCandidate(
        { patientId: user?.patient_id ?? "", conversationId: activeId, attemptId, actionId },
        accessToken,
      );
      appendMessage(activeId, "assistant", data.reply);
    } catch (error) {
      toast(error instanceof Error ? error.message : "Lựa chọn không còn hiệu lực. Hãy gửi lại ảnh.");
    } finally {
      setImagePending(false);
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
          <ChatMessage
            key={m.id}
            message={m}
            at={formatMessageTime(m.at)}
            conversationId={activeId ?? undefined}
            accessToken={accessToken}
            actionsDisabled={isPending || imagePending}
            onConfirmDrugCandidate={confirmCandidate}
            onSelectAction={(action) => {
              const { label: _label, ...selectedAction } = action;
              submit(action.label, selectedAction);
            }}
          />
        ))}

        {(isPending || imagePending) && (
          <div
            className="font-mono self-start px-[15px] py-[13px] text-[13px]"
            style={{ background: "#E4DDFB", color: "#4B3E86", borderRadius: "20px 20px 20px 6px" }}
          >
            {imagePending ? "Đang phân tích ảnh..." : "Capy đang xử lý…"}
          </div>
        )}

        {isError && (
          <ChatError
            error={error instanceof Error ? error.message : "Không thể kết nối tới trợ lý AI."}
            onRetry={() => submit(lastQuestion.current)}
          />
        )}
      </div>

      {/* Khoi day: goi y + o nhap + dong luu y */}
      <div className="mt-auto flex shrink-0 flex-col gap-3">
        {selectedImage && (
          <div className="flex items-center justify-between rounded-xl border border-[#E3E8F1] bg-white px-3 py-2 text-sm text-[#1B2A44]">
            <div className="flex min-w-0 items-center gap-2">
              {selectedImagePreviewUrl && (
                <img
                  src={selectedImagePreviewUrl}
                  alt="Xem trước ảnh thuốc đã chọn"
                  className="h-10 w-10 shrink-0 rounded-lg object-cover"
                />
              )}
              <span className="truncate">Ảnh đã chọn: {selectedImage.name}</span>
            </div>
            <button type="button" onClick={() => setSelectedImage(null)} aria-label="Bỏ ảnh đã chọn" className="ml-2 text-[#16386E]">
              Bỏ ảnh
            </button>
          </div>
        )}
        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_PROMPTS.map((p) => (
              <button
                key={p}
                onClick={() => submit(p)}
                className="rounded-full border border-[#E3E8F1] bg-white px-3.5 py-2.5 text-[13px] font-medium text-[#1B2A44] transition-colors hover:bg-[#F4F7FC]"
              >
                {p}
              </button>
            ))}
          </div>
        )}

        <div className="relative flex items-end gap-2.5">
          <input
            ref={imageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="sr-only"
            onChange={(event) => {
              selectImage(event.target.files?.[0] ?? null);
              event.currentTarget.value = "";
            }}
          />
          {plusOpen && (
            <div className="absolute bottom-[60px] left-0 flex gap-2 rounded-[20px] bg-white p-2 shadow-[0_10px_30px_rgba(22,56,110,.14)]">
              <button
                type="button"
                aria-label="Chụp ảnh thuốc"
                disabled={isPending || imagePending}
                onClick={() => {
                  setPlusOpen(false);
                  setCameraOpen(true);
                }}
                className="grid h-11 w-11 place-items-center rounded-[16px] bg-[#F4F7FC] text-[18px] transition-colors hover:bg-[#EDF0F6] disabled:opacity-50"
              >
                📷
              </button>
              <button
                type="button"
                aria-label="Tải ảnh thuốc lên"
                disabled={isPending || imagePending}
                onClick={() => {
                  setPlusOpen(false);
                  imageInputRef.current?.click();
                }}
                className="grid h-11 w-11 place-items-center rounded-[16px] bg-[#F4F7FC] text-[18px] transition-colors hover:bg-[#EDF0F6] disabled:opacity-50"
              >
                🖼️
              </button>
            </div>
          )}
          <button
            aria-label="Thêm"
            onClick={() => setPlusOpen((v) => !v)}
            className="font-display grid h-[52px] w-[52px] shrink-0 place-items-center rounded-[18px] text-[20px] font-bold transition-colors"
            style={
              plusOpen
                ? { background: "#16386E", color: "#FFFFFF" }
                : { background: "#EDF0F6", color: "#1B2A44" }
            }
          >
            +
          </button>
          <input
            value={input}
            placeholder="Hỏi Capy..."
            aria-label="Nhập câu hỏi cho trợ lý AI"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isPending || imagePending}
            className="h-[52px] min-w-0 flex-1 rounded-[20px] border border-[#E3E8F1] bg-white px-4 text-[14px] text-[#1B2A44] outline-none transition-colors focus:border-[#16386E] disabled:opacity-60"
          />
          <button
            aria-label="Gửi câu hỏi"
            disabled={isPending || imagePending || (!input.trim() && !selectedImage)}
            onClick={() => (selectedImage ? submitImage() : submit(input))}
            className="font-display grid h-[52px] w-[52px] shrink-0 place-items-center rounded-[18px] text-[18px] font-bold text-white transition-colors"
            style={{ background: input.trim() || selectedImage ? "#16386E" : "#B7C2D6" }}
          >
            ↑
          </button>
        </div>
      </div>

      <CameraCapture
        open={cameraOpen}
        onOpenChange={setCameraOpen}
        onCapture={(file) => {
          setCameraOpen(false);
          selectImage(file);
        }}
        onFallbackToFile={() => imageInputRef.current?.click()}
      />

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
