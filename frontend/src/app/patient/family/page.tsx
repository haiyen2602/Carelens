"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, Loader2, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { listDoses } from "@/lib/doses";
import { listPatients, type PatientRecord } from "@/lib/patients";
import {
  acceptCaregiverInvite,
  leaveCaregiverLink,
  listMonitoredPatients,
  listPendingInvitesForMe,
  sendCaregiverInvite,
  type MonitoredPatient,
  type PendingInvite,
} from "@/lib/caregivers";

async function demSoCanhBao(relative: MonitoredPatient): Promise<number> {
  // "So can chu y" = canh bao dang mo + so lieu dang cho nguoi than duyet
  // (AWAITING_CAREGIVER, sau khi chup lai 2 lan van lech - ADR-0011). Goi
  // rieng listDoses vi MonitoredPatient tu backend chua dem san so nay.
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
  const [dangTai, setDangTai] = useState(true);
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);

  const [dangMoi, setDangMoi] = useState(false);
  const [tuKhoa, setTuKhoa] = useState("");
  const [ketQuaTim, setKetQuaTim] = useState<PatientRecord[]>([]);
  const [nguoiDuocChon, setNguoiDuocChon] = useState<PatientRecord | null>(null);
  const [quanHe, setQuanHe] = useState("");
  const [dangGuiMoi, setDangGuiMoi] = useState(false);

  const taiLai = async () => {
    if (!user?.id) return;
    setDangTai(true);
    try {
      const [ds, moi] = await Promise.all([
        listMonitoredPatients(user.id),
        accessToken ? listPendingInvitesForMe(accessToken) : Promise.resolve([]),
      ]);
      setRelatives(ds);
      setPending(moi);
      const badges = await Promise.all(ds.map(async (r) => [r.patientId, await demSoCanhBao(r)] as const));
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
      // SUA 2026-08-14: thieu accessToken khien request luon 401 (chua xac
      // thuc), khac han bug 403 truoc do (thieu role) - benh nhan van khong
      // tim duoc ai du backend da mo quyen, loi bi .catch() nuot am tham.
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

  const guiLoiMoi = async () => {
    if (!accessToken || !nguoiDuocChon || !quanHe.trim()) return;
    setDangGuiMoi(true);
    try {
      await sendCaregiverInvite(accessToken, { patientId: nguoiDuocChon.id, relationship: quanHe.trim() });
      toast.success(`Đã gửi lời mời tới ${nguoiDuocChon.fullName} — chờ họ đồng ý`);
      setDangMoi(false);
      setTuKhoa("");
      setNguoiDuocChon(null);
      setQuanHe("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được lời mời");
    } finally {
      setDangGuiMoi(false);
    }
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">Người thân</h1>
        <p className="text-sm text-muted-foreground">
          Theo dõi mức tuân thủ và cảnh báo của người thân bạn quan tâm.
        </p>
      </header>

      {pending.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-bold uppercase text-muted-foreground">
            Lời mời đang chờ bạn
          </h2>
          <div className="space-y-2">
            {pending.map((invite) => (
              <div key={invite.id} className="surface-card flex items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{invite.inviterName}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    Muốn theo dõi bạn · {invite.relationship}
                  </p>
                </div>
                <Button
                  size="sm"
                  disabled={dangXuLy === invite.id}
                  onClick={() => chapNhan(invite)}
                >
                  <Check className="mr-1 h-3.5 w-3.5" /> Đồng ý
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive"
                  disabled={dangXuLy === invite.id}
                  onClick={() => tuChoi(invite)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-bold uppercase text-muted-foreground">
          Người thân bạn theo dõi
        </h2>

        {dangTai && (
          <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Đang tải…
          </div>
        )}

        {!dangTai && relatives.length === 0 && (
          <p className="surface-card p-6 text-center text-sm text-muted-foreground">
            Bạn chưa theo dõi người thân nào.
          </p>
        )}

        <div className="space-y-3">
          {relatives.map((r) => {
            const badge = badgeByPatientId[r.patientId] ?? 0;
            return (
              <Link key={r.linkId} href={`/patient/family/${r.patientId}`} className="surface-card block p-4">
                <div className="flex items-center gap-3">
                  <span className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                    {r.fullName.charAt(0)}
                    {badge > 0 && (
                      <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                        {badge}
                      </span>
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{r.fullName}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {r.relationship}
                      {r.note ? ` · ${r.note}` : ""}
                    </p>
                  </div>
                  {r.adherencePct !== null && (
                    <span className="shrink-0 text-lg font-extrabold text-primary">
                      {Math.round(r.adherencePct)}%
                    </span>
                  )}
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>

                {r.adherencePct !== null && (
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${r.adherencePct}%` }}
                    />
                  </div>
                )}
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Đã uống {r.doseTakenToday}/{r.doseTotalToday} liều hôm nay
                  {r.openEscalations.length > 0 && ` · ${r.openEscalations.length} cảnh báo`}
                </p>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="surface-card p-4">
        {!dangMoi ? (
          <>
            <p className="font-semibold">Theo dõi thêm người thân</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Gửi lời mời — họ cần đồng ý thì bạn mới xem được tình trạng uống thuốc của họ.
            </p>
            <Button variant="outline" className="mt-3 w-full" onClick={() => setDangMoi(true)}>
              <UserPlus className="mr-1 h-4 w-4" /> Gửi lời mời theo dõi
            </Button>
          </>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-semibold">Gửi lời mời theo dõi</p>
              <button onClick={() => setDangMoi(false)} aria-label="Đóng">
                <X className="h-4 w-4 text-muted-foreground" />
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
              />
              {ketQuaTim.length > 0 && !nguoiDuocChon && (
                <div className="max-h-48 overflow-auto rounded-lg border border-border">
                  {ketQuaTim.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        setNguoiDuocChon(p);
                        setTuKhoa("");
                        setKetQuaTim([]);
                      }}
                      className="block w-full px-3 py-2 text-left text-sm hover:bg-muted"
                    >
                      {p.fullName}
                      <span className="ml-1.5 text-xs text-muted-foreground">({p.id})</span>
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
                />
              </div>
            )}

            <Button
              className="w-full"
              disabled={!nguoiDuocChon || !quanHe.trim() || dangGuiMoi}
              onClick={guiLoiMoi}
            >
              {dangGuiMoi ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <UserPlus className="mr-1 h-4 w-4" />}
              Gửi lời mời
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
