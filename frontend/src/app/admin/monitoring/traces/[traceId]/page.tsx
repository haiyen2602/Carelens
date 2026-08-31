"use client";

// BUILD-36: Trace detail -- drill-down target from every dashboard section,
// from tickets, and from safety events. Durable metrics ALWAYS available;
// raw query/response text only when `content_available` is true (still in
// the 200-entry in-memory buffer) -- never fabricated/reconstructed when
// it is not (see BUILD-36 report's own audit on this architectural limit).

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock,
  Coins,
  Cpu,
  DollarSign,
  ExternalLink,
  FileCode,
  FileText,
  Gauge,
  Info,
  Layers,
  LayoutDashboard,
  ListChecks,
  ListFilter,
  Loader2,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
  Ticket,
  User,
  Wrench,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { getTraceDetail, type TraceDetailOut } from "@/lib/admin-monitoring";

// ─── Metadata Dictionaries ───────────────────────────────────────────────────

const EXECUTION_PATH_METADATA: Record<string, { label: string; description: string }> = {
  DRUG_LOOKUP: {
    label: "Tra cứu thông tin thuốc",
    description: "Tra cứu chi tiết chỉ định, liều dùng, tác dụng phụ và chống chỉ định từ cơ sở dữ liệu dược học.",
  },
  DETERMINISTIC_TOOL: {
    label: "Công cụ tính toán nghiệp vụ",
    description: "Thực thi công cụ quy chuẩn xác định (tính liều lượng, lịch nhắc uống thuốc, chuyển đổi đơn vị).",
  },
  DETERMINISTIC_SCHEDULE: {
    label: "Lập lịch uống thuốc",
    description: "Xử lý và thiết lập lịch nhắc uống thuốc tự động theo phác đồ điều trị.",
  },
  GENERAL_MODEL: {
    label: "Mô hình ngôn ngữ tổng quát",
    description: "Xử lý hội thoại tự nhiên, giải thích thông tin y tế thông thường không cần gọi công cụ đặc thù.",
  },
  RAG: {
    label: "Truy xuất tài liệu y khoa (RAG)",
    description: "Tìm kiếm và tổng hợp thông tin từ cơ sở tri thức y dược và tài liệu chuyên môn.",
  },
  TRIAGE: {
    label: "Phân loại triệu chứng",
    description: "Đánh giá mức độ khẩn cấp của triệu chứng và đưa ra hướng xử trí ban đầu.",
  },
  MEDICATION_DOSE_SAFETY: {
    label: "Kiểm tra an toàn liều lượng",
    description: "Kiểm tra an toàn liều dùng, tương tác thuốc và cảnh báo nguy cơ vượt liều.",
  },
  SAFETY: {
    label: "Bộ lọc an toàn y khoa",
    description: "Kích hoạt quy tắc an toàn bảo vệ bệnh nhân và chặn các nội dung vi phạm tiêu chuẩn y tế.",
  },
  HANDOFF: {
    label: "Chuyển tiếp bác sĩ",
    description: "Tạo phiếu hỗ trợ và chuyển giao ca bệnh phức tạp sang hàng đợi bác sĩ chuyên môn.",
  },
  FALLBACK: {
    label: "Phản hồi dự phòng",
    description: "Kích hoạt phản hồi an toàn dự phòng khi hệ thống gặp ngoại lệ hoặc sự cố kết nối.",
  },
  OUT_OF_SCOPE: {
    label: "Ngoài phạm vi hỗ trợ",
    description: "Yêu cầu nằm ngoài phạm vi tư vấn y tế hoặc năng lực phục vụ của hệ thống.",
  },
};

const INTENT_METADATA: Record<string, { label: string; description: string }> = {
  MISSED_DOSE: {
    label: "Xử lý quên liều thuốc",
    description: "Hướng dẫn người bệnh cách xử lý khi quên uống hoặc uống trễ một liều thuốc.",
  },
  DRUG_INFORMATION: {
    label: "Tra cứu thông tin thuốc",
    description: "Hỏi về công dụng, chỉ định, tác dụng phụ hoặc cách sử dụng thuốc.",
  },
  MEDICATION_SCHEDULE: {
    label: "Lập lịch uống thuốc",
    description: "Tạo hoặc điều chỉnh thời gian biểu uống thuốc trong ngày.",
  },
  SYMPTOM_CHECK: {
    label: "Tư vấn triệu chứng",
    description: "Kiểm tra và phân loại mức độ của các triệu chứng bất thường.",
  },
  GENERAL_CHAT: {
    label: "Trò chuyện thông thường",
    description: "Hội thoại chào hỏi hoặc câu hỏi chăm sóc sức khỏe thông thường.",
  },
  UNKNOWN_OR_AMBIGUOUS: {
    label: "Yêu cầu chưa rõ ràng / chung",
    description: "Câu hỏi tổng quát hoặc chưa xác định rõ ý định y khoa cụ thể.",
  },
  SAFETY_CRITICAL: {
    label: "Tình huống y tế nguy cấp",
    description: "Yêu cầu chứa từ khóa hoặc tình trạng cấp cứu, nguy hiểm.",
  },
};

const TRACE_STATUS_METADATA: Record<string, { label: string; bgClass: string }> = {
  COMPLETED: { label: "Thành công", bgClass: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" },
  SUCCESS: { label: "Thành công", bgClass: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" },
  HANDOFF_CREATED: { label: "Đã tạo chuyển tiếp bác sĩ", bgClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" },
  HANDOFF_REQUIRED: { label: "Cần chuyển bác sĩ", bgClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" },
  SAFETY_TRIGGERED: { label: "Kích hoạt an toàn", bgClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" },
  SAFETY_BLOCKED: { label: "Chặn vi phạm an toàn", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  BUDGET_EXCEEDED: { label: "Vượt ngân sách", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  TIMEOUT: { label: "Hết thời gian chờ", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  FAILED: { label: "Thất bại", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  CANCELLED: { label: "Đã hủy", bgClass: "bg-muted text-muted-foreground border" },
};

const SPAN_TYPE_MAP: Record<string, string> = {
  llm: "Mô hình AI",
  tool: "Công cụ nghiệp vụ",
  retrieval: "Truy xuất tài liệu",
  safety: "Kiểm tra an toàn",
  guardrail: "Kiểm duyệt",
  triage: "Phân loại triệu chứng",
  orchestration: "Điều phối luồng",
};

const SEVERITY_METADATA: Record<string, { label: string; color: string; bgClass: string }> = {
  CRITICAL: { label: "Khẩn cấp", color: "#ef4444", bgClass: "bg-rose-600 text-white" },
  HIGH: { label: "Cao", color: "#f97316", bgClass: "bg-orange-500 text-white" },
  MEDIUM: { label: "Trung bình", color: "#f59e0b", bgClass: "bg-amber-500 text-white" },
  LOW: { label: "Thấp", color: "#10b981", bgClass: "bg-emerald-500 text-white" },
};

const SAFETY_REASON_METADATA: Record<string, { label: string; description: string }> = {
  ACUTE_DANGER_DETECTED: {
    label: "Phát hiện nguy hiểm cấp tính",
    description: "Phát hiện dấu hiệu cấp cứu hoặc triệu chứng nguy hiểm đe dọa tính mạng cần can thiệp y tế ngay.",
  },
  DOSE_UNRESOLVED: {
    label: "Chưa xác định được liều lượng",
    description: "Không đủ thông tin an toàn để tính toán hoặc khuyến cáo liều dùng chính xác.",
  },
  DRUG_INTERACTION: {
    label: "Tương tác thuốc nguy hiểm",
    description: "Phát hiện nguy cơ tương tác bất lợi giữa các loại thuốc trong đơn hoặc tiền sử.",
  },
  CONTRAINDICATION: {
    label: "Chống chỉ định dùng thuốc",
    description: "Thuốc bị chống chỉ định đối với tình trạng bệnh lý hoặc tiền sử dị ứng của bệnh nhân.",
  },
  SPECIAL_POPULATION: {
    label: "Đối tượng nguy cơ đặc biệt",
    description: "Bệnh nhân thuộc nhóm đặc biệt (phụ nữ mang thai, cho con bú, trẻ nhỏ, suy gan/thận).",
  },
  HIGH_RISK_SYMPTOM: {
    label: "Triệu chứng nguy cơ cao",
    description: "Triệu chứng bất thường kéo dài hoặc trở nặng cần bác sĩ chuyên khoa thăm khám trực tiếp.",
  },
  SAFETY_ANOMALY: {
    label: "Bất thường về an toàn",
    description: "Hệ thống phát hiện tín hiệu bất thường trong câu trả lời cần kiểm tra an toàn.",
  },
  DOCTOR_REVIEW_REQUESTED: {
    label: "Yêu cầu bác sĩ đánh giá",
    description: "Hệ thống kích hoạt chuyển tiếp để bác sĩ chuyên khoa kiểm duyệt và đánh giá tư vấn trực tiếp.",
  },
};

const DIMENSION_NAME_MAP: Record<string, string> = {
  faithfulness: "Độ trung thực",
  relevance: "Độ phù hợp",
  answer_relevance: "Độ phù hợp câu trả lời",
  safety: "Độ an toàn",
  coherence: "Tính mạch lạc",
  instruction_following: "Tuân thủ chỉ dẫn",
  conciseness: "Tính cô đọng",
};

const JUDGE_REASON_METADATA: Record<string, string> = {
  SAFETY_ANOMALY: "Bất thường về an toàn y tế",
  RANDOM_SAMPLE: "Lấy mẫu ngẫu nhiên",
  LOW_CONFIDENCE: "Độ tin cậy thấp",
  FALLBACK_TRIGGERED: "Kích hoạt phản hồi dự phòng",
  MANUAL_EVALUATION: "Yêu cầu đánh giá thủ công",
};

function cleanPreviewText(raw: string | null | undefined): string {
  if (!raw) return "N/A";
  const trimmed = raw.trim();
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed === "object" && parsed !== null) {
      if (parsed.message) return String(parsed.message);
      if (parsed.response) return String(parsed.response);
      if (parsed.reply) return String(parsed.reply);
      if (parsed.text) return String(parsed.text);
    }
  } catch {
    const match = trimmed.match(/^\{['"](?:message|response|reply|text)['"]\s*:\s*['"](.+?)['"]\}$/s);
    if (match && match[1]) {
      return match[1].replace(/\\n/g, "\n").replace(/\\'/g, "'").replace(/\\"/g, '"');
    }
  }
  return trimmed;
}

export default function TraceDetailPage() {
  const params = useParams<{ traceId: string }>();
  const router = useRouter();
  const { accessToken } = useAuth();
  const [detail, setDetail] = useState<TraceDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !params.traceId) return;
    setLoading(true);
    getTraceDetail(params.traceId, accessToken)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Lỗi không xác định"))
      .finally(() => setLoading(false));
  }, [accessToken, params.traceId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-sm text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin text-primary" /> Đang tải thông tin chi tiết trace...
      </div>
    );
  }
  if (error || !detail) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Quay lại
          </Button>
          <Link href="/admin/monitoring/traces">
            <Button variant="ghost" size="sm">
              <ListFilter className="mr-1 h-4 w-4" /> Về Trace Explorer
            </Button>
          </Link>
        </div>
        <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error ?? "Không tìm thấy trace"}
        </div>
      </div>
    );
  }

  const isSafetyTriggered = detail.safety && (detail.safety.outcome !== "SAFE" || detail.safety.handoff_required);
  const cleanQuery = cleanPreviewText(detail.query_preview);
  const cleanResponse = cleanPreviewText(detail.response_preview);

  const statusMeta = TRACE_STATUS_METADATA[detail.status] ?? {
    label: detail.status,
    bgClass: detail.status.includes("FAILED") || detail.status.includes("TIMEOUT") || detail.status.includes("EXCEEDED")
      ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
      : detail.status.includes("HANDOFF") || detail.status.includes("SAFETY")
      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
      : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20",
  };

  const pathMeta = EXECUTION_PATH_METADATA[detail.execution_path ?? ""];
  const intentMeta = INTENT_METADATA[detail.intent ?? ""];

  return (
    <div className="space-y-6 pb-12">
      {/* Navigation bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (window.history.length > 1) {
                router.back();
              } else {
                router.push("/admin/monitoring/traces");
              }
            }}
          >
            <ArrowLeft className="mr-1 h-4 w-4" /> Quay lại trang trước
          </Button>
          <Link href="/admin/monitoring/traces">
            <Button variant="ghost" size="sm">
              <ListFilter className="mr-1 h-4 w-4" /> Danh sách Trace
            </Button>
          </Link>
        </div>
        <Link href="/admin/monitoring">
          <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground">
            <LayoutDashboard className="mr-1 h-4 w-4" /> Bảng điều khiển Giám sát
          </Button>
        </Link>
      </div>

      {/* Overview Metadata Card */}
      <div className="surface-card p-5 space-y-4">
        <div className="flex items-center justify-between border-b pb-3 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold">Thông tin tổng quan Trace</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${statusMeta.bgClass}`}>
              {statusMeta.label}
            </span>
            {detail.error_code && (
              <span className="inline-flex items-center rounded bg-destructive/10 px-2 py-0.5 text-xs font-mono text-destructive">
                Mã lỗi: {detail.error_code}
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <Field label="Mã Trace" value={detail.trace_id} mono copyable />
          <Field label="Mã Agent Run" value={detail.agent_run_id} mono copyable />
          <Field
            label="Hội thoại"
            value={detail.conversation_id}
            mono
            link={detail.conversation_id ? `/admin/monitoring/sessions/${detail.conversation_id}` : undefined}
          />
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Đường dẫn xử lý</p>
            <div className="flex flex-col" title={pathMeta?.description}>
              <span className="font-medium text-foreground text-xs">{pathMeta?.label ?? detail.execution_path ?? "N/A"}</span>
              {detail.execution_path && (
                <span className="font-mono text-[11px] text-muted-foreground">{detail.execution_path}</span>
              )}
            </div>
          </div>

          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Ý định yêu cầu</p>
            <div className="flex flex-col" title={intentMeta?.description}>
              <span className="font-medium text-foreground text-xs">{intentMeta?.label ?? detail.intent ?? "N/A"}</span>
              {detail.intent && (
                <span className="font-mono text-[11px] text-muted-foreground">{detail.intent}</span>
              )}
            </div>
          </div>

          <Field label="Mô hình AI" value={detail.model} mono />
          <Field
            label="Thời điểm bắt đầu"
            value={detail.started_at ? new Date(detail.started_at).toLocaleString("vi-VN", {
              timeZone: "Asia/Ho_Chi_Minh",
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
            }) : null}
          />
          <Field
            label="Thời gian thực thi"
            value={detail.duration_ms !== null ? `${Math.round(detail.duration_ms)} ms` : null}
          />
          <Field label="Số lượt gọi mô hình" value={`${detail.model_calls} lượt`} />
          <Field label="Phiên bản Prompt" value={detail.prompt_version} mono />
          <Field label="Phiên bản Truy xuất" value={detail.retrieval_version} mono />
          <Field label="Trạng thái Timeout" value={detail.timeout ? "Bị Timeout" : "Không"} />
        </div>
      </div>

      {/* Token & Cost Card */}
      <div className="surface-card p-5 space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div className="flex items-center gap-2">
            <Coins className="h-5 w-5 text-amber-500" />
            <h2 className="text-base font-semibold">Token & Chi phí</h2>
          </div>
          <span
            className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
              detail.cost.status === "AVAILABLE"
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                : "bg-muted text-muted-foreground"
            }`}
          >
            {detail.cost.status === "AVAILABLE" ? "Đã tính chi phí" : "Chưa có biểu phí"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <div className="rounded-lg border bg-card p-3.5 flex flex-col justify-between">
            <span className="text-xs text-muted-foreground font-medium">Chi phí ước tính</span>
            <span className="text-lg font-bold text-primary mt-1">
              {detail.cost.status === "AVAILABLE" && detail.cost.total_usd !== null
                ? `$${detail.cost.total_usd.toFixed(6)}`
                : "N/A"}
            </span>
          </div>
          <div className="rounded-lg border bg-card p-3.5 flex flex-col justify-between">
            <span className="text-xs text-muted-foreground font-medium">Token đầu vào</span>
            <span className="text-lg font-semibold mt-1">{detail.tokens.input.toLocaleString("vi-VN")}</span>
          </div>
          <div className="rounded-lg border bg-card p-3.5 flex flex-col justify-between">
            <span className="text-xs text-muted-foreground font-medium">Token bộ nhớ đệm</span>
            <span className="text-lg font-semibold mt-1">{detail.tokens.cached_input.toLocaleString("vi-VN")}</span>
          </div>
          <div className="rounded-lg border bg-card p-3.5 flex flex-col justify-between">
            <span className="text-xs text-muted-foreground font-medium">Token đầu ra</span>
            <span className="text-lg font-semibold mt-1">{detail.tokens.output.toLocaleString("vi-VN")}</span>
          </div>
          <div className="rounded-lg border bg-card p-3.5 flex flex-col justify-between">
            <span className="text-xs text-muted-foreground font-medium">Tổng số Token</span>
            <span className="text-lg font-bold text-foreground mt-1">{detail.tokens.total.toLocaleString("vi-VN")}</span>
          </div>
        </div>
      </div>

      {/* Nội dung trao đổi (Buffer Context) */}
      <div className="surface-card p-5 space-y-4">
        <div className="flex items-center justify-between border-b pb-3 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-sky-500" />
            <h2 className="text-base font-semibold">Nội dung trao đổi</h2>
          </div>
          <span
            className={`inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium ${
              detail.content_available
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                : "bg-muted text-muted-foreground border"
            }`}
          >
            {detail.content_available ? (
              <>
                <CheckCircle2 className="h-3 w-3 text-emerald-500" /> Còn trong bộ nhớ tạm 200 mục gần nhất
              </>
            ) : (
              <>
                <Info className="h-3 w-3" /> Đã hết hạn bộ nhớ tạm (Dữ liệu đo lường bền vững vẫn đầy đủ)
              </>
            )}
          </span>
        </div>

        {!detail.content_available ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground bg-muted/20">
            <p className="font-medium text-foreground mb-1">Nội dung câu hỏi/trả lời không còn được lưu tạm</p>
            <p className="text-xs">
              Trace đã vượt quá giới hạn 200 mục trong bộ nhớ tạm gần nhất hoặc tiến trình đã khởi động lại. Tất cả chỉ số đo lường, thời gian thực thi, chi phí và sự kiện an toàn ở trên vẫn được lưu trữ bền vững trong cơ sở dữ liệu.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* User Prompt Bubble */}
            <div className="flex gap-3 items-start">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary mt-0.5">
                <User className="h-4 w-4" />
              </div>
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold">Người dùng / Bệnh nhân</span>
                </div>
                <div className="rounded-xl rounded-tl-none border bg-muted/40 p-3.5 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                  {cleanQuery}
                </div>
              </div>
            </div>

            {/* Assistant Response Bubble */}
            <div className="flex gap-3 items-start">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-500/10 text-sky-600 dark:text-sky-400 mt-0.5">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold">Trợ lý Y tế AI</span>
                </div>
                <div className="rounded-xl rounded-tl-none border border-sky-500/20 bg-sky-500/5 p-3.5 text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                  {cleanResponse}
                </div>
              </div>
            </div>

            {/* Tools list */}
            {detail.tool_names && detail.tool_names.length > 0 && (
              <div className="pt-2 flex items-center gap-2 flex-wrap text-xs">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  <Wrench className="h-3.5 w-3.5" /> Công cụ đã kích hoạt:
                </span>
                {detail.tool_names.map((tool) => (
                  <span key={tool} className="rounded-md border bg-background px-2 py-0.5 font-mono text-[11px] text-foreground">
                    {tool}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Judge Card */}
      {detail.judge && (
        <div className="surface-card p-5 space-y-4">
          <div className="flex items-center justify-between border-b pb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <ListChecks className="h-5 w-5 text-indigo-500" />
              <h2 className="text-base font-semibold">Đánh giá tự động (LLM Judge)</h2>
            </div>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                detail.judge.judge_status === "JUDGE_COMPLETED"
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                  : detail.judge.judge_status === "JUDGE_FAILED"
                  ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                  : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
              }`}
            >
              {detail.judge.judge_status === "JUDGE_COMPLETED"
                ? "Đã hoàn tất chấm điểm"
                : detail.judge.judge_status === "JUDGE_FAILED"
                ? "Chấm điểm thất bại"
                : "Đang chờ chấm điểm"}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border bg-card p-4 flex flex-col justify-between">
              <span className="text-xs text-muted-foreground font-medium">Điểm số tổng thể</span>
              <div className="mt-2 flex items-baseline gap-1">
                <span
                  className={`text-2xl font-bold ${
                    detail.judge.overall_score !== null
                      ? detail.judge.overall_score >= 0.8
                        ? "text-emerald-600 dark:text-emerald-400"
                        : detail.judge.overall_score >= 0.6
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-rose-600 dark:text-rose-400"
                      : "text-muted-foreground"
                  }`}
                >
                  {detail.judge.overall_score !== null ? detail.judge.overall_score.toFixed(2) : "N/A"}
                </span>
                <span className="text-xs text-muted-foreground">/ 1.00</span>
              </div>
            </div>

            <div className="rounded-lg border bg-card p-4 space-y-2">
              <span className="text-xs text-muted-foreground font-medium">Cấu hình Judge</span>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Model AI:</span>
                  <span className="font-mono font-medium">{detail.judge.judge_model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Tiêu chí (Rubric):</span>
                  <span className="font-mono font-medium">{detail.judge.rubric_version}</span>
                </div>
              </div>
            </div>

            <div className="rounded-lg border bg-card p-4 space-y-2">
              <span className="text-xs text-muted-foreground font-medium">Lý do đánh giá</span>
              <p className="text-xs text-foreground font-medium">
                {JUDGE_REASON_METADATA[detail.judge.eligibility_reason ?? ""] ?? detail.judge.eligibility_reason ?? "Đủ điều kiện đánh giá tự động"}
              </p>
              {detail.judge.flags && detail.judge.flags.length > 0 && (
                <div className="flex gap-1 flex-wrap pt-1">
                  {detail.judge.flags.map((f) => (
                    <span key={f} className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-600">
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {detail.judge.dimension_scores && Object.keys(detail.judge.dimension_scores).length > 0 && (
            <div className="pt-2">
              <p className="text-xs font-semibold text-muted-foreground mb-2">Chi tiết các tiêu chí chất lượng:</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(detail.judge.dimension_scores).map(([dim, score]) => (
                  <div key={dim} className="rounded border bg-background px-3 py-2 text-xs flex justify-between items-center">
                    <span className="text-muted-foreground">{DIMENSION_NAME_MAP[dim] ?? dim.replace(/_/g, " ")}:</span>
                    <span className="font-bold text-foreground">{typeof score === "number" ? score.toFixed(2) : score}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Safety / Handoff Card */}
      {detail.safety && (
        <div
          className={`surface-card p-5 space-y-4 border ${
            isSafetyTriggered
              ? "border-rose-500/40 bg-rose-500/[0.02]"
              : "border-emerald-500/30"
          }`}
        >
          <div className="flex items-center justify-between border-b pb-3 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              {isSafetyTriggered ? (
                <ShieldAlert className="h-5 w-5 text-rose-600" />
              ) : (
                <ShieldCheck className="h-5 w-5 text-emerald-600" />
              )}
              <h2 className={`text-base font-semibold ${isSafetyTriggered ? "text-rose-600" : ""}`}>
                An toàn Y tế & Chuyển tiếp Bác sĩ
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  detail.safety.outcome === "SAFE"
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                }`}
              >
                {detail.safety.outcome === "SAFE" ? "An toàn" : "Cảnh báo an toàn"}
              </span>
              {detail.safety.severity && (
                <span
                  className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-bold ${
                    SEVERITY_METADATA[detail.safety.severity]?.bgClass ?? "bg-muted text-muted-foreground"
                  }`}
                >
                  {SEVERITY_METADATA[detail.safety.severity]?.label ?? detail.safety.severity}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Nguyên nhân kích hoạt</p>
              <div className="flex flex-col" title={SAFETY_REASON_METADATA[detail.safety.reason_code ?? ""]?.description}>
                <span className="font-medium text-foreground text-xs">
                  {SAFETY_REASON_METADATA[detail.safety.reason_code ?? ""]?.label ?? detail.safety.reason_code ?? "Không có"}
                </span>
                {detail.safety.reason_code && (
                  <span className="font-mono text-[11px] text-muted-foreground">{detail.safety.reason_code}</span>
                )}
              </div>
            </div>
            <Field
              label="Yêu cầu chuyển bác sĩ"
              value={detail.safety.handoff_required ? "Có (Bắt buộc)" : "Không"}
            />
            <Field
              label="Trạng thái chuyển tiếp"
              value={detail.safety.handoff_created ? "Đã tạo ca chuyển tiếp" : "Chưa tạo"}
            />
            <Field
              label="Mã chuyển tiếp (Handoff ID)"
              value={detail.safety.handoff_id}
              mono
              copyable
            />
          </div>
        </div>
      )}

      {/* Ticket Card (nếu có) */}
      {detail.ticket && (
        <div className="surface-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b pb-3">
            <div className="flex items-center gap-2">
              <Ticket className="h-5 w-5 text-primary" />
              <h2 className="text-base font-semibold">Phiếu hỗ trợ (Ticket liên kết)</h2>
            </div>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              {detail.ticket.status}
            </span>
          </div>
          <div className="flex items-center justify-between flex-wrap gap-2 text-sm">
            <div>
              <span className="text-muted-foreground mr-2">Mã phiếu:</span>
              <Link
                className="text-primary font-mono font-semibold underline inline-flex items-center gap-1 hover:text-primary/80"
                href={`/admin/tickets/${detail.ticket.ticket_id}`}
              >
                {detail.ticket.ticket_id} <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>
            {detail.ticket.reason && (
              <div>
                <span className="text-muted-foreground mr-1">Lý do:</span>
                <span className="font-medium text-foreground">{detail.ticket.reason}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Span Timeline */}
      {detail.spans.length > 0 && (
        <div className="surface-card p-5 space-y-4">
          <div className="flex items-center justify-between border-b pb-3">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-primary" />
              <h2 className="text-base font-semibold">Dòng thời gian các bước thực thi</h2>
            </div>
            <span className="text-xs text-muted-foreground">{detail.spans.length} bước</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs font-medium text-muted-foreground">
                  <th className="pb-2">Bước thực thi</th>
                  <th className="pb-2">Phân loại</th>
                  <th className="pb-2">Trạng thái</th>
                  <th className="pb-2 text-right">Thời gian (ms)</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {detail.spans.map((s, i) => (
                  <tr key={i} className="hover:bg-muted/30">
                    <td className="py-2.5 font-mono text-xs font-medium">{s.span_name}</td>
                    <td className="py-2.5 text-xs text-muted-foreground">{SPAN_TYPE_MAP[s.span_type] ?? s.span_type}</td>
                    <td className="py-2.5 text-xs">
                      <span className={`inline-flex rounded px-2 py-0.5 text-[11px] font-semibold ${
                        s.status === "OK" ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20" : "bg-rose-500/10 text-rose-600 border border-rose-500/20"
                      }`}>
                        {s.status === "OK" ? "Hoàn tất" : s.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">{s.duration_ms.toFixed(1)} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Evaluation V2 Collapsible */}
      {detail.evaluation && (
        <details className="surface-card p-5 group cursor-pointer">
          <summary className="flex items-center justify-between font-semibold text-base list-none focus:outline-none">
            <div className="flex items-center gap-2">
              <FileCode className="h-5 w-5 text-indigo-500" />
              <span>Dữ liệu đánh giá chi tiết (Evaluation)</span>
            </div>
            <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="mt-4 pt-3 border-t">
            <pre className="overflow-x-auto rounded-lg bg-muted/40 p-4 text-xs font-mono text-foreground leading-relaxed">
              {JSON.stringify(detail.evaluation, null, 2)}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  link,
  badge,
  copyable,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
  link?: string;
  badge?: boolean;
  copyable?: boolean;
}) {
  const content = value ?? "N/A";
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      {link ? (
        <Link
          href={link}
          className={`text-primary underline font-medium hover:text-primary/80 inline-flex items-center gap-1 ${
            mono ? "font-mono text-xs" : "text-sm"
          }`}
        >
          {content} <ExternalLink className="h-3 w-3" />
        </Link>
      ) : badge && value ? (
        <span className="inline-flex rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          {content}
        </span>
      ) : (
        <p className={`font-medium ${mono ? "font-mono text-xs break-all" : "text-sm"}`}>{content}</p>
      )}
    </div>
  );
}
