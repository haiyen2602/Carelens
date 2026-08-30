"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Bell,
  Camera,
  ChevronRight,
  Globe,
  Info,
  KeyRound,
  Send,
  ShieldCheck,
  UserRound,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { EditPersonalInfoDialog } from "@/components/edit-personal-info-dialog";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";
import {
  getNotificationPrefs,
  type NotificationPrefs,
  setNotificationPrefs,
} from "@/lib/notification-prefs";
import { getNotificationPermission, requestNotificationPermission } from "@/lib/notifications";
import { updateMyPatientProfile } from "@/lib/patients";
import { subscribeToPush } from "@/lib/push";
import { batDauGhepTelegram, datTuyChonTelegram, goKetNoiTelegram } from "@/lib/telegram";
import { useProto } from "@/lib/proto-store";
import { loadVoiceOutputEnabled, saveVoiceOutputEnabled } from "@/lib/voice-settings";

export function AccountSettings() {
  const { phone, role } = useProto();
  const { user, accessToken, updateSession } = useAuth();
  const [dangLuuChupAnh, setDangLuuChupAnh] = useState(false);
  // Doc localStorage o effect (khong phai o useState initializer) - trang
  // nay render ca server (SSR) truoc khi hydrate, localStorage chi co tren
  // trinh duyet nen phai doi den sau mount de tranh lech hydration.
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(false);
  useEffect(() => {
    setVoiceOutputEnabled(loadVoiceOutputEnabled());
  }, []);
  const doiVoiceOutput = (bat: boolean) => {
    setVoiceOutputEnabled(bat);
    saveVoiceOutputEnabled(bat);
  };

  // GHI CHU 2026-08-28: ba useState `reminders`/`emergencyAlerts`/
  // `weeklySummary` da bi XOA khi khoi "Thong bao" duoc lam that (luu vao
  // patient_notification_pref + telegram_link). Chu thich cu o day tung noi
  // switch chup anh "khac 3 switch chi doi UI" - gio khong con 3 switch gia
  // nao nua, moi cong tac trong man hinh nay deu ghi xuong he thong.
  //
  // Switch nay goi PATCH /patients/me, vi no doi hanh vi xac nhan lieu thuoc
  // o tab "Hom nay" (xem app/patient/page.tsx::chupAnhBat). updateSession()
  // de "Hom nay" thay gia tri MOI ngay, khong phai doi tai lai trang.
  const doiChupAnh = async (bat: boolean) => {
    if (!user || !accessToken) return;
    setDangLuuChupAnh(true);
    try {
      await updateMyPatientProfile(accessToken, { photo_capture_enabled: bat });
      updateSession(accessToken, { ...user, photo_capture_enabled: bat });
      toast.success(bat ? "Đã bật chụp ảnh xác nhận" : "Đã tắt chụp ảnh xác nhận");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không lưu được thay đổi");
    } finally {
      setDangLuuChupAnh(false);
    }
  };

  // THEM 2026-08-17: tai khoan tao qua Login with Google chua co mat khau -
  // nhan phai la "Đặt mật khẩu", biet TRUOC khi mo dialog (neu vao trong roi
  // moi biet thi nguoi dung da nhap xong 3 o mat khau).
  //
  // GHI CHU 2026-08-17: nhan nay phu thuoc DU LIEU cua tung tai khoan
  // (`auth_provider`), khong phai moi truong - cung 1 email co the thay
  // "Đặt mật khẩu" o may nay va "Đổi mật khẩu" o may khac neu 2 DB co 2 trang
  // thai khac nhau (tai khoan sinh ra tu Google vs tai khoan cu moi lien ket
  // Google sau). Copy ben duoi noi ro dieu do de khong bi hieu la loi hien thi.
  const chuaCoMatKhau = user?.auth_provider === "google";

  // MOT nguon su that cho ca khoi Thong bao (ca tuy chon Telegram) - truoc
  // day 3 cong tac dau la useState khong luu gi, dat canh 1 cong tac that se
  // khong ai phan biet duoc cai nao thuc su co tac dung.
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [dangGhep, setDangGhep] = useState(false);
  // Quyen Notification cua TRINH DUYET - khac han web_push_enabled o server:
  // benh nhan co the bat tuy chon nhung tu choi quyen (hoac nguoc lai), va
  // hai thu do phai hien khac nhau tren man hinh.
  const [quyenTrinhDuyet, setQuyenTrinhDuyet] = useState(getNotificationPermission());

  const taiTuyChon = useCallback(async () => {
    if (!accessToken) return;
    setPrefs(await getNotificationPrefs(accessToken));
    setQuyenTrinhDuyet(getNotificationPermission());
  }, [accessToken]);

  useEffect(() => {
    void taiTuyChon();
  }, [taiTuyChon]);

  // Tai lai khi nguoi dung quay ve tab: viec ghep Telegram hoan tat o BEN
  // NGOAI app, nen khong co su kien nao trong trang bao ta biet no da xong.
  // Khoanh khac ho chuyen ve day la tin hieu duy nhat co that.
  useEffect(() => {
    const onFocus = () => void taiTuyChon();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [taiTuyChon]);

  /** Cap nhat lac quan roi moi goi API: cong tac phai nhay NGAY duoi ngon
   * tay, doi mot vong mang moi nhuc nhich se bi tuong la bam hong. Loi thi
   * tra lai trang thai cu. */
  const gat = async (
    thayDoi: Partial<NotificationPrefs>,
    luu: () => Promise<boolean>,
    loiBao: string,
  ) => {
    if (!prefs) return;
    const truoc = prefs;
    setPrefs({ ...prefs, ...thayDoi });
    if (!(await luu())) {
      setPrefs(truoc);
      toast.error(loiBao);
    }
  };

  const doiNhacUongThuoc = (bat: boolean) =>
    gat(
      { doseReminderEnabled: bat },
      async () => {
        const moi = accessToken
          ? await setNotificationPrefs(accessToken, { doseReminderEnabled: bat })
          : null;
        if (moi) setPrefs(moi);
        return moi !== null;
      },
      "Chưa lưu được, bạn thử lại giúp mình nhé",
    );

  const doiWebPush = async (bat: boolean) => {
    if (!accessToken || !prefs) return;

    // Bat len ma trinh duyet chua cho quyen thi phai xin quyen TRUOC, khong
    // thi tuy chon o server bat nhung may van im lang - benh nhan se tuong
    // he thong hong chu khong nghi la thieu quyen.
    if (bat && quyenTrinhDuyet !== "granted") {
      if (quyenTrinhDuyet === "denied") {
        toast("Bạn đã chặn thông báo — mở cài đặt trình duyệt để bật lại");
        return;
      }
      const ketQua = await requestNotificationPermission();
      setQuyenTrinhDuyet(ketQua);
      if (ketQua !== "granted") return;
      await subscribeToPush(accessToken);
    }

    await gat(
      { webPushEnabled: bat },
      async () => {
        const moi = await setNotificationPrefs(accessToken, { webPushEnabled: bat });
        if (moi) setPrefs(moi);
        return moi !== null;
      },
      "Chưa lưu được, bạn thử lại giúp mình nhé",
    );
  };

  const doiTelegram = (bat: boolean) =>
    gat(
      { telegramEnabled: bat },
      () => datTuyChonTelegram(accessToken ?? "", bat),
      "Chưa lưu được, bạn thử lại giúp mình nhé",
    );

  const ketNoiTelegram = async () => {
    if (!accessToken) return;
    setDangGhep(true);
    const ok = await batDauGhepTelegram(accessToken);
    setDangGhep(false);
    if (ok) {
      toast("Bấm nút Start trong Telegram để hoàn tất, rồi quay lại đây");
    } else {
      toast.error("Chưa mở được Telegram, bạn thử lại giúp mình nhé");
    }
  };

  const huyKetNoiTelegram = async () => {
    if (!accessToken) return;
    if (await goKetNoiTelegram(accessToken)) {
      toast("Đã ngắt kết nối Telegram");
      await taiTuyChon();
    } else {
      toast.error("Chưa ngắt được, bạn thử lại giúp mình nhé");
    }
  };

  const soon = () => toast("Tính năng đang được phát triển");

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Cài đặt</h1>
        <p className="text-sm text-muted-foreground">Quản lý tài khoản và tuỳ chọn của bạn.</p>
      </header>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Tài khoản</h2>
        {/* SUA 2026-08-23: hang nay tung chi hien toast "dang phat trien".
            Chi wire EditPersonalInfoDialog cho role=patient - backend
            (GET/PATCH /api/v1/patients/me) chi phuc vu tai khoan co
            patient_id gan voi minh (thuc te chi role=patient), family/doctor
            goi se 403 nen van giu nut toast cu cho ho. */}
        {role === "patient" ? (
          <EditPersonalInfoDialog
            trigger={
              <button className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
                  <UserRound className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">
                    {phone || "Chưa có số điện thoại"}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    Bệnh nhân · Bấm để đổi thông tin cá nhân
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            }
          />
        ) : (
          <button
            onClick={soon}
            className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
              <UserRound className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-semibold">
                {phone || "Chưa có số điện thoại"}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {role === "family" ? "Người thân" : "Bác sĩ"} · Bấm để đổi thông tin cá nhân
              </span>
            </span>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        )}
      </section>

      <section className="surface-card space-y-4 p-5">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
          <Bell className="h-4 w-4" /> Thông báo
        </h2>

        {/* TANG 1 - co muon duoc nhac khong. Tat cai nay thi khong kenh nao
            gui, du tung kenh ben duoi van bat.

            An voi NGUOI THAN: ho khong co lich uong thuoc, chi nhan canh bao
            khi benh nhan ho theo doi co van de. Hien mot cong tac ho khong
            the tat duoc gi chi lam ho hoang mang. */}
        {prefs?.isPatient ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">Nhắc uống thuốc</p>
              <p className="text-xs text-muted-foreground">
                Nhắc theo đúng khung giờ trong phác đồ
              </p>
            </div>
            <Switch
              aria-label="Nhắc uống thuốc"
              checked={prefs.doseReminderEnabled}
              onCheckedChange={doiNhacUongThuoc}
            />
          </div>
        ) : null}

        {/* TANG 2 - nhac qua duong nao. LONG VAO BEN TRONG tang 1 (thut le +
            vach doc) chu khong xep ngang hang: quan he "tat tang 1 thi ca hai
            kenh im" phai nhin ra duoc ngay, khong can doc chu giai thich. */}
        {/* Hien khoi kenh khi: la benh nhan VA dang bat nhac uong thuoc, HOAC
            la nguoi than (luon can kenh de nhan canh bao - canh bao khong tat
            duoc nen kenh cung phai luon co). Mot nguoi co the thoa ca hai. */}
        {prefs && ((prefs.isPatient && prefs.doseReminderEnabled) || prefs.isCaregiver) ? (
          <div
            className={
              prefs.isPatient && prefs.doseReminderEnabled
                ? "ml-1 space-y-4 border-l-2 border-border pl-4"
                : "space-y-4"
            }
          >
            {/* Chi thut le + hien nhan "Kenh nhan" khi no THAT SU long trong
                muc nhac uong thuoc. Voi nguoi than thuan tuy thi khoi nay
                dung doc lap, thut le se nhin nhu con cua mot muc bi thieu. */}
            {prefs.isPatient && prefs.doseReminderEnabled ? (
              <p className="text-xs font-semibold uppercase text-muted-foreground">Kênh nhận</p>
            ) : null}

            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">Thông báo trên máy</p>
                <p className="text-xs text-muted-foreground">
                  {quyenTrinhDuyet === "denied"
                    ? "Bạn đã chặn thông báo trong trình duyệt"
                    : quyenTrinhDuyet === "unsupported"
                      ? "Trình duyệt này không hỗ trợ"
                      : "Hiện ngay trên máy, kể cả khi đã đóng app"}
                </p>
              </div>
              <Switch
                aria-label="Thông báo trên máy"
                checked={prefs.webPushEnabled && quyenTrinhDuyet === "granted"}
                disabled={quyenTrinhDuyet === "unsupported" || quyenTrinhDuyet === "denied"}
                onCheckedChange={doiWebPush}
              />
            </div>

            {/* An HAN khi server chua cau hinh bot: mot nut bam duoc nhung
                luon bao loi con kho hieu hon la khong co nut. */}
            {prefs.telegramConfigured ? (
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-medium">
                    <Send className="h-4 w-4" /> Telegram
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {prefs.telegramLinked
                      ? `Đã kết nối${prefs.telegramUsername ? ` với @${prefs.telegramUsername}` : ""}`
                      : prefs.isPatient && prefs.isCaregiver
                        ? "Nhận nhắc uống thuốc và cảnh báo về người bạn đang theo dõi"
                        : prefs.isPatient
                          ? "Nhận nhắc qua Telegram, kể cả khi đã đóng app"
                          : "Nhận cảnh báo về người thân bạn đang theo dõi"}
                  </p>
                  {/* Ngat ket noi la hanh dong HIEM (doi tai khoan Telegram,
                      cho nguoi khac muon may) - de nho o duoi, khong canh
                      tranh voi cong tac von la thu dung hang ngay. */}
                  {prefs.telegramLinked ? (
                    <button
                      type="button"
                      onClick={huyKetNoiTelegram}
                      className="mt-1 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                    >
                      Ngắt kết nối
                    </button>
                  ) : null}
                </div>
                {prefs.telegramLinked ? (
                  <Switch
                    aria-label="Nhắc qua Telegram"
                    checked={prefs.telegramEnabled}
                    onCheckedChange={doiTelegram}
                  />
                ) : (
                  <button
                    type="button"
                    onClick={ketNoiTelegram}
                    disabled={dangGhep}
                    className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
                  >
                    {dangGhep ? "Đang mở…" : "Kết nối"}
                  </button>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Canh bao khan cap CO Y khong phai cong tac. Day la luoi an toan
            cho nguoi than, khong phai tien nghi cua benh nhan: nguoi muon tat
            no nhat - benh nhan khong muon con chau biet minh quen thuoc - lai
            dung la nguoi no sinh ra de bao ve. Khop voi backend, cho
            tao_canh_bao_cho_nguoi_than() nam NGOAI moi kiem tra tuy chon
            (backend/services/dose_push_reminder.py). */}
        {prefs?.isPatient ? (
          <div className="flex items-start gap-3 border-t border-border pt-4">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="font-medium">Cảnh báo khẩn cấp — luôn bật</p>
              <p className="text-xs text-muted-foreground">
                Khi phát hiện dấu hiệu nguy hiểm hoặc bạn bỏ liều nhiều lần, người thân sẽ được báo
                ngay. Mục này không tắt được để đảm bảo an toàn cho bạn.
              </p>
            </div>
          </div>
        ) : null}
      </section>

      {role === "patient" && (
        <section className="surface-card space-y-4 p-5">
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
            <Camera className="h-4 w-4" /> Chụp ảnh xác nhận
          </h2>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">Yêu cầu chụp ảnh khi uống thuốc</p>
              <p className="text-xs text-muted-foreground">
                Khi tắt, bạn chỉ cần chọn &quot;Tôi đã uống&quot; hoặc &quot;Chưa uống&quot; — người
                thân sẽ xác nhận lại giúp bạn trước khi tính là đã uống.
              </p>
            </div>
            <Switch
              aria-label="Yêu cầu chụp ảnh khi uống thuốc"
              checked={user?.photo_capture_enabled ?? true}
              disabled={dangLuuChupAnh}
              onCheckedChange={doiChupAnh}
            />
          </div>
        </section>
      )}

      {role === "patient" && (
        <section className="surface-card space-y-4 p-5">
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
            <Volume2 className="h-4 w-4" /> Trợ lý giọng nói
          </h2>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">Trợ lý đọc to câu trả lời</p>
              <p className="text-xs text-muted-foreground">
                Khi bật, Capy sẽ đọc to câu trả lời sau mỗi lần bạn ghi âm hoặc nhắn tin.
              </p>
            </div>
            <Switch
              aria-label="Trợ lý đọc to câu trả lời"
              checked={voiceOutputEnabled}
              onCheckedChange={doiVoiceOutput}
            />
          </div>
        </section>
      )}

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Bảo mật</h2>
        <ChangePasswordDialog
          trigger={
            <button className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left">
              <KeyRound className="h-5 w-5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">
                  {chuaCoMatKhau ? "Đặt mật khẩu" : "Đổi mật khẩu"}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {chuaCoMatKhau
                    ? "Tài khoản tạo qua Google chưa có mật khẩu — đặt mật khẩu để đăng nhập được cả hai cách"
                    : "Tài khoản này đã có mật khẩu riêng — đổi sang mật khẩu mới"}
                </span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          }
        />
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Ngôn ngữ</h2>
        <button
          onClick={soon}
          className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left"
        >
          <Globe className="h-5 w-5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 font-medium">Tiếng Việt</span>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </section>

      <section className="surface-card flex items-center gap-3 p-5 text-sm text-muted-foreground">
        <Info className="h-4 w-4 shrink-0" />
        CapyMedi · Prototype bấm được · v0.1
      </section>
    </div>
  );
}
