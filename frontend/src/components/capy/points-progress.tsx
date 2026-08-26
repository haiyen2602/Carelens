"use client";

// Thanh diem tich luy toi Rank ke tiep. Dat duoi ten benh nhan trong sheet
// tai khoan, va o dau trang /patient/rewards.
//
// Tu ve thanh bang div thay vi dung components/ui/progress.tsx (Radix): ban
// Radix keo theo mau shadcn mac dinh, khong khop bang mau CapyMedi dang dung
// (#16386E / #EDF0F6) va se phai ghi de gan het class - khong con loi gi.

import type { RewardSummary } from "@/lib/rewards";

export function PointsProgress({ summary }: { summary: RewardSummary }) {
  const { lifetimePoints, nextRankAt, nextRankLabel, pointsToNextRank } = summary;

  // Da o Rank cao nhat: khong con moc nao de "tien toi" nen thay thanh
  // tien do bang mot dong ghi nhan - ve thanh day 100% se ngu y con muc
  // tiep theo.
  if (nextRankAt === null || pointsToNextRank === null) {
    return (
      <p className="m-0 text-[12px] font-semibold text-[#62708A]">
        {lifetimePoints.toLocaleString("vi-VN")} điểm tích luỹ · Rank cao nhất 🎉
      </p>
    );
  }

  const phanTram = Math.min(100, Math.round((lifetimePoints / nextRankAt) * 100));

  return (
    <div className="w-full">
      <div className="h-[6px] w-full overflow-hidden rounded-full bg-[#EDF0F6]">
        <div
          className="h-full rounded-full bg-[#16386E] transition-[width] duration-500"
          style={{ width: `${phanTram}%` }}
        />
      </div>
      <p className="m-0 mt-1 text-[11px] font-semibold text-[#62708A]">
        Còn {pointsToNextRank.toLocaleString("vi-VN")} điểm để lên Rank {nextRankLabel}
      </p>
    </div>
  );
}
