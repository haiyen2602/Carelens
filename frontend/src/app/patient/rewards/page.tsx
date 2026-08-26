"use client";

// Trang "Điểm thưởng" - Rank hien tai, cua hang doi qua theo Rank, va lich
// su tich diem. Trang MOI hoan toan, khong dong vao 5 tab co san.
//
// Moi dieu kien mo khoa/du diem/da doi deu do BACKEND tinh san va tra ve
// (unlocked/affordable/alreadyRedeemed, xem backend/services/reward_ledger.py
// ::list_catalog_for_patient) - trang nay chi ve theo co, khong tu suy lai
// tu rank + so diem. Neu khong, luat mo khoa se ton tai o 2 noi va som muon
// cung lech nhau.

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CapyPrimaryButton,
  CapySecondaryButton,
  CapySheet,
  SectionLabel,
} from "@/components/capy/capy-ui";
import { PointsProgress } from "@/components/capy/points-progress";
import { RankBadge } from "@/components/capy/rank-badge";
import { useAuth } from "@/lib/auth";
import {
  getRewardSummary,
  listRewardCatalog,
  listRewardHistory,
  redeemReward,
  type RankName,
  type RewardHistoryEntry,
  type RewardItem,
  type RewardSummary,
} from "@/lib/rewards";

// Thu tu hien thi cac khoi qua - tu Rank thap len cao, giong bang trong
// reward/reward.md phan 4.
const THU_TU_RANK: RankName[] = ["BRONZE", "SILVER", "GOLD", "DIAMOND"];

function dinhDang(diem: number): string {
  return diem.toLocaleString("vi-VN");
}

function ngayHienThi(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

export default function RewardsPage() {
  const { accessToken, user } = useAuth();
  const [summary, setSummary] = useState<RewardSummary | null>(null);
  const [catalog, setCatalog] = useState<RewardItem[]>([]);
  const [history, setHistory] = useState<RewardHistoryEntry[]>([]);
  const [dangTai, setDangTai] = useState(true);
  // Mon dang cho xac nhan doi - sheet xac nhan mo khi khac null.
  const [dangXacNhan, setDangXacNhan] = useState<RewardItem | null>(null);
  const [dangGui, setDangGui] = useState(false);
  // Thong bao "da doi thanh cong" - giu lai ten qua de hien trong sheet.
  const [daDoi, setDaDoi] = useState<{ tenQua: string; loiNhan: string } | null>(null);

  const taiLai = useCallback(async () => {
    const [s, c, h] = await Promise.all([
      getRewardSummary(accessToken),
      listRewardCatalog(accessToken),
      listRewardHistory(accessToken),
    ]);
    setSummary(s);
    setCatalog(c);
    setHistory(h);
  }, [accessToken]);

  useEffect(() => {
    taiLai()
      .catch(() => toast.error("Không tải được điểm thưởng"))
      .finally(() => setDangTai(false));
  }, [taiLai]);

  const xacNhanDoi = async () => {
    if (!dangXacNhan) return;
    setDangGui(true);
    try {
      const ketQua = await redeemReward(dangXacNhan.id, accessToken);
      setDangXacNhan(null);
      setDaDoi({ tenQua: ketQua.itemName, loiNhan: ketQua.message });
      // Tai lai de so diem va trang thai card cap nhat ngay, khong bat benh
      // nhan tai lai trang.
      await taiLai();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Không đổi được quà");
    } finally {
      setDangGui(false);
    }
  };

  if (dangTai || !summary) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
          Điểm thưởng
        </h1>
        <p className="m-0 text-[13px] text-[#5B6A85]">Đang tải...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
        Điểm thưởng
      </h1>

      {/* Rank hien tai + tien do */}
      <div className="flex items-center gap-3.5 rounded-[28px] bg-[#FFF0D6] p-[18px]">
        <RankBadge rank={summary.rank} label={summary.rankLabel} size={72} />
        <div className="min-w-0 flex-1">
          <p className="font-display m-0 text-[19px] font-bold text-[#6B4E0E]">
            Rank {summary.rankLabel}
          </p>
          <p className="m-0 mt-0.5 text-[13px] font-semibold text-[#7A5A10]">
            {dinhDang(summary.spendablePoints)} điểm có thể đổi quà
          </p>
          <div className="mt-2">
            <PointsProgress summary={summary} />
          </div>
        </div>
      </div>

      {/* Cua hang qua tang, chia theo Rank */}
      {THU_TU_RANK.map((rank) => {
        const mucNay = catalog.filter((m) => m.rankRequired === rank);
        if (mucNay.length === 0) return null;

        return (
          <div key={rank}>
            <div className="mb-2.5">
              <SectionLabel>Rank {mucNay[0].rankRequiredLabel}</SectionLabel>
            </div>
            <div className="flex flex-col gap-2.5">
              {mucNay.map((mon) => (
                <RewardCard
                  key={mon.id}
                  mon={mon}
                  spHienCo={summary.spendablePoints}
                  onDoi={() => setDangXacNhan(mon)}
                />
              ))}
            </div>
          </div>
        );
      })}

      {/* Lich su tich diem */}
      <div>
        <div className="mb-2.5">
          <SectionLabel>Lịch sử điểm</SectionLabel>
        </div>
        <div className="flex flex-col gap-2">
          {history.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between gap-2.5 rounded-[18px] bg-white px-4 py-3"
            >
              <div className="min-w-0">
                <p className="m-0 truncate text-[14px] font-semibold text-[#1B2A44]">{d.label}</p>
                <p className="font-mono m-0 mt-0.5 text-[11px] text-[#62708A]">
                  {ngayHienThi(d.createdAt)}
                </p>
              </div>
              <span
                className="shrink-0 whitespace-nowrap rounded-full px-2.5 py-[5px] text-[12px] font-bold"
                style={
                  d.pointsDelta >= 0
                    ? { background: "#DFF3E9", color: "#1F6A50" }
                    : { background: "#EDF0F6", color: "#5B6A85" }
                }
              >
                {d.pointsDelta >= 0 ? "+" : ""}
                {dinhDang(d.pointsDelta)}
              </span>
            </div>
          ))}
          {history.length === 0 && (
            <div className="rounded-[22px] bg-white p-4 text-[13px] text-[#5B6A85]">
              Chưa có điểm nào. Uống thuốc đúng giờ mỗi ngày để bắt đầu tích điểm nhé!
            </div>
          )}
        </div>
      </div>

      {/* Sheet xac nhan truoc khi tru diem - tranh bam nham mat diem tich
          luy ca nam. */}
      {dangXacNhan && (
        <CapySheet onClose={() => setDangXacNhan(null)}>
          <p className="font-display m-0 text-[20px] font-extrabold leading-[1.2] text-[#16386E]">
            Đổi {dangXacNhan.name}?
          </p>
          <p className="m-0 mt-2 text-[13px] leading-[1.5] text-[#5B6A85]">
            Bạn sẽ dùng <b>{dinhDang(dangXacNhan.spCost)}</b> điểm. Sau khi đổi còn{" "}
            <b>{dinhDang(summary.spendablePoints - dangXacNhan.spCost)}</b> điểm.
          </p>
          <p className="m-0 mt-1.5 text-[12px] leading-[1.5] text-[#62708A]">
            Rank {summary.rankLabel} của bạn được giữ nguyên sau khi đổi quà.
          </p>
          <div className="mt-4 flex gap-2.5">
            <CapySecondaryButton onClick={() => setDangXacNhan(null)} disabled={dangGui}>
              Huỷ
            </CapySecondaryButton>
            <CapyPrimaryButton className="flex-1" onClick={xacNhanDoi} disabled={dangGui}>
              {dangGui ? "Đang đổi..." : "Xác nhận đổi"}
            </CapyPrimaryButton>
          </div>
        </CapySheet>
      )}

      {/* Sheet bao thanh cong - loi nhan lay tu backend (co dinh theo yeu
          cau nghiep vu), khong viet lai o day de 2 noi khong lech nhau. */}
      {daDoi && (
        <CapySheet onClose={() => setDaDoi(null)}>
          <p className="font-display m-0 text-center text-[22px] font-extrabold leading-[1.2] text-[#14563F]">
            Đổi quà thành công! 🎉
          </p>
          <p className="m-0 mt-2 text-center text-[15px] font-semibold text-[#16386E]">
            {daDoi.tenQua}
          </p>
          <p className="m-0 mt-2 text-center text-[13px] leading-[1.5] text-[#5B6A85]">
            {daDoi.loiNhan}
          </p>
          {/* Hien LUON ma so benh nhan o day thay vi chi nhac "mang theo ma so":
              benh nhan khong phai thoat ra sheet tai khoan de tra lai, va co
              the chia man hinh nay thang cho nhan vien quay le tan. */}
          {user?.patient_id && (
            <div className="mt-3 rounded-[16px] bg-[#F4F7FC] px-4 py-3 text-center">
              <p className="m-0 text-[11px] font-bold uppercase tracking-[0.08em] text-[#62708A]">
                Mã số bệnh nhân của bạn
              </p>
              <p className="font-mono m-0 mt-1 text-[15px] font-bold text-[#16386E]">
                {user.patient_id}
              </p>
            </div>
          )}
          <div className="mt-4">
            <CapyPrimaryButton onClick={() => setDaDoi(null)}>Đã hiểu</CapyPrimaryButton>
          </div>
        </CapySheet>
      )}
    </div>
  );
}

function RewardCard({
  mon,
  spHienCo,
  onDoi,
}: {
  mon: RewardItem;
  spHienCo: number;
  onDoi: () => void;
}) {
  const doiDuoc = mon.unlocked && mon.affordable && !mon.alreadyRedeemed;

  return (
    <div className="rounded-[22px] bg-white p-4" style={{ opacity: mon.unlocked ? 1 : 0.6 }}>
      <div className="flex items-baseline justify-between gap-2.5">
        <p className="font-display m-0 text-[16px] font-bold text-[#16386E]">{mon.name}</p>
        {/* "p" (point) chu KHONG phai "d": "10.000 d" de bi doc nham thanh
            10.000 dong - gia tien, trong khi day la diem tich luy. */}
        <span className="font-mono shrink-0 whitespace-nowrap text-[12px] font-bold text-[#8A6516]">
          {dinhDang(mon.spCost)} p
        </span>
      </div>
      <p className="m-0 mt-1 text-[13px] leading-[1.45] text-[#5B6A85]">{mon.description}</p>

      <div className="mt-3">
        {!mon.unlocked ? (
          <p className="m-0 text-[12px] font-semibold text-[#62708A]">
            🔒 Cần đạt Rank {mon.rankRequiredLabel}
          </p>
        ) : mon.alreadyRedeemed ? (
          <p className="m-0 text-[12px] font-semibold text-[#1F6A50]">✓ Bạn đã đổi phần quà này</p>
        ) : !mon.affordable ? (
          <p className="m-0 text-[12px] font-semibold text-[#62708A]">
            Còn thiếu {dinhDang(mon.spCost - spHienCo)} điểm
          </p>
        ) : null}

        {doiDuoc && (
          <button
            onClick={onDoi}
            className="font-display mt-1 flex min-h-[44px] w-full items-center justify-center rounded-[16px] bg-[#16386E] text-[15px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Đổi quà
          </button>
        )}
      </div>
    </div>
  );
}
