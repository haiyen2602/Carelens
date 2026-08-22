"use client";

// Tab "Người thân" (Capy Circle) - port tu capyphone.js::renderFamily() +
// renderSheetNudge(). Giu nguyen logic that: danh sach nguoi than dang
// theo doi, loi moi den/di, tim benh nhan de moi.
//
// Ban mau hard-code 3 nguoi (Me/Bo/Chi Lan) va 1 the canh bao co dinh.
// O day: the canh bao chi hien khi CO canh bao that, danh sach lay tu API,
// tien do lay tu so lieu that. Sheet "Nhac nhe" gui loi nhac -> CHUA co
// API nen la nut bao truoc (toast), khong gia vo la da gui.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CHIP,
  CapyPrimaryButton,
  CapySecondaryButton,
  CapySheet,
  PillChip,
  SectionLabel,
  type ChipStyle,
} from "@/components/capy/capy-ui";
import { useAuth } from "@/lib/auth";
import { listDoses } from "@/lib/doses";
import { sendNudge } from "@/lib/nudges";
import { listPatients, type PatientRecord } from "@/lib/patients";
import {
  acceptCaregiverInvite,
  leaveCaregiverLink,
  listMonitoredPatients,
  listPendingInvitesForMe,
  listSentInvites,
  sendCaregiverInvite,
  type MonitoredPatient,
  type PendingInvite,
  type SentInvite,
} from "@/lib/caregivers";

const NUDGES = [
  "Đến giờ uống thuốc rồi nha 💊",
  "Đừng quên thuốc nhé ❤️",
  "Capy đang ngó bạn đó 👀",
];

const AVATAR_MAU = [
  { bg: "#FFE7D9", fg: "#B4432C" },
  { bg: "#DFF3E9", fg: "#1F6A50" },
  { bg: "#CFE6FF", fg: "#16386E" },
  { bg: "#E4DDFB", fg: "#4B3E86" },
];

async function demSoCanhBao(relative: MonitoredPatient): Promise<number> {
  // "So can chu y" = canh bao dang mo + so lieu dang cho nguoi than duyet
  // (AWAITING_CAREGIVER). Goi rieng listDoses vi MonitoredPatient tu backend
  // chua dem san so nay.
  try {
    const doses = await listDoses(relative.patientId);
    const soCanDuyet = doses.filter((d) => d.status === "AWAITING_CAREGIVER").length;
    return relative.openEscalations.length + soCanDuyet;
  } catch {
    return relative.openEscalations.length;
  }
}

export default function PatientFamilyPage() {
  const { user, accessToken } = useAuth();
  const [relatives, setRelatives] = useState<MonitoredPatient[]>([]);
  const [badgeByPatientId, setBadgeByPatientId] = useState<Record<string, number>>({});
  const [pending, setPending] = useState<PendingInvite[]>([]);
  const [daGui, setDaGui] = useState<SentInvite[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [dangHuy, setDangHuy] = useState<string | null>(null);
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);

  const [dangMoi, setDangMoi] = useState(false);
  const [tuKhoa, setTuKhoa] = useState("");
  const [ketQuaTim, setKetQuaTim] = useState<PatientRecord[]>([]);
  const [nguoiDuocChon, setNguoiDuocChon] = useState<PatientRecord | null>(null);
  const [quanHe, setQuanHe] = useState("");
  const [dangGuiMoi, setDangGuiMoi] = useState(false);

  const [nudgeCho, setNudgeCho] = useState<MonitoredPatient | null>(null);
  const [nudgeChon, setNudgeChon] = useState(0);
  const [dangGuiNhac, setDangGuiNhac] = useState(false);

  const taiLai = async () => {
    if (!user?.id) return;
    setDangTai(true);
    try {
      const [ds, moi, gui] = await Promise.all([
        listMonitoredPatients(user.id),
        accessToken ? listPendingInvitesForMe(accessToken) : Promise.resolve([]),
        accessToken ? listSentInvites(accessToken) : Promise.resolve([]),
      ]);
      setRelatives(ds);
      setPending(moi);
      setDaGui(gui);
      const badges = await Promise.all(
        ds.map(async (r) => [r.patientId, await demSoCanhBao(r)] as const),
      );
      setBadgeByPatientId(Object.fromEntries(badges));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách người thân");
    } finally {
      setDangTai(false);
    }
  };

  useEffect(() => {
    taiLai();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!dangMoi || !tuKhoa.trim()) {
      setKetQuaTim([]);
      return;
    }
    const timer = setTimeout(() => {
      listPatients(tuKhoa, accessToken)
        .then((ds) => setKetQuaTim(ds.filter((p) => p.id !== user?.patient_id)))
        .catch(() => setKetQuaTim([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [tuKhoa, dangMoi, user?.patient_id, accessToken]);

  const chapNhan = async (invite: PendingInvite) => {
    if (!accessToken) return;
    setDangXuLy(invite.id);
    try {
      await acceptCaregiverInvite(accessToken, invite.id);
      toast.success(`Đã chấp nhận lời mời từ ${invite.inviterName}`);
      await taiLai();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không chấp nhận được lời mời");
    } finally {
      setDangXuLy(null);
    }
  };

  const tuChoi = async (invite: PendingInvite) => {
    if (!accessToken) return;
    setDangXuLy(invite.id);
    try {
      await leaveCaregiverLink(accessToken, invite.id);
      toast("Đã từ chối lời mời");
      await taiLai();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không từ chối được lời mời");
    } finally {
      setDangXuLy(null);
    }
  };

  const guiNhac = async () => {
    if (!accessToken || !nudgeCho) return;
    setDangGuiNhac(true);
    try {
      await sendNudge(accessToken, { patientId: nudgeCho.patientId, message: NUDGES[nudgeChon] });
      toast.success(`Đã gửi lời nhắc tới ${nudgeCho.fullName}`);
      setNudgeCho(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được lời nhắc");
    } finally {
      setDangGuiNhac(false);
    }
  };

  const guiLoiMoi = async () => {
    if (!accessToken || !nguoiDuocChon || !quanHe.trim()) return;
    setDangGuiMoi(true);
    try {
      await sendCaregiverInvite(accessToken, {
        patientId: nguoiDuocChon.id,
        relationship: quanHe.trim(),
      });
      toast.success(`Đã gửi lời mời tới ${nguoiDuocChon.fullName} — chờ họ đồng ý`);
      setDangMoi(false);
      setTuKhoa("");
      setNguoiDuocChon(null);
      setQuanHe("");
      await taiLai();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được lời mời");
    } finally {
      setDangGuiMoi(false);
    }
  };

  const huyLoiMoiDaGui = async (invite: SentInvite) => {
    if (!accessToken) return;
    setDangHuy(invite.id);
    try {
      await leaveCaregiverLink(accessToken, invite.id);
      toast("Đã huỷ lời mời");
      await taiLai();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không huỷ được lời mời");
    } finally {
      setDangHuy(null);
    }
  };

  // The canh bao dau trang: chi hien khi co nguoi than DANG co canh bao that.
  const canChuY = relatives.find((r) => (badgeByPatientId[r.patientId] ?? 0) > 0);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.05] text-[#16386E]">
          Capy Circle
        </h1>
        <p className="m-0 mt-1 text-[14px] leading-[1.45] text-[#5B6A85]">
          Cùng chăm sóc những người bạn thương.
        </p>
      </div>

      {/* Canh bao */}
      {canChuY && (
        <div className="rounded-[26px] bg-[#FFD5C2] p-4">
          <PillChip chip={{ label: "Cần chú ý", icon: "!", bg: "#FFFFFF", fg: "#B4432C" }} />
          <p className="font-display m-0 mt-2.5 text-[16px] font-bold leading-[1.35] text-[#8A3521]">
            {canChuY.fullName} có {badgeByPatientId[canChuY.patientId]} việc cần bạn xem
          </p>
          <p className="m-0 mt-1 text-[12.5px] leading-[1.45] text-[#A0492F]">
            Có liều chờ xác nhận hoặc cảnh báo đang mở. Chưa chắc là bỏ liều.
          </p>
          <div className="mt-3.5 flex gap-2.5">
            <Link
              href={`/patient/family/${canChuY.patientId}`}
              className="font-display flex min-h-[46px] flex-1 items-center justify-center rounded-[16px] bg-white text-[14px] font-bold text-[#8A3521] transition-colors hover:bg-[#FFF6F2]"
            >
              Xem
            </Link>
            <button
              onClick={() => {
                setNudgeCho(canChuY);
                setNudgeChon(0);
              }}
              className="font-display flex min-h-[46px] flex-1 items-center justify-center rounded-[16px] bg-[#16386E] text-[14px] font-bold text-white transition-colors hover:bg-[#0E2749]"
            >
              Nhắc nhẹ
            </button>
          </div>
        </div>
      )}

      {/* Loi moi den voi minh */}
      {pending.length > 0 && (
        <div>
          <div className="mb-2.5">
            <SectionLabel>Lời mời đang chờ bạn</SectionLabel>
          </div>
          <div className="flex flex-col gap-2.5">
            {pending.map((invite) => (
              <div key={invite.id} className="flex items-center gap-3 rounded-[24px] bg-white p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-display m-0 truncate text-[15px] font-bold text-[#16386E]">
                    {invite.inviterName}
                  </p>
                  <p className="m-0 text-[12px] text-[#62708A]">
                    Muốn theo dõi bạn · {invite.relationship}
                  </p>
                </div>
                <button
                  disabled={dangXuLy === invite.id}
                  onClick={() => chapNhan(invite)}
                  className="font-display rounded-full bg-[#16386E] px-3.5 py-2 text-[12px] font-bold text-white disabled:opacity-50"
                >
                  Đồng ý
                </button>
                <button
                  aria-label="Từ chối lời mời"
                  disabled={dangXuLy === invite.id}
                  onClick={() => tuChoi(invite)}
                  className="rounded-full bg-[#F6E9E7] px-3 py-2 text-[12px] font-semibold text-[#B4432C] disabled:opacity-50"
                >
                  Từ chối
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Loi moi minh da gui, con dang cho nguoi kia duyet */}
      {daGui.length > 0 && (
        <div>
          <div className="mb-2.5">
            <SectionLabel>Lời mời bạn đã gửi</SectionLabel>
          </div>
          <div className="flex flex-col gap-2.5">
            {daGui.map((invite) => (
              <div key={invite.id} className="flex items-center gap-3 rounded-[24px] bg-white p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-display m-0 truncate text-[15px] font-bold text-[#16386E]">
                    {invite.patientName}
                  </p>
                  <p className="m-0 text-[12px] text-[#62708A]">{invite.relationship}</p>
                </div>
                <PillChip chip={{ label: "Đang đợi duyệt", icon: "‖", bg: "#FDEBC9", fg: "#8A6516" }} />
                <button
                  aria-label="Huỷ lời mời"
                  disabled={dangHuy === invite.id}
                  onClick={() => huyLoiMoiDaGui(invite)}
                  className="rounded-full bg-[#F6E9E7] px-3 py-2 text-[12px] font-semibold text-[#B4432C] disabled:opacity-50"
                >
                  Huỷ
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Nguoi than dang theo doi */}
      <div>
        <div className="mb-2.5">
          <SectionLabel>Bạn đang theo dõi</SectionLabel>
        </div>

        {dangTai && (
          <div className="flex items-center justify-center gap-2 rounded-[24px] bg-white p-6 text-[13px] text-[#5B6A85]">
            <Loader2 className="h-4 w-4 animate-spin" /> Đang tải…
          </div>
        )}

        {!dangTai && relatives.length === 0 && (
          <div className="rounded-[24px] bg-white p-6 text-center text-[13px] text-[#5B6A85]">
            Bạn chưa theo dõi người thân nào.
          </div>
        )}

        <div className="flex flex-col gap-2.5">
          {relatives.map((r, i) => {
            const badge = badgeByPatientId[r.patientId] ?? 0;
            const xong = r.doseTotalToday > 0 && r.doseTakenToday >= r.doseTotalToday;
            const mau = AVATAR_MAU[i % AVATAR_MAU.length];
            const chip: ChipStyle = badge
              ? { label: `${badge} việc cần xem`, icon: "!", bg: "#FDEBC9", fg: "#8A6516" }
              : xong
                ? CHIP.taken
                : CHIP.upcoming;
            const pct =
              r.doseTotalToday > 0
                ? (r.doseTakenToday / r.doseTotalToday) * 100
                : (r.adherencePct ?? 0);
            return (
              <Link
                key={r.linkId}
                href={`/patient/family/${r.patientId}`}
                className="block rounded-[24px] bg-white p-4"
              >
                <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3">
                  <span
                    className="font-display grid h-[46px] w-[46px] place-items-center rounded-[16px] text-[17px] font-bold"
                    style={{ background: mau.bg, color: mau.fg }}
                  >
                    {r.fullName.charAt(0).toUpperCase()}
                  </span>
                  <span className="block min-w-0">
                    <span className="font-display block truncate text-[16px] font-bold text-[#16386E]">
                      {r.fullName}
                    </span>
                    <span className="block text-[12.5px] text-[#5B6A85]">
                      {r.doseTotalToday > 0
                        ? `${r.doseTakenToday} / ${r.doseTotalToday} liều hôm nay`
                        : r.relationship}
                    </span>
                  </span>
                  <PillChip chip={chip} />
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#EDF0F6]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct}%`, background: badge ? "#E39A16" : "#2E9E6B" }}
                  />
                </div>
                <p className="font-mono m-0 mt-2 text-[11px] text-[#62708A]">
                  chia sẻ: mức tuân thủ + cảnh báo bỏ liều · không xem nhật ký
                </p>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Moi them nguoi than */}
      {!dangMoi ? (
        <div className="flex flex-col gap-2">
          <CapyPrimaryButton onClick={() => setDangMoi(true)}>+ Mời người thân</CapyPrimaryButton>
          <p className="m-0 text-center text-[11.5px] leading-[1.5] text-[#62708A]">
            Họ phải đồng ý trước khi bạn xem được thông tin dùng thuốc.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3 rounded-[24px] bg-white p-4">
          <div className="flex items-center justify-between">
            <p className="font-display m-0 font-bold text-[#16386E]">Gửi lời mời theo dõi</p>
            <button onClick={() => setDangMoi(false)} aria-label="Đóng">
              <X className="h-4 w-4 text-[#62708A]" />
            </button>
          </div>

          <div className="space-y-2">
            <Label htmlFor="tim-nguoi-than">Tìm bệnh nhân theo tên</Label>
            <Input
              id="tim-nguoi-than"
              value={nguoiDuocChon ? nguoiDuocChon.fullName : tuKhoa}
              onChange={(e) => {
                setNguoiDuocChon(null);
                setTuKhoa(e.target.value);
              }}
              placeholder="Gõ tên bệnh nhân..."
              className="rounded-2xl border-[#E3E8F1]"
            />
            {ketQuaTim.length > 0 && !nguoiDuocChon && (
              <div className="max-h-48 overflow-auto rounded-2xl border border-[#E3E8F1]">
                {ketQuaTim.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      setNguoiDuocChon(p);
                      setTuKhoa("");
                      setKetQuaTim([]);
                    }}
                    className="block w-full px-3 py-2 text-left text-[13px] hover:bg-[#F4F7FC]"
                  >
                    {p.fullName}
                    <span className="font-mono ml-1.5 text-[11px] text-[#62708A]">({p.id})</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {nguoiDuocChon && (
            <div className="space-y-2">
              <Label htmlFor="quan-he">Quan hệ với bạn</Label>
              <Input
                id="quan-he"
                value={quanHe}
                onChange={(e) => setQuanHe(e.target.value)}
                placeholder="vd. Con gái, Vợ, Bố..."
                className="rounded-2xl border-[#E3E8F1]"
              />
            </div>
          )}

          <CapyPrimaryButton
            disabled={!nguoiDuocChon || !quanHe.trim() || dangGuiMoi}
            onClick={guiLoiMoi}
            className="min-h-[50px] text-[15px]"
          >
            {dangGuiMoi ? <Loader2 className="h-4 w-4 animate-spin" /> : "Gửi lời mời"}
          </CapyPrimaryButton>
        </div>
      )}

      {/* Sheet nhac nhe */}
      {nudgeCho && (
        <CapySheet onClose={() => setNudgeCho(null)}>
          <p className="font-display m-0 text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Nhắc nhẹ {nudgeCho.fullName}
          </p>
          <p className="m-0 mt-1.5 text-[13.5px] leading-[1.5] text-[#5B6A85]">
            Chọn một lời nhắc.
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            {NUDGES.map((n, i) => (
              <button
                key={n}
                onClick={() => setNudgeChon(i)}
                className="flex min-h-[54px] items-center rounded-[18px] px-[18px] text-left text-[14.5px] font-medium text-[#1B2A44] transition-colors"
                style={{
                  background: nudgeChon === i ? "#CFE6FF" : "#F4F7FC",
                  border: `1.5px solid ${nudgeChon === i ? "#16386E" : "transparent"}`,
                }}
              >
                {n}
              </button>
            ))}
            <CapySecondaryButton
              className="min-h-[56px] text-[15px]"
              disabled={dangGuiNhac}
              onClick={guiNhac}
            >
              {dangGuiNhac ? <Loader2 className="h-4 w-4 animate-spin" /> : "Gửi lời nhắc"}
            </CapySecondaryButton>
          </div>
        </CapySheet>
      )}
    </div>
  );
}
