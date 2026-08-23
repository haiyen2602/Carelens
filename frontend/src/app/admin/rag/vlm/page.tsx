"use client";

// Tab "VLM (Đếm thuốc)" trong Giám sát RAG & AI - THEM 2026-08-22. Doc lap
// HOAN TOAN voi /admin/rag (chatbot, viec cua thanh vien khac): fetch tu 2
// endpoint rieng (backend/api/vlm_monitoring_routes.py), Langfuse project
// rieng (backend/services/vlm_telemetry.py). Khung trang copy phong cach tu
// admin/rag/page.tsx (poll 10s, AreaChart, surface-card) nhung KHONG import
// gi tu file do - tranh moi rang buoc code giua 2 pipeline.

import { useEffect, useState } from "react";
import { Activity, AlertCircle, RefreshCw } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { PipelineSwitcher } from "../_pipeline-switcher";

type VlmHealth = {
  status: string;
  sample_size: number;
  kpis: {
    match_rate: number;
    mismatch_rate: number;
    error_rate: number;
    retake_rate: number;
    caregiver_review_count: number;
    caregiver_override_rate: number | null;
    caregiver_override_count: number;
    caregiver_override_resolved_count: number;
    avg_confidence: number;
    avg_latency_ms: number | null;
  };
  trend: { date: string; match_rate: number; avg_confidence: number; attempts: number }[];
  langfuse: { connected: boolean; host: string };
};

type VlmAttempt = {
  id: string;
  dose_event_id: string;
  patient_id: string;
  attempt: number;
  ket_qua: string;
  confidence: string | null;
  ghi_chu: string | null;
  thong_bao: string | null;
  created_at: string | null;
};

const KET_QUA_LABEL: Record<string, { label: string; className: string }> = {
  khop: { label: "Khớp", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  lech: { label: "Lệch", className: "bg-amber-50 text-amber-700 border-amber-200" },
  khong_xac_minh_duoc: {
    label: "Không xác minh được",
    className: "bg-muted text-muted-foreground border-border",
  },
  loi_he_thong: { label: "Lỗi hệ thống", className: "bg-rose-50 text-rose-700 border-rose-200" },
  dang_xu_ly: { label: "Đang xử lý", className: "bg-blue-50 text-blue-700 border-blue-200" },
};

export default function VlmDashboardPage() {
  const { accessToken } = useAuth();
  const [healthData, setHealthData] = useState<VlmHealth | null>(null);
  const [attempts, setAttempts] = useState<VlmAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchDashboardData = async (isBackground = false) => {
    if (!accessToken) return;
    if (!isBackground) setLoading(true);
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
      const [healthRes, attemptsRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/admin/vlm/health`, { headers })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        fetch(`${apiBase}/api/v1/admin/vlm/attempts`, { headers })
          .then((r) => (r.ok ? r.json() : []))
          .catch(() => []),
      ]);
      if (healthRes) setHealthData(healthRes);
      if (Array.isArray(attemptsRes)) setAttempts(attemptsRes);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("Failed to load VLM monitoring data:", e);
    } finally {
      if (!isBackground) setLoading(false);
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    fetchDashboardData();
    const interval = setInterval(() => fetchDashboardData(true), 10000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const kpis = healthData?.kpis || {
    match_rate: 0,
    mismatch_rate: 0,
    error_rate: 0,
    retake_rate: 0,
    caregiver_review_count: 0,
    caregiver_override_rate: null,
    caregiver_override_count: 0,
    caregiver_override_resolved_count: 0,
    avg_confidence: 0,
    avg_latency_ms: null,
  };
  const trend = healthData?.trend || [];

  return (
    <div className="space-y-6">
      <PipelineSwitcher active="vlm" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Giám sát VLM — Đếm thuốc & Đối chiếu đơn</h1>
            {healthData?.langfuse?.connected ? (
              <a
                href={healthData.langfuse.host}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                Langfuse: Đã kết nối
              </a>
            ) : (
              <span className="flex items-center gap-1.5 rounded-full bg-muted border border-border px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                Langfuse: Chưa kết nối
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Dữ liệu thật 100% từ bảng photo_verification (mỗi lần chụp là 1 dòng thật) — cập nhật
            mỗi 10 giây. Cập nhật lúc {lastUpdated.toLocaleTimeString("vi-VN")}.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchDashboardData(false)}
          className="flex items-center gap-1.5"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Làm mới ngay
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">Match Rate</span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {kpis.match_rate}%
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">
            Số đếm khớp với đơn thuốc / tổng số lần chụp
          </p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">Retake Rate</span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {kpis.retake_rate}%
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">
            Tỉ lệ phải chụp lại (attempt &gt; 1)
          </p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">
            Chuyển người thân duyệt
          </span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-amber-600">
            {kpis.caregiver_review_count}
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">
            Hết 3 lần vẫn không khớp đơn
          </p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">
            Tỉ lệ người thân bác bỏ
          </span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {kpis.caregiver_override_rate === null ? "—" : `${kpis.caregiver_override_rate}%`}
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">
            {kpis.caregiver_override_resolved_count > 0
              ? `Trên ${kpis.caregiver_override_resolved_count} ca đã xem — accuracy thật trên production`
              : "Chưa có ca nào người thân xem xong"}
          </p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">Lỗi hệ thống</span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {kpis.error_rate}%
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">
            Model/mạng lỗi — không trừ lượt bệnh nhân
          </p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">Độ tin cậy TB</span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {Math.round(kpis.avg_confidence * 100)}%
          </p>
          <p className="mt-2 text-xs font-semibold text-muted-foreground">Model tự báo cáo</p>
        </div>
        <div className="surface-card p-5">
          <span className="text-xs font-semibold text-muted-foreground uppercase">Độ trễ TB</span>
          <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
            {kpis.avg_latency_ms === null ? (
              "—"
            ) : (
              <>
                {kpis.avg_latency_ms} <span className="text-sm font-normal text-muted-foreground">ms</span>
              </>
            )}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {kpis.avg_latency_ms === null
              ? "Chưa có lần chụp nào từ lúc backend khởi động lại"
              : "Từ trace gần đây (buffer nội bộ)"}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="surface-card p-5">
        <h2 className="text-base font-bold text-foreground mb-4 flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          Xu hướng đối chiếu (7 ngày qua)
        </h2>
        {trend.length === 0 || trend.every((t) => t.attempts === 0) ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Chưa có dữ liệu chụp ảnh trong 7 ngày qua.
          </div>
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="colorMatch" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" stroke="var(--muted-foreground)" fontSize={12} />
                <YAxis
                  domain={[0, 100]}
                  stroke="var(--muted-foreground)"
                  fontSize={12}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#ffffff",
                    borderColor: "var(--border)",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="match_rate"
                  stroke="#10b981"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorMatch)"
                  name="Match Rate (%)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Recent attempts table */}
      <div className="surface-card overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h3 className="font-bold text-foreground flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Lần xác minh gần đây
          </h3>
          <span className="text-xs text-muted-foreground">{attempts.length} bản ghi</span>
        </div>
        {attempts.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            Chưa có lần chụp ảnh nào được ghi nhận.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground">
                  <th className="py-3 px-4">Thời gian</th>
                  <th className="py-3 px-4">Bệnh nhân</th>
                  <th className="py-3 px-4">Lần</th>
                  <th className="py-3 px-4">Kết quả</th>
                  <th className="py-3 px-4">Độ tin cậy</th>
                  <th className="py-3 px-4">Ghi chú</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {attempts.map((a) => {
                  const chip = KET_QUA_LABEL[a.ket_qua] ?? {
                    label: a.ket_qua,
                    className: "bg-muted text-muted-foreground border-border",
                  };
                  return (
                    <tr key={a.id} className="hover:bg-muted/30">
                      <td className="py-2.5 px-4 text-xs text-muted-foreground">
                        {a.created_at ? new Date(a.created_at).toLocaleString("vi-VN") : "—"}
                      </td>
                      <td className="py-2.5 px-4 font-mono text-xs">{a.patient_id}</td>
                      <td className="py-2.5 px-4">{a.attempt}</td>
                      <td className="py-2.5 px-4">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${chip.className}`}>
                          {chip.label}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">{a.confidence ?? "—"}</td>
                      <td className="py-2.5 px-4 text-xs text-muted-foreground">{a.ghi_chu ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
