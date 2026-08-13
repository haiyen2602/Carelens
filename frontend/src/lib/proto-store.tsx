import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/lib/auth";
import { listPatients } from "@/lib/patients";
import {
  approvePrescription,
  createPrescription as createPrescriptionApi,
  DEMO_DOCTOR_ID,
  listPrescriptions,
  rejectPrescription,
  type PrescriptionItemInput,
  type PrescriptionRecord,
} from "@/lib/prescriptions";
import { listReportingPatients, setPatientWatch, type ReportingPatient } from "@/lib/reporting";
import { listEscalations, type Escalation } from "@/lib/escalations";
import { listAuditLog, type AuditLogEntry } from "@/lib/audit";
import {
  listCaregiverLinksForPatient,
  listMonitoredPatients,
  type MonitoredPatient,
} from "@/lib/caregivers";
import { listDoses, updateDoseStatus, type Dose as DoseRecord } from "@/lib/doses";

export type Role = "doctor" | "patient" | "family";

export type DoseStatus =
  "pending" | "taken" | "unverified" | "missed" | "wrong" | "acknowledged" | "resolved";

// Doi chieu voi backend/db/models.py::DoseEvent - khong co "wrong"/"acknowledged"
// nhu tap hop cu, nhung giu lai trong union de statusLabel/consumer khong vo
// (khong con duong nao tao ra 2 gia tri do tu du lieu that nua).
export type Dose = {
  id: string;
  med: string;
  strength: string;
  time: string;
  meal: string;
  status: DoseStatus;
  reminders: number;
  photo: boolean;
  note?: string;
};

export type Prescription = {
  id: string;
  orderId: string;
  patient: string;
  med: string;
  dose: string;
  perDay: number;
  meal: string;
  note: string;
  times: string[];
  startDate: string;
  endDate: string;
  cycle: { onDays: number; offDays: number } | null;
  status: "draft" | "pending" | "approved" | "rejected";
};

export type AlertLevel = "low" | "mid" | "high";

// `target` (ai duoc thay canh bao nay) khong co trong /escalations that -
// backend chua phan loai canh bao theo doi tuong nhan, nen cac trang doctor
// va patient/family deu doc CHUNG mot danh sach `alerts` (khong loc rieng
// theo vai tro nua, xem doctor/alerts/page.tsx).
export type SysAlert = {
  id: string;
  patientId: string;
  level: AlertLevel;
  title: string;
  detail: string;
  at: string;
  status: "new" | "processing" | "acknowledged" | "resolved";
  doseId?: string;
};

// Thay the AuditEntry cu (actor/action tu bia) bang hinh dang audit-log THAT:
// 1 ban ghi = 1 luot hoi AI cua benh nhan (utterance/final_response/trace).
// Xem doctor/audit/page.tsx da doi theo hinh dang nay.
export type AuditEntry = {
  id: string;
  patientId: string;
  at: string;
  utterance: string;
  finalResponse: string | null;
};

export type Patient = {
  id: string;
  name: string;
  age: number;
  condition: string;
  adherence: number;
  watch: boolean;
};

// Một bệnh nhân có thể đồng thời là người theo dõi (không phải "đăng nhập
// thay") cho người thân khác — chỉ xem được mức tuân thủ và cảnh báo của họ,
// không có quyền xác thực ảnh / báo bác sĩ như một caregiver thật sự.
export type RelativeAlert = { id: string; level: AlertLevel; title: string; at: string };

export type RelativePrescription = { id: string; med: string; dose: string; schedule: string };

export type DoseHistoryStatus = "taken" | "late" | "missed";

// `prescriptions` cua nguoi than duoc theo doi LUON RONG - GET
// /caregiver-links?caregiver_account_id= (BE contract) khong tra kem don
// thuoc cua tung benh nhan, va goi rieng listPrescriptions cho MOI benh nhan
// trong danh sach theo doi se nhan N request khong can thiet cho 1 man hinh
// phu. UI (patient/family/[id]/page.tsx) da co san trang thai rong cho truong
// hop nay ("Chưa có đơn thuốc nào") nen khong can fake du lieu.
export type MonitoredRelative = {
  id: string;
  name: string;
  relationship: string;
  age: number;
  condition: string;
  adherence: number;
  doseTakenToday: number;
  doseTotalToday: number;
  alerts: RelativeAlert[];
  prescriptions: RelativePrescription[];
  weekHistory: { day: string; status: DoseHistoryStatus }[];
};

// `phone` khong co trong GET /caregiver-links?patient_id= (BE contract chi
// tra id/caregiver_account_id/caregiver_name/relationship/created_at) - bo
// truong nay thay vi bia so dien thoai. Xem doctor/family/page.tsx.
export type FamilyContact = {
  id: string;
  patientId: string;
  name: string;
  relation: string;
};

type State = {
  role: Role | null;
  phone: string;
  monitoredRelatives: MonitoredRelative[];
  doses: Dose[];
  prescriptions: Prescription[];
  alerts: SysAlert[];
  audit: AuditEntry[];
  patients: Patient[];
  familyContacts: FamilyContact[];
  healthLog: { id: string; at: string; text: string; level: AlertLevel }[];
  emergency: boolean;
  symptomCheckPending: boolean;
};

const uid = () => Math.random().toString(36).slice(2, 9);

function gioHienThi(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

const initial: State = {
  role: null,
  phone: "",
  monitoredRelatives: [],
  emergency: false,
  doses: [],
  // Du lieu mau chi hien thi tam - ProtoProvider tu tai ngay khi mount va ghi
  // de bang phac do that (POST /api/v1/prescriptions), xem refreshPrescriptions.
  prescriptions: [],
  alerts: [],
  audit: [],
  patients: [],
  familyContacts: [],
  healthLog: [],
  symptomCheckPending: false,
};

type Ctx = State & {
  login: (role: Role, phone: string) => void;
  logout: () => void;
  respondDose: (id: string, taken: boolean) => Promise<void>;
  sendPhoto: (id: string) => Promise<void>;
  remindAgain: (id: string) => void;
  markMissed: (id: string) => Promise<void>;
  reportHealth: (text: string, level: AlertLevel) => void;
  requestSymptomCheck: () => void;
  clearSymptomCheck: () => void;
  setEmergency: (v: boolean) => void;
  // `id` la id gop (xem flattenPrescriptions) - duyet/tu choi mot dong se
  // duyet/tu choi CA phac do that dang sau no (moi thuoc trong don). UI gop
  // nhieu dong cung orderId thanh 1 the (xem queue/page.tsx groupOrders) nen
  // chi can truyen id CUA MOT dong trong don la du.
  decidePrescription: (id: string, ok: boolean) => Promise<void>;
  // Gui MOT LAN cho ca don (nhieu thuoc), khong phai tung thuoc mot - hai
  // thuoc cung gio phai nam chung mot phac do de backend gop dung 1 dose_event
  // (backend/services/scheduling/generator.py).
  createPrescription: (input: {
    patientId: string;
    note?: string;
    items: PrescriptionItemInput[];
  }) => Promise<void>;
  // Chua co API sua don o backend (chi co create/list/approve/reject/stop) -
  // ham nay CHI sua state cuc bo, mat khi refresh trang. Giu lai de nut "Dieu
  // chinh thu cong" o queue/page.tsx khong vo, cho toi khi co endpoint that.
  updatePrescription: (id: string, patch: Partial<Omit<Prescription, "id" | "orderId">>) => void;
  verifyDose: (doseId: string, verdict: "correct" | "wrong" | "unclear" | "absent") => Promise<void>;
  familyConfirmDose: (id: string, taken: boolean) => Promise<void>;
  // Chua co API sua trang thai escalation o backend (BE contract chi co GET
  // /escalations) - ham nay CHI sua state cuc bo, mat khi refresh trang.
  // Cung ly do/gioi han voi updatePrescription o tren.
  setAlertStatus: (id: string, status: SysAlert["status"]) => void;
  toggleWatch: (id: string) => Promise<void>;
};

const ProtoContext = createContext<Ctx | null>(null);

// backend/services/prescription/service.py dung 5 trang thai: draft|active|
// rejected|stopped|completed. UI hien tai chi phan biet 3 nhom (cho duyet/da
// duyet/tu choi) - stopped va completed gop chung vao "approved" vi chua co
// nut "Dung phac do" nao trong UI de tao ra 2 trang thai do qua luong nay.
function anhXaTrangThai(status: string): Prescription["status"] {
  if (status === "draft") return "pending";
  if (status === "rejected") return "rejected";
  return "approved"; // active | stopped | completed
}

// Ky tu noi id phac do that voi so thu tu thuoc khi rai phang - "::" khong
// xuat hien trong uuid nen tach lai an toan.
const NOI_ID = "::";

/**
 * Rai MOT phac do that (nhieu thuoc, `items[]`) thanh NHIEU dong kieu
 * `Prescription` cu (1 dong = 1 thuoc) - de queue/dashboard/badge dung nguyen
 * khong phai doi UI. Duyet/tu choi mot dong se goi API tren CA phac do goc
 * (moi thuoc di theo nhau), nen sau khi tai lai ca nhom dong cung doi trang
 * thai mot luc - dung y, vi chung von la mot don.
 */
// Backend chua tra cycle (dot uong - dot nghi) va luon co duration_days huu
// han (mac dinh 7, xem service.py::SO_NGAY_MAC_DINH) nen tinh duoc endDate.
function tinhNgayKetThuc(startDate: string, durationDays: number): string {
  const d = new Date(`${startDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + durationDays);
  return d.toISOString().slice(0, 10);
}

function flattenPrescriptions(records: PrescriptionRecord[], tenBenhNhan: Record<string, string>): Prescription[] {
  const ra: Prescription[] = [];
  for (const p of records) {
    const trangThai = anhXaTrangThai(p.status);
    p.items.forEach((item, idx) => {
      ra.push({
        id: `${p.id}${NOI_ID}${idx}`,
        orderId: p.id,
        patient: tenBenhNhan[p.patientId] ?? p.patientId,
        med: item.tenThuoc,
        dose: item.lieuDung,
        perDay: item.gioNhac.length || 1,
        meal: "",
        note: p.note ?? "",
        times: item.gioNhac,
        startDate: p.startDate,
        endDate: tinhNgayKetThuc(p.startDate, p.durationDays),
        cycle: null,
        status: trangThai,
      });
    });
  }
  return ra;
}

// PENDING|TAKEN|DELAYED|MISSED|CANCELLED|AWAITING_CAREGIVER (backend/db/
// models.py::DoseEvent) -> vocab DoseStatus cu de statusLabel/UI hien co
// khong phai doi ten truong. Khong co "wrong" that (chi co qua verifyDose
// cuc bo, xem comment o duoi).
function anhXaTrangThaiLieu(status: string): DoseStatus {
  switch (status) {
    case "TAKEN":
    case "DELAYED":
      return "taken";
    case "MISSED":
      return "missed";
    case "AWAITING_CAREGIVER":
      return "unverified";
    case "CANCELLED":
      return "resolved";
    default:
      return "pending";
  }
}

function moTaThuoc(d: DoseRecord): { med: string; strength: string } {
  const ten = d.expectedItems.map((it) => it.tenThuoc).join(", ") || "(chưa rõ tên thuốc)";
  const luong = d.expectedItems
    .map((it) => `${it.soVien} ${it.dangThuoc ?? "đơn vị"}`)
    .join(", ");
  return { med: ten, strength: luong };
}

function toDose(d: DoseRecord): Dose {
  const { med, strength } = moTaThuoc(d);
  return {
    id: d.id,
    med,
    strength,
    time: gioHienThi(d.scheduledAt),
    meal: "",
    status: anhXaTrangThaiLieu(d.status),
    reminders: 0,
    photo: false,
  };
}

function anhXaMucDo(severity: string): AlertLevel {
  if (severity === "HIGH") return "high";
  if (severity === "MEDIUM") return "mid";
  return "low";
}

function anhXaTrangThaiCanhBao(status: string): SysAlert["status"] {
  if (status === "ACKED") return "acknowledged";
  if (status === "RESOLVED") return "resolved";
  return "new"; // OPEN
}

function toSysAlert(e: Escalation): SysAlert {
  return {
    id: e.id,
    patientId: e.patientId,
    level: anhXaMucDo(e.severity),
    title: e.reason || e.trigger,
    detail: e.rawUtterance || e.trigger,
    at: gioHienThi(e.createdAt),
    status: anhXaTrangThaiCanhBao(e.status),
    doseId: e.doseEventId ?? undefined,
  };
}

function toAuditEntry(a: AuditLogEntry): AuditEntry {
  return {
    id: a.id,
    patientId: a.patientId,
    at: gioHienThi(a.createdAt),
    utterance: a.utterance,
    finalResponse: a.finalResponse,
  };
}

function tinhTuoi(yearOfBirth: number | null): number {
  return yearOfBirth ? new Date().getFullYear() - yearOfBirth : 0;
}

function toPatient(p: ReportingPatient): Patient {
  return {
    id: p.id,
    name: p.fullName,
    age: tinhTuoi(p.yearOfBirth),
    condition: p.note ?? "",
    adherence: p.adherencePct ?? 0,
    watch: p.watch,
  };
}

const THU_VN = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function toMonitoredRelative(m: MonitoredPatient): MonitoredRelative {
  return {
    id: m.patientId,
    name: m.fullName,
    relationship: m.relationship,
    age: tinhTuoi(m.yearOfBirth),
    condition: m.note ?? "",
    adherence: m.adherencePct ?? 0,
    doseTakenToday: m.doseTakenToday,
    doseTotalToday: m.doseTotalToday,
    alerts: m.openEscalations.map((e) => ({
      id: e.id,
      level: anhXaMucDo(e.level),
      title: e.title,
      at: gioHienThi(e.createdAt),
    })),
    prescriptions: [],
    weekHistory: m.weekHistory.map((h) => ({
      day: THU_VN[new Date(`${h.date}T00:00:00`).getDay()],
      status: h.status,
    })),
  };
}

export function ProtoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(initial);
  const { user } = useAuth();
  // Chi dung de dich patient_id -> ten hien thi trong flattenPrescriptions,
  // KHONG lien quan mang `patients` mock (age/condition/adherence/watch) -
  // hai nguon phuc vu hai muc dich khac han nhau, xem lib/patients.ts.
  const [tenBenhNhanThat, setTenBenhNhanThat] = useState<Record<string, string>>({});

  const refreshPrescriptions = useCallback(async () => {
    const [records, benhNhan] = await Promise.all([listPrescriptions(), listPatients()]);
    const tenMoi = Object.fromEntries(benhNhan.map((b) => [b.id, b.fullName]));
    setTenBenhNhanThat(tenMoi);
    setState((s) => ({ ...s, prescriptions: flattenPrescriptions(records, tenMoi) }));
  }, []);

  useEffect(() => {
    refreshPrescriptions().catch((err) => {
      // Khong chan render ca app vi mot lan tai loi - trang doctor/queue,
      // doctor/page se chi thay danh sach rong cho toi lan refresh ke tiep.
      console.error("Không tải được danh sách phác đồ:", err);
    });
  }, [refreshPrescriptions]);

  // Lieu hom nay/lich su cua CHINH benh nhan dang dang nhap - GET /doses can
  // patient_id (khong co endpoint liet ke toan bo lieu moi benh nhan), nen
  // chi tai duoc khi da biet patient_id that (user.patient_id tu /auth/me).
  const refreshDoses = useCallback(async (patientId: string | null | undefined) => {
    if (!patientId) {
      setState((s) => ({ ...s, doses: [] }));
      return;
    }
    const records = await listDoses(patientId);
    setState((s) => ({ ...s, doses: records.map(toDose) }));
  }, []);

  const refreshEscalations = useCallback(async () => {
    const records = await listEscalations();
    setState((s) => ({ ...s, alerts: records.map(toSysAlert) }));
  }, []);

  const refreshAudit = useCallback(async () => {
    const records = await listAuditLog();
    setState((s) => ({ ...s, audit: records.map(toAuditEntry) }));
  }, []);

  const refreshReportingPatients = useCallback(async () => {
    const records = await listReportingPatients();
    const patients = records.map(toPatient);
    setState((s) => ({ ...s, patients }));

    // Nguoi than cua TUNG benh nhan (doctor/family/page.tsx can xem theo
    // benh nhan) - khong co endpoint liet ke gop tat ca link 1 lan, nen goi
    // song song theo tung patient_id (chap nhan duoc o quy mo prototype).
    const linkLists = await Promise.all(
      patients.map((p) =>
        listCaregiverLinksForPatient(p.id).catch(() => [] as Awaited<ReturnType<typeof listCaregiverLinksForPatient>>),
      ),
    );
    const familyContacts: FamilyContact[] = linkLists.flatMap((links, i) =>
      links.map((l) => ({
        id: l.id,
        patientId: patients[i].id,
        name: l.caregiverName,
        relation: l.relationship,
      })),
    );
    setState((s) => ({ ...s, familyContacts }));
  }, []);

  const refreshMonitoredRelatives = useCallback(async (caregiverAccountId: string | null | undefined) => {
    if (!caregiverAccountId) {
      setState((s) => ({ ...s, monitoredRelatives: [] }));
      return;
    }
    const records = await listMonitoredPatients(caregiverAccountId);
    setState((s) => ({ ...s, monitoredRelatives: records.map(toMonitoredRelative) }));
  }, []);

  useEffect(() => {
    refreshDoses(user?.patient_id).catch((err) => {
      console.error("Không tải được lịch uống thuốc:", err);
    });
    refreshEscalations().catch((err) => {
      console.error("Không tải được danh sách cảnh báo:", err);
    });
    refreshAudit().catch((err) => {
      console.error("Không tải được audit log:", err);
    });
    refreshReportingPatients().catch((err) => {
      console.error("Không tải được danh sách bệnh nhân:", err);
    });
    // Mot benh nhan cung co the la nguoi theo doi nguoi khac (xem comment o
    // MonitoredRelative) - dung id tai khoan dang dang nhap lam
    // caregiver_account_id, khong gioi han theo role.
    refreshMonitoredRelatives(user?.id).catch((err) => {
      console.error("Không tải được danh sách người thân theo dõi:", err);
    });
  }, [
    user?.id,
    user?.patient_id,
    refreshDoses,
    refreshEscalations,
    refreshAudit,
    refreshReportingPatients,
    refreshMonitoredRelatives,
  ]);

  const value = useMemo<Ctx>(
    () => ({
      ...state,
      login: (role, phone) => {
        setState((s) => ({ ...s, role, phone }));
      },
      logout: () => setState((s) => ({ ...s, role: null, phone: "" })),
      respondDose: async (id, taken) => {
        // "Da uong" (taken=true) van cho anh xac nhan that (xem
        // submitDosePhoto o patient/page.tsx) - o day chi xu ly nhanh nhat
        // truong hop bao CHUA UONG, ghi nhan MISSED ngay tren backend.
        if (!taken) {
          await updateDoseStatus(id, "MISSED");
          await refreshDoses(user?.patient_id);
          await refreshEscalations();
        }
      },
      sendPhoto: async (id) => {
        await updateDoseStatus(id, "TAKEN");
        await refreshDoses(user?.patient_id);
        await refreshEscalations();
      },
      // Chua co API "nhac lai" o backend (nhac tu dong theo reminder_count
      // cua escalation, khong co thao tac thu cong) - giu ham rong de nut
      // trong UI khong vo, khong fake so lan nhac nua.
      remindAgain: () => undefined,
      markMissed: async (id) => {
        await updateDoseStatus(id, "MISSED");
        await refreshDoses(user?.patient_id);
        await refreshEscalations();
      },
      reportHealth: (text, level) => {
        setState((s) => ({
          ...s,
          healthLog: [{ id: uid(), at: gioHienThi(new Date().toISOString()), text, level }, ...s.healthLog],
        }));
      },
      requestSymptomCheck: () => setState((s) => ({ ...s, symptomCheckPending: true })),
      clearSymptomCheck: () => setState((s) => ({ ...s, symptomCheckPending: false })),
      setEmergency: (v) => setState((s) => ({ ...s, emergency: v })),
      decidePrescription: async (id, ok) => {
        const prescriptionId = id.split(NOI_ID)[0];
        await (ok ? approvePrescription(prescriptionId) : rejectPrescription(prescriptionId));
        await refreshPrescriptions();
      },
      createPrescription: async (input) => {
        await createPrescriptionApi({
          patientId: input.patientId,
          doctorId: DEMO_DOCTOR_ID,
          note: input.note,
          items: input.items,
        });
        await refreshPrescriptions();
      },
      updatePrescription: (id, patch) => {
        setState((s) => ({
          ...s,
          prescriptions: s.prescriptions.map((p) => (p.id === id ? { ...p, ...patch } : p)),
        }));
      },
      // Khong co trang thai "WRONG" that tren backend (chi PENDING|TAKEN|
      // DELAYED|MISSED|CANCELLED|AWAITING_CAREGIVER) - chi "correct" moi goi
      // API that (-> TAKEN); cac phan quyet con lai (wrong/unclear/absent)
      // khong co hanh dong backend tuong ung nen chi refetch, khong sua gi.
      verifyDose: async (doseId, verdict) => {
        if (verdict === "correct") {
          await updateDoseStatus(doseId, "TAKEN");
          await refreshDoses(user?.patient_id);
          await refreshEscalations();
        }
      },
      familyConfirmDose: async (id, taken) => {
        await updateDoseStatus(id, taken ? "TAKEN" : "MISSED");
        await refreshDoses(user?.patient_id);
        await refreshEscalations();
      },
      setAlertStatus: (id, status) => {
        setState((s) => ({
          ...s,
          alerts: s.alerts.map((a) => (a.id === id ? { ...a, status } : a)),
        }));
      },
      toggleWatch: async (id) => {
        const p = state.patients.find((x) => x.id === id);
        await setPatientWatch(id, !(p?.watch ?? false));
        await refreshReportingPatients();
      },
    }),
    [state, user, refreshPrescriptions, refreshDoses, refreshEscalations, refreshReportingPatients],
  );

  return <ProtoContext.Provider value={value}>{children}</ProtoContext.Provider>;
}

export function useProto() {
  const ctx = useContext(ProtoContext);
  if (!ctx) throw new Error("useProto must be used inside ProtoProvider");
  return ctx;
}

export const statusLabel: Record<DoseStatus, string> = {
  pending: "Chờ uống",
  taken: "Đã uống",
  unverified: "Chưa xác thực",
  missed: "Bỏ liều",
  wrong: "Uống sai",
  acknowledged: "Đã ghi nhận",
  resolved: "Đã xử lý",
};
