// Diem thuong & Rank cua benh nhan, qua /api/rewards/* (route noi bo cua
// chinh FE - cung mau voi lib/doses.ts, lib/patients.ts).
//
// Backend lay patient_id tu JWT nen khong ham nao o day nhan patient_id.

export type RankName = "BRONZE" | "SILVER" | "GOLD" | "DIAMOND";

export type RewardSummary = {
  lifetimePoints: number;
  spendablePoints: number;
  rank: RankName;
  rankLabel: string;
  nextRank: RankName | null;
  nextRankLabel: string | null;
  nextRankAt: number | null;
  pointsToNextRank: number | null;
};

export type RewardItem = {
  id: string;
  name: string;
  description: string;
  category: string;
  spCost: number;
  rankRequired: RankName;
  rankRequiredLabel: string;
  unlocked: boolean;
  affordable: boolean;
  alreadyRedeemed: boolean;
};

export type RewardHistoryEntry = {
  id: string;
  eventType: string;
  pointsDelta: number;
  label: string;
  occurredOn: string | null;
  createdAt: string;
};

export type RedeemResult = {
  itemId: string;
  itemName: string;
  spSpent: number;
  spendablePointsLeft: number;
  message: string;
};

// Anh huy hieu trong public/rank - dat theo Rank, khong theo ten file goc
// (reward/photo_rank/*) de doi anh khong phai sua code.
export const RANK_IMAGES: Record<RankName, string> = {
  BRONZE: "/rank/dong.jpg",
  SILVER: "/rank/bac.jpg",
  GOLD: "/rank/vang.webp",
  DIAMOND: "/rank/kimcuong.webp",
};

type RewardSummaryApi = {
  lifetime_points: number;
  spendable_points: number;
  rank: RankName;
  rank_label: string;
  next_rank: RankName | null;
  next_rank_label: string | null;
  next_rank_at: number | null;
  points_to_next_rank: number | null;
};

type RewardItemApi = {
  id: string;
  name: string;
  description: string;
  category: string;
  sp_cost: number;
  rank_required: RankName;
  rank_required_label: string;
  unlocked: boolean;
  affordable: boolean;
  already_redeemed: boolean;
};

type RewardHistoryApi = {
  id: string;
  event_type: string;
  points_delta: number;
  label: string;
  occurred_on: string | null;
  created_at: string;
};

function auth(accessToken?: string | null): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function docLoi(response: Response, macDinh: string): Promise<string> {
  // Backend tra loi nghiep vu bang tieng Viet o truong `detail` (vd "Bạn còn
  // thiếu 5.000 điểm") - hien dung cau do cho benh nhan thay vi mot thong
  // bao chung chung.
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // Response khong phai JSON - dung cau mac dinh ben duoi.
  }
  return macDinh;
}

export async function getRewardSummary(accessToken?: string | null): Promise<RewardSummary> {
  const response = await fetch("/api/rewards/me", { headers: auth(accessToken) });
  if (!response.ok) throw new Error(await docLoi(response, "Không tải được điểm thưởng"));

  const d: RewardSummaryApi = await response.json();
  return {
    lifetimePoints: d.lifetime_points,
    spendablePoints: d.spendable_points,
    rank: d.rank,
    rankLabel: d.rank_label,
    nextRank: d.next_rank,
    nextRankLabel: d.next_rank_label,
    nextRankAt: d.next_rank_at,
    pointsToNextRank: d.points_to_next_rank,
  };
}

export async function listRewardCatalog(accessToken?: string | null): Promise<RewardItem[]> {
  const response = await fetch("/api/rewards/catalog", { headers: auth(accessToken) });
  if (!response.ok) throw new Error(await docLoi(response, "Không tải được danh sách quà"));

  const items: RewardItemApi[] = await response.json();
  return items.map((d) => ({
    id: d.id,
    name: d.name,
    description: d.description,
    category: d.category,
    spCost: d.sp_cost,
    rankRequired: d.rank_required,
    rankRequiredLabel: d.rank_required_label,
    unlocked: d.unlocked,
    affordable: d.affordable,
    alreadyRedeemed: d.already_redeemed,
  }));
}

export async function listRewardHistory(
  accessToken?: string | null,
): Promise<RewardHistoryEntry[]> {
  const response = await fetch("/api/rewards/history", { headers: auth(accessToken) });
  if (!response.ok) throw new Error(await docLoi(response, "Không tải được lịch sử điểm"));

  const rows: RewardHistoryApi[] = await response.json();
  return rows.map((d) => ({
    id: d.id,
    eventType: d.event_type,
    pointsDelta: d.points_delta,
    label: d.label,
    occurredOn: d.occurred_on,
    createdAt: d.created_at,
  }));
}

export async function redeemReward(
  itemId: string,
  accessToken?: string | null,
): Promise<RedeemResult> {
  const response = await fetch("/api/rewards/redeem", {
    method: "POST",
    headers: auth(accessToken),
    body: JSON.stringify({ item_id: itemId }),
  });
  if (!response.ok) throw new Error(await docLoi(response, "Không đổi được quà"));

  const d = await response.json();
  return {
    itemId: d.item_id,
    itemName: d.item_name,
    spSpent: d.sp_spent,
    spendablePointsLeft: d.spendable_points_left,
    message: d.message,
  };
}

export type DailyCheckinResult = {
  awarded: boolean;
  pointsAwarded: number;
  spendablePoints: number;
};

// Khao sat "hom nay ban cam thay the nao" o tab Hom nay. Loi o day KHONG
// duoc chan luong khao sat cua benh nhan (dieu huong sang Capy AI khi thay
// khong on) - nguoi goi bat loi va bo qua, xem patient/page.tsx.
//
// Tra ve null neu request loi (thay vi throw) - diem thuong la tinh nang
// PHU, nguoi goi khong nen phai boc try/catch chi de bo qua loi mang.
export async function postDailyCheckin(
  feltOk: boolean,
  accessToken?: string | null,
): Promise<DailyCheckinResult | null> {
  const response = await fetch("/api/rewards/daily-checkin", {
    method: "POST",
    headers: auth(accessToken),
    body: JSON.stringify({ felt_ok: feltOk }),
  });
  if (!response.ok) return null;
  const d = await response.json();
  return {
    awarded: d.awarded,
    pointsAwarded: d.points_awarded,
    spendablePoints: d.spendable_points,
  };
}
