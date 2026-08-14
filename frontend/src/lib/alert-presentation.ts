import type { AlertLevel, SysAlert } from "@/lib/proto-store";

type AlertPatient = {
  id: string;
  name: string;
};

export type PresentedAlert = {
  title: string;
  patientName: string;
  severityLabel: string;
  problem: string;
  evidence: string;
  source: string;
  action: string;
  triggerLabel: string;
  statusLabel: string;
};

const severityLabel: Record<AlertLevel, string> = {
  low: "Nhẹ",
  mid: "Trung bình",
  high: "Nghiêm trọng",
};

const statusLabel: Record<SysAlert["status"], string> = {
  new: "Mới",
  processing: "Đang xử lý",
  acknowledged: "Đã ghi nhận",
  resolved: "Đã xử lý",
};

function findFirst(source: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = source.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return "";
}

function prettyToken(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
}

function extractKeyword(source: string) {
  const raw = findFirst(source, [
    /tu khoa\/nguon=["']([^"']+)["']/i,
    /tu khoa=["']([^"']+)["']/i,
    /tu_khoa=["']([^"']+)["']/i,
  ]);
  return raw
    .replaceAll("'", "")
    .replace(/\s*\+\s*/g, ", ")
    .trim();
}

function triggerLabel(trigger: string) {
  const labels: Record<string, string> = {
    safety_redflag: "Dấu hiệu nguy hiểm",
    missed_dose: "Bỏ lỡ liều thuốc",
    side_effect: "Nghi ngờ tác dụng phụ",
    photo_mismatch: "Ảnh xác minh không khớp",
  };
  return labels[trigger] ?? prettyToken(trigger);
}

function problemFromClassification(classification: string) {
  const labels: Record<string, string> = {
    MISSED: "Bệnh nhân có dấu hiệu bỏ lỡ liều thuốc.",
    DELAYED: "Bệnh nhân có dấu hiệu uống thuốc trễ giờ.",
    SIDE_EFFECT: "Bệnh nhân báo cáo triệu chứng có thể liên quan tác dụng phụ.",
    TAKEN: "Bệnh nhân đã xác nhận dùng thuốc, cần đối chiếu thêm nếu vẫn có cảnh báo.",
  };
  return labels[classification] ?? `Cảnh báo liên quan ${prettyToken(classification)}.`;
}

function actionFor(alert: SysAlert, classification: string, category: string) {
  if (alert.level === "high") {
    return "Kiểm tra ngay nội dung hội thoại, liên hệ người thân/bệnh nhân và cân nhắc xử trí khẩn nếu có triệu chứng nặng.";
  }
  if (classification === "MISSED") {
    return "Xem liều bị bỏ lỡ, nhắc bệnh nhân xác nhận tình trạng hiện tại và đánh giá nguy cơ theo đơn thuốc.";
  }
  if (classification === "SIDE_EFFECT" || category === "clinical_symptom") {
    return "Hỏi rõ thời điểm, mức độ triệu chứng và đối chiếu với thuốc đang dùng trước khi hướng dẫn tiếp.";
  }
  return "Mở chi tiết bệnh nhân để xem ngữ cảnh và cập nhật trạng thái xử lý.";
}

export function presentAlert(alert: SysAlert, patients: AlertPatient[] = []): PresentedAlert {
  const patientName =
    patients.find((p) => p.id === alert.patientId)?.name ?? `BN ${alert.patientId}`;
  const source = `${alert.title} ${alert.detail}`;
  const classification = findFirst(source, [/classification=['"]?([A-Z_]+)['"]?/i]);
  const category = findFirst(source, [/llm_category=['"]([^'"]+)['"]/i]);
  const llmReasoning = findFirst(source, [/llm_reasoning=['"]([^'"]+)['"]/i]);
  const keyword = extractKeyword(source);
  const detectedBy = findFirst(source, [/phat hien qua ([^,]+)/i]);
  const hasSafetyRedflag =
    alert.trigger === "safety_redflag" || /safety layer redflag/i.test(source);

  const problem = hasSafetyRedflag
    ? category === "dosage_risk"
      ? "Bệnh nhân hỏi về liều dùng có nguy cơ vượt mức an toàn."
      : category === "clinical_symptom"
        ? "Bệnh nhân báo cáo triệu chứng cần được đánh giá sớm."
        : "Hệ thống phát hiện nội dung có nguy cơ an toàn."
    : classification
      ? problemFromClassification(classification)
      : alert.title;

  const evidence =
    llmReasoning ||
    (keyword
      ? `Từ khóa phát hiện: ${keyword}.`
      : alert.detail !== alert.trigger
        ? alert.detail
        : "");

  return {
    title:
      alert.level === "high"
        ? `${triggerLabel(alert.trigger)} cần xem ngay`
        : triggerLabel(alert.trigger),
    patientName,
    severityLabel: severityLabel[alert.level],
    problem,
    evidence: evidence || "Chưa có mô tả chi tiết từ hệ thống.",
    source: detectedBy ? `Phát hiện qua ${detectedBy}` : triggerLabel(alert.trigger),
    action: actionFor(alert, classification, category),
    triggerLabel: triggerLabel(alert.trigger),
    statusLabel: statusLabel[alert.status],
  };
}
