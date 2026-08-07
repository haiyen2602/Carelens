import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type Role = "doctor" | "patient" | "family";

export type DoseStatus =
  "pending" | "taken" | "unverified" | "missed" | "wrong" | "acknowledged" | "resolved";

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
  patient: string;
  med: string;
  dose: string;
  perDay: number;
  meal: string;
  note: string;
  times: string[];
  status: "draft" | "pending" | "approved" | "rejected";
};

export type AlertLevel = "low" | "mid" | "high";

export type SysAlert = {
  id: string;
  level: AlertLevel;
  title: string;
  detail: string;
  at: string;
  target: Role[];
  status: "new" | "processing" | "acknowledged" | "resolved";
  doseId?: string;
};

export type AuditEntry = { id: string; at: string; actor: string; action: string };

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

const MONITORED_RELATIVES: MonitoredRelative[] = [
  {
    id: "rel-minh",
    name: "Trần Văn Minh",
    relationship: "Bố chồng",
    age: 74,
    condition: "Đái tháo đường type 2",
    adherence: 92,
    doseTakenToday: 1,
    doseTotalToday: 2,
    alerts: [{ id: "ra1", level: "low", title: "Trễ liều chiều 20 phút", at: "19:20" }],
    prescriptions: [
      { id: "rp1", med: "Metformin 850mg", dose: "1 viên", schedule: "2 lần/ngày · sau ăn" },
      {
        id: "rp2",
        med: "Losartan 50mg",
        dose: "1 viên",
        schedule: "1 lần/ngày · buổi sáng",
      },
    ],
    weekHistory: [
      { day: "T2", status: "taken" },
      { day: "T3", status: "taken" },
      { day: "T4", status: "late" },
      { day: "T5", status: "taken" },
      { day: "T6", status: "taken" },
      { day: "T7", status: "taken" },
      { day: "CN", status: "late" },
    ],
  },
  {
    id: "rel-hoa",
    name: "Lê Thị Hoa",
    relationship: "Mẹ",
    age: 61,
    condition: "Rối loạn lipid máu",
    adherence: 68,
    doseTakenToday: 0,
    doseTotalToday: 1,
    alerts: [
      { id: "ra2", level: "mid", title: "Bỏ liều sáng nay", at: "08:15" },
      { id: "ra3", level: "low", title: "Chưa gửi ảnh xác nhận thuốc", at: "08:00" },
    ],
    prescriptions: [
      {
        id: "rp3",
        med: "Atorvastatin 20mg",
        dose: "1 viên",
        schedule: "1 lần/ngày · trước khi ngủ",
      },
    ],
    weekHistory: [
      { day: "T2", status: "taken" },
      { day: "T3", status: "missed" },
      { day: "T4", status: "taken" },
      { day: "T5", status: "missed" },
      { day: "T6", status: "late" },
      { day: "T7", status: "taken" },
      { day: "CN", status: "missed" },
    ],
  },
];

type State = {
  role: Role | null;
  phone: string;
  monitoredRelatives: MonitoredRelative[];
  doses: Dose[];
  prescriptions: Prescription[];
  alerts: SysAlert[];
  audit: AuditEntry[];
  patients: Patient[];
  healthLog: { id: string; at: string; text: string; level: AlertLevel }[];
  emergency: boolean;
};

const now = () => new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

const uid = () => Math.random().toString(36).slice(2, 9);

const initial: State = {
  role: null,
  phone: "",
  monitoredRelatives: MONITORED_RELATIVES,
  emergency: false,
  doses: [
    {
      id: "d1",
      med: "Paracetamol",
      strength: "500mg · 1 viên",
      time: "09:30",
      meal: "Sau ăn sáng",
      status: "pending",
      reminders: 0,
      photo: false,
    },
    {
      id: "d2",
      med: "Amlodipine",
      strength: "5mg · 1 viên",
      time: "13:00",
      meal: "Sau ăn trưa",
      status: "pending",
      reminders: 0,
      photo: false,
    },
    {
      id: "d3",
      med: "Metformin",
      strength: "850mg · 1 viên",
      time: "07:00",
      meal: "Sau ăn sáng",
      status: "taken",
      reminders: 1,
      photo: true,
    },
    {
      id: "d4",
      med: "Atorvastatin",
      strength: "20mg · 1 viên",
      time: "21:00",
      meal: "Trước khi ngủ",
      status: "unverified",
      reminders: 2,
      photo: true,
      note: "Ảnh chụp mờ, cần người thân đối chiếu",
    },
  ],
  prescriptions: [
    {
      id: "p1",
      patient: "Nguyễn Thị Lan",
      med: "Amlodipine 5mg",
      dose: "1 viên",
      perDay: 1,
      meal: "Sau ăn trưa",
      note: "Theo dõi huyết áp mỗi sáng",
      times: ["13:00"],
      status: "pending",
    },
    {
      id: "p2",
      patient: "Trần Văn Minh",
      med: "Metformin 850mg",
      dose: "1 viên",
      perDay: 2,
      meal: "Sau ăn",
      note: "Đề xuất AI: đổi 07:00 → 07:30 do bệnh nhân thường ăn muộn",
      times: ["07:30", "19:00"],
      status: "pending",
    },
  ],
  alerts: [
    {
      id: "a1",
      level: "mid",
      title: "Ảnh thuốc không xác thực được",
      detail:
        "Bệnh nhân Nguyễn Thị Lan gửi ảnh liều Atorvastatin 21:00 nhưng AI không đối chiếu được viên thuốc.",
      at: "21:14",
      target: ["family", "doctor"],
      status: "new",
      doseId: "d4",
    },
    {
      id: "a2",
      level: "low",
      title: "Trễ liều 15 phút",
      detail: "Liều Paracetamol 09:30 chưa được phản hồi sau nhắc lần 1.",
      at: "09:45",
      target: ["family"],
      status: "new",
      doseId: "d1",
    },
  ],
  audit: [
    {
      id: "l1",
      at: "08:02",
      actor: "BS. Phạm Quốc Huy",
      action: "Duyệt phác đồ #P0114 cho Trần Văn Minh",
    },
    {
      id: "l2",
      at: "07:05",
      actor: "Hệ thống",
      action: "Ghi nhận TAKEN liều Metformin 07:00 (có ảnh)",
    },
  ],
  patients: [
    {
      id: "bn1",
      name: "Nguyễn Thị Lan",
      age: 68,
      condition: "Tăng huyết áp",
      adherence: 85,
      watch: true,
    },
    {
      id: "bn2",
      name: "Trần Văn Minh",
      age: 74,
      condition: "Đái tháo đường type 2",
      adherence: 92,
      watch: false,
    },
    {
      id: "bn3",
      name: "Lê Thị Hoa",
      age: 61,
      condition: "Rối loạn lipid máu",
      adherence: 68,
      watch: true,
    },
  ],
  healthLog: [],
};

type Ctx = State & {
  login: (role: Role, phone: string) => void;
  logout: () => void;
  respondDose: (id: string, taken: boolean) => void;
  sendPhoto: (id: string) => void;
  remindAgain: (id: string) => void;
  markMissed: (id: string) => void;
  reportHealth: (text: string, level: AlertLevel) => void;
  setEmergency: (v: boolean) => void;
  decidePrescription: (id: string, ok: boolean) => void;
  createPrescription: (p: Omit<Prescription, "id" | "status">) => void;
  verifyDose: (doseId: string, verdict: "correct" | "wrong" | "unclear" | "absent") => void;
  setAlertStatus: (id: string, status: SysAlert["status"]) => void;
  escalateToDoctor: (id: string) => void;
  toggleWatch: (id: string) => void;
};

const ProtoContext = createContext<Ctx | null>(null);

export function ProtoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(initial);

  const log = useCallback((actor: string, action: string) => {
    setState((s) => ({
      ...s,
      audit: [{ id: uid(), at: now(), actor, action }, ...s.audit],
    }));
  }, []);

  const pushAlert = useCallback((a: Omit<SysAlert, "id" | "at" | "status">) => {
    setState((s) => ({
      ...s,
      alerts: [{ ...a, id: uid(), at: now(), status: "new" }, ...s.alerts],
    }));
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      ...state,
      login: (role, phone) => {
        setState((s) => ({ ...s, role, phone }));
        log(
          role === "doctor" ? "Bác sĩ" : role === "patient" ? "Bệnh nhân" : "Người thân",
          "Đăng nhập bằng OTP",
        );
      },
      logout: () => setState((s) => ({ ...s, role: null, phone: "" })),
      respondDose: (id, taken) => {
        setState((s) => ({
          ...s,
          doses: s.doses.map((d) =>
            d.id === id ? { ...d, status: taken ? "unverified" : d.status } : d,
          ),
        }));
        log("Bệnh nhân", taken ? `Trả lời ĐÃ UỐNG liều #${id}` : `Trả lời CHƯA UỐNG liều #${id}`);
      },
      sendPhoto: (id) => {
        setState((s) => ({
          ...s,
          doses: s.doses.map((d) => (d.id === id ? { ...d, photo: true, status: "taken" } : d)),
        }));
        log("Hệ thống", `AI đối chiếu ảnh thuốc liều #${id} → TAKEN`);
      },
      remindAgain: (id) => {
        setState((s) => ({
          ...s,
          doses: s.doses.map((d) => (d.id === id ? { ...d, reminders: d.reminders + 1 } : d)),
        }));
        const dose = state.doses.find((d) => d.id === id);
        if (dose && dose.reminders + 1 >= 3) {
          pushAlert({
            level: "mid",
            title: "Nhắc lần 3 không phản hồi",
            detail: `Liều ${dose.med} ${dose.time} đã nhắc 3 lần, bệnh nhân chưa phản hồi.`,
            target: ["family"],
            doseId: id,
          });
        }
      },
      markMissed: (id) => {
        setState((s) => ({
          ...s,
          doses: s.doses.map((d) => (d.id === id ? { ...d, status: "missed" } : d)),
        }));
        const dose = state.doses.find((d) => d.id === id);
        pushAlert({
          level: "mid",
          title: "MISSED — hết dose window",
          detail: `Liều ${dose?.med ?? ""} ${dose?.time ?? ""} không được uống trong khung an toàn ±30 phút.`,
          target: ["family", "doctor"],
          doseId: id,
        });
        log("Hệ thống", `Ghi nhận MISSED liều #${id}`);
      },
      reportHealth: (text, level) => {
        setState((s) => ({
          ...s,
          healthLog: [{ id: uid(), at: now(), text, level }, ...s.healthLog],
        }));
        if (level !== "low") {
          pushAlert({
            level: level === "high" ? "high" : "mid",
            title:
              level === "high"
                ? "Cảnh báo sức khỏe nghiêm trọng"
                : "Vấn đề sức khỏe mức trung bình",
            detail: text,
            target: level === "high" ? ["family", "doctor"] : ["family"],
          });
        }
        log("Bệnh nhân", `Báo vấn đề sức khỏe (${level}): ${text}`);
      },
      setEmergency: (v) => setState((s) => ({ ...s, emergency: v })),
      decidePrescription: (id, ok) => {
        setState((s) => ({
          ...s,
          prescriptions: s.prescriptions.map((p) =>
            p.id === id ? { ...p, status: ok ? "approved" : "rejected" } : p,
          ),
        }));
        const p = state.prescriptions.find((x) => x.id === id);
        log(
          "BS. Phạm Quốc Huy",
          `${ok ? "Duyệt" : "Từ chối"} phác đồ ${p?.med ?? id} — ${p?.patient ?? ""}`,
        );
      },
      createPrescription: (p) => {
        setState((s) => ({
          ...s,
          prescriptions: [{ ...p, id: uid(), status: "pending" }, ...s.prescriptions],
        }));
        log("BS. Phạm Quốc Huy", `Tạo đơn thuốc ${p.med} cho ${p.patient}, chờ duyệt HITL`);
      },
      verifyDose: (doseId, verdict) => {
        const map = {
          correct: "taken",
          wrong: "wrong",
          unclear: "unverified",
          absent: "unverified",
        } as const;
        setState((s) => ({
          ...s,
          doses: s.doses.map((d) => (d.id === doseId ? { ...d, status: map[verdict] } : d)),
          alerts: s.alerts.map((a) =>
            a.doseId === doseId
              ? { ...a, status: verdict === "correct" ? "resolved" : "processing" }
              : a,
          ),
        }));
        log("Người thân", `Phán quyết ảnh liều #${doseId}: ${verdict}`);
        if (verdict === "wrong") {
          pushAlert({
            level: "high",
            title: "Uống sai thuốc",
            detail: "Người thân xác nhận bệnh nhân uống sai thuốc. Cần bác sĩ xem xét.",
            target: ["doctor"],
            doseId,
          });
        }
      },
      setAlertStatus: (id, status) => {
        setState((s) => ({
          ...s,
          alerts: s.alerts.map((a) => (a.id === id ? { ...a, status } : a)),
        }));
        log("Người thân", `Cập nhật cảnh báo #${id} → ${status}`);
      },
      escalateToDoctor: (id) => {
        setState((s) => ({
          ...s,
          alerts: s.alerts.map((a) =>
            a.id === id ? { ...a, status: "processing", target: ["doctor"] } : a,
          ),
        }));
        log("Người thân", `Chuyển cảnh báo #${id} tới bác sĩ`);
      },
      toggleWatch: (id) => {
        setState((s) => ({
          ...s,
          patients: s.patients.map((p) => (p.id === id ? { ...p, watch: !p.watch } : p)),
        }));
      },
    }),
    [state, log, pushAlert],
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
