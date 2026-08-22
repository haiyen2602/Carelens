"use client";

// Hang doi duyet yeu cau bo sung thuoc (FB-14).
//
// Day la CANH CUA cua duong ngoai le: danh muc thuoc la allowlist dong, va
// day la cho duy nhat mot thuoc ngoai danh muc tro thanh ke duoc. Bam duyet
// qua loa o day la mo lai dung lo hong FB-14 - vi vay man hinh hien du thong
// tin de nguoi duyet quyet dinh duoc, khong chi mot nut Duyet.

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import {
  approveDrugRequest,
  listAllDrugRequests,
  rejectDrugRequest,
  type DrugRequest,
  type DrugRequestStatus,
} from "@/lib/drug-requests";

const TABS: { value: DrugRequestStatus; label: string }[] = [
  { value: "PENDING", label: "Chờ duyệt" },
  { value: "APPROVED", label: "Đã duyệt" },
  { value: "REJECTED", label: "Đã từ chối" },
];

function BieuTuongTrangThai({ status }: { status: DrugRequestStatus }) {
  if (status === "APPROVED") return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (status === "REJECTED") return <XCircle className="h-4 w-4 text-destructive" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}

export default function AdminDrugRequestsPage() {
  const { accessToken } = useAuth();
  const [tab, setTab] = useState<DrugRequestStatus>("PENDING");
  const [rows, setRows] = useState<DrugRequest[]>([]);
  const [dangTai, setDangTai] = useState(true);
  // Ly do tu choi, giu rieng cho tung dong - go o dong nay khong lam anh huong
  // dong khac.
  const [lyDo, setLyDo] = useState<Record<string, string>>({});
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);

  const nap = useCallback(async () => {
    setDangTai(true);
    try {
      setRows(await listAllDrugRequests(tab, accessToken));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách");
    } finally {
      setDangTai(false);
    }
  }, [tab, accessToken]);

  useEffect(() => {
    void nap();
  }, [nap]);

  const duyet = async (row: DrugRequest) => {
    setDangXuLy(row.id);
    try {
      const updated = await approveDrugRequest(row.id, undefined, accessToken);
      toast.success(`Đã duyệt. Mã thuốc: ${updated.approved_drug_id}`);
      void nap();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không duyệt được");
    } finally {
      setDangXuLy(null);
    }
  };

  const tuChoi = async (row: DrugRequest) => {
    const note = (lyDo[row.id] ?? "").trim();
    if (!note) {
      // Backend cung chan, nhung bao o day thi nguoi duyet biet ngay thay vi
      // doi mot vong mang.
      toast.error("Nhập lý do trước khi từ chối.");
      return;
    }
    setDangXuLy(row.id);
    try {
      await rejectDrugRequest(row.id, note, accessToken);
      toast.success("Đã từ chối yêu cầu.");
      setLyDo((prev) => ({ ...prev, [row.id]: "" }));
      void nap();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không từ chối được");
    } finally {
      setDangXuLy(null);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Thuốc được duyệt ở đây sẽ kê đơn được ngay, nhưng chatbot chưa trả lời được về nó (chưa có
        dữ liệu RAG).
      </p>

      <div className="flex gap-2">
        {TABS.map((t) => (
          <Button
            key={t.value}
            variant={tab === t.value ? "default" : "outline"}
            size="sm"
            onClick={() => setTab(t.value)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {dangTai && <p className="text-sm text-muted-foreground">Đang tải…</p>}

      {!dangTai && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Không có yêu cầu nào.</p>
      )}

      <div className="space-y-4">
        {rows.map((row) => (
          <div key={row.id} className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <BieuTuongTrangThai status={row.status} />
                  <span className="font-medium">{row.ten_thuoc}</span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {row.dang_thuoc} · {row.duong_dung}
                  {row.ham_luong ? ` · ${row.ham_luong}` : ""}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Bác sĩ {row.requested_by_doctor_id} ·{" "}
                  {new Date(row.created_at).toLocaleString("vi-VN")}
                </p>
                {row.ly_do && <p className="mt-2 text-sm">Lý do: {row.ly_do}</p>}
                {row.approved_drug_id && (
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    {row.approved_drug_id}
                  </p>
                )}
                {row.review_note && (
                  <p className="mt-2 text-sm text-muted-foreground">Ghi chú: {row.review_note}</p>
                )}
              </div>

              {row.status === "PENDING" && (
                <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-64">
                  <Button size="sm" disabled={dangXuLy === row.id} onClick={() => duyet(row)}>
                    Duyệt
                  </Button>
                  <Input
                    value={lyDo[row.id] ?? ""}
                    onChange={(e) => setLyDo((prev) => ({ ...prev, [row.id]: e.target.value }))}
                    placeholder="Lý do từ chối"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={dangXuLy === row.id}
                    onClick={() => tuChoi(row)}
                  >
                    Từ chối
                  </Button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
