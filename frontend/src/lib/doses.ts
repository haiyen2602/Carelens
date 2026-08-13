// Lich uong thuoc va luong xac nhan bang anh THAT (ADR-0011), qua /api/doses
// va /api/photo-verifications (route noi bo cua chinh FE, giu X-Internal-Secret
// an toan phia server - cung mau voi lib/prescriptions.ts).

export type DoseItem = {
  drugId: string;
  tenThuoc: string;
  soVien: number;
  dangThuoc?: string;
  duongDung?: string;
};

export type Dose = {
  id: string;
  prescriptionId: string;
  scheduledAt: string;
  windowStart: string;
  windowEnd: string;
  status: string; // PENDING|TAKEN|MISSED|DELAYED|CANCELLED|AWAITING_CAREGIVER
  expectedItems: DoseItem[];
};

// dang_xu_ly khong nam trong 3 gia tri matcher.KetQua (khop/lech/khong_xac_minh_duoc)
// - no ta trang thai XU LY, chua co ket qua nghiep vu (backend/services/
// photo_verification/verifier.py). loi_he_thong tuong tu: mo hinh/mang loi,
// khong phai loi cua benh nhan, khong tinh vao han muc chup lai.
export type TrangThaiXacMinh =
  "dang_xu_ly" | "khop" | "lech" | "khong_xac_minh_duoc" | "loi_he_thong";
export type NextAction = "NONE" | "RETAKE" | "CAREGIVER_REVIEW" | null;

export type PhotoVerification = {
  id: string;
  doseEventId: string;
  attempt: number;
  maxAttempts: number;
  status: TrangThaiXacMinh;
  matched: boolean | null;
  expectedByForm: Record<string, number>;
  detectedByForm: Record<string, number>;
  confidence: string | null;
  nextAction: NextAction;
  message: string;
};

type DoseApiItem = {
  id: string;
  prescription_id: string;
  scheduled_at: string;
  window_start: string;
  window_end: string;
  status: string;
  expected_items: {
    drug_id: string;
    ten_thuoc: string;
    so_vien?: number;
    dang_thuoc?: string;
    duong_dung?: string;
  }[];
};

type PhotoVerificationApi = {
  id: string;
  dose_event_id: string;
  attempt: number;
  max_attempts: number;
  status: TrangThaiXacMinh;
  matched: boolean | null;
  expected_by_form: Record<string, number>;
  detected_by_form: Record<string, number>;
  confidence: string | null;
  next_action: NextAction;
  message: string;
};

async function loi(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  const message =
    typeof detail === "string"
      ? detail
      : (detail?.message ?? `Yêu cầu thất bại (${response.status})`);
  throw new Error(message);
}

function toDose(d: DoseApiItem): Dose {
  return {
    id: d.id,
    prescriptionId: d.prescription_id,
    scheduledAt: d.scheduled_at,
    windowStart: d.window_start,
    windowEnd: d.window_end,
    status: d.status,
    expectedItems: (d.expected_items ?? []).map((it) => ({
      drugId: it.drug_id,
      tenThuoc: it.ten_thuoc,
      soVien: it.so_vien ?? 0,
      dangThuoc: it.dang_thuoc,
      duongDung: it.duong_dung,
    })),
  };
}

function toPhotoVerification(p: PhotoVerificationApi): PhotoVerification {
  return {
    id: p.id,
    doseEventId: p.dose_event_id,
    attempt: p.attempt,
    maxAttempts: p.max_attempts,
    status: p.status,
    matched: p.matched,
    expectedByForm: p.expected_by_form,
    detectedByForm: p.detected_by_form,
    confidence: p.confidence,
    nextAction: p.next_action,
    message: p.message,
  };
}

export async function listDoses(patientId: string): Promise<Dose[]> {
  const response = await fetch(`/api/doses?patient_id=${encodeURIComponent(patientId)}`);
  if (!response.ok) return loi(response);
  const items: DoseApiItem[] = await response.json();
  return items.map(toDose);
}

export async function updateDoseStatus(doseId: string, status: string): Promise<Dose> {
  const response = await fetch(`/api/doses/${encodeURIComponent(doseId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) return loi(response);
  return toDose(await response.json());
}

/**
 * Gửi ảnh xác nhận. Trả về ngay (202) — một lần gọi mô hình đo được 26 đến
 * 265 giây, backend không giữ request chờ. Dùng `pollPhotoVerification` để
 * hỏi lại kết quả.
 */
export async function submitDosePhoto(
  doseId: string,
  file: File | Blob,
): Promise<PhotoVerification> {
  const form = new FormData();
  form.append("file", file, "anh_thuoc.jpg");

  const response = await fetch(`/api/doses/${encodeURIComponent(doseId)}/photo`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) return loi(response);
  const data = await response.json();
  // POST tra PhotoSubmitResponse (verification_id) - goi lai GET 1 lan de co
  // du hinh dang PhotoVerification, khong tu ghep tay o day tranh 2 nguon
  // dinh dang lech nhau.
  return getPhotoVerification(data.verification_id);
}

export async function getPhotoVerification(verificationId: string): Promise<PhotoVerification> {
  const response = await fetch(`/api/photo-verifications/${encodeURIComponent(verificationId)}`);
  if (!response.ok) return loi(response);
  return toPhotoVerification(await response.json());
}

const KHOANG_CACH_HOI_LAI_MS = 6000;
const SO_LAN_HOI_TOI_DA = 60; // 60 x 6s = 6 phut, du rong cho tran 265s da do duoc

/**
 * Hỏi lại tới khi có kết quả thật (không còn "dang_xu_ly"). `onCapNhat` được
 * gọi sau MỖI lần hỏi (kể cả khi vẫn đang xử lý) để UI cập nhật số lần đã chờ.
 */
export async function pollPhotoVerification(
  verificationId: string,
  onCapNhat?: (v: PhotoVerification) => void,
): Promise<PhotoVerification> {
  for (let lan = 0; lan < SO_LAN_HOI_TOI_DA; lan++) {
    const ketQua = await getPhotoVerification(verificationId);
    onCapNhat?.(ketQua);
    if (ketQua.status !== "dang_xu_ly") return ketQua;
    await new Promise((r) => setTimeout(r, KHOANG_CACH_HOI_LAI_MS));
  }
  throw new Error("Phân tích ảnh mất quá lâu, bác thử lại giúp cháu nhé.");
}
