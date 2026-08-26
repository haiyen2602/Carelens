"use client";

// Huy hieu Rank tron - dat CANH avatar chu cai dau (khong thay the no), o
// nut tai khoan goc phai va trong sheet tai khoan.
//
// Anh nam trong public/rank (copy tu reward/photo_rank) - `unoptimized` vi
// day la anh nho, co dinh, khong can pipeline toi uu cua next/image.

import Image from "next/image";
import { RANK_IMAGES, type RankName } from "@/lib/rewards";

export function RankBadge({
  rank,
  label,
  size = 18,
  className = "",
}: {
  rank: RankName;
  label: string;
  size?: number;
  className?: string;
}) {
  return (
    <span
      // Vien trang tach huy hieu khoi nen phia sau khi no nam de len avatar.
      className={`inline-grid shrink-0 place-items-center overflow-hidden rounded-full bg-white ring-2 ring-white ${className}`}
      style={{ width: size, height: size }}
      title={`Rank ${label}`}
    >
      <Image
        src={RANK_IMAGES[rank]}
        alt={`Rank ${label}`}
        width={size}
        height={size}
        unoptimized
        className="h-full w-full object-cover"
      />
    </span>
  );
}
