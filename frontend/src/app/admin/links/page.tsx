"use client";

import { HeartHandshake, Plus, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listAccounts, type AccountRecord } from "@/lib/accounts";
import {
  createCaregiverLink,
  deleteCaregiverLink,
  listCaregiverLinksForPatient,
  type CaregiverLink,
} from "@/lib/caregivers";
import { listReportingPatients, type ReportingPatient } from "@/lib/reporting";

export default function LinksPage() {
  const [patients, setPatients] = useState<ReportingPatient[]>([]);
  const [caregivers, setCaregivers] = useState<AccountRecord[]>([]);
  const [linksByPatient, setLinksByPatient] = useState<Record<string, CaregiverLink[]>>({});
  const [loading, setLoading] = useState(true);
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [caregiverAccountId, setCaregiverAccountId] = useState("");
  const [relationship, setRelationship] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [pts, accounts] = await Promise.all([listReportingPatients(), listAccounts()]);
      setPatients(pts);
      setCaregivers(accounts.filter((a) => a.role === "caregiver"));
      const entries = await Promise.all(
        pts.map(async (p) => [p.id, await listCaregiverLinksForPatient(p.id)] as const),
      );
      setLinksByPatient(Object.fromEntries(entries));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách liên kết");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const reloadPatientLinks = async (patientId: string) => {
    const links = await listCaregiverLinksForPatient(patientId);
    setLinksByPatient((prev) => ({ ...prev, [patientId]: links }));
  };

  const removeCaregiver = async (patientId: string, linkId: string) => {
    try {
      await deleteCaregiverLink(linkId);
      await reloadPatientLinks(patientId);
      toast.success("Đã gỡ liên kết");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gỡ được liên kết");
    }
  };

  const addCaregiver = async (patientId: string) => {
    if (!caregiverAccountId) return;
    try {
      await createCaregiverLink({
        caregiverAccountId,
        patientId,
        relationship: relationship || "Người thân",
      });
      await reloadPatientLinks(patientId);
      toast.success("Đã thêm liên kết");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không thêm được liên kết");
    } finally {
      setAddingTo(null);
      setCaregiverAccountId("");
      setRelationship("");
    }
  };

  return (
    <div className="space-y-6">
      {loading && <p className="text-sm text-muted-foreground">Đang tải…</p>}

      <div className="space-y-4">
        {patients.map((p) => {
          const links = linksByPatient[p.id] ?? [];
          return (
            <div key={p.id} className="surface-card p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                    {p.fullName.charAt(0)}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{p.fullName}</p>
                    <p className="text-xs text-muted-foreground">{p.id}</p>
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-border p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <HeartHandshake className="h-3.5 w-3.5" /> Người thân liên kết
                  </p>
                  <button
                    onClick={() => setAddingTo(addingTo === p.id ? null : p.id)}
                    className="text-xs font-semibold text-primary"
                  >
                    <Plus className="mr-0.5 inline h-3.5 w-3.5" /> Thêm
                  </button>
                </div>

                <div className="mt-2 space-y-2">
                  {links.length === 0 && (
                    <p className="text-sm text-muted-foreground">Chưa có người thân liên kết.</p>
                  )}
                  {links.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-muted px-3 py-2"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <UserRound className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{c.caregiverName}</p>
                          <p className="text-xs text-muted-foreground">{c.relationship}</p>
                        </div>
                      </div>
                      <button
                        onClick={() => removeCaregiver(p.id, c.id)}
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                        title="Gỡ liên kết"
                        aria-label={`Gỡ liên kết với ${c.caregiverName}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}

                  {addingTo === p.id && (
                    <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold">Thêm người thân</p>
                        <button onClick={() => setAddingTo(null)} aria-label="Đóng">
                          <X className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="cg-name" className="text-xs">
                          Tài khoản người thân
                        </Label>
                        <select
                          id="cg-name"
                          value={caregiverAccountId}
                          onChange={(e) => setCaregiverAccountId(e.target.value)}
                          className="h-9 w-full rounded-lg border border-input bg-card px-2 text-sm outline-none"
                        >
                          <option value="">Chọn tài khoản...</option>
                          {caregivers.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.fullName} ({c.email})
                            </option>
                          ))}
                        </select>
                        <Label htmlFor="cg-rel" className="text-xs">
                          Mối quan hệ
                        </Label>
                        <Input
                          id="cg-rel"
                          value={relationship}
                          onChange={(e) => setRelationship(e.target.value)}
                          placeholder="VD: Con gái, Vợ..."
                          className="h-9"
                        />
                        <Button size="sm" className="w-full" onClick={() => addCaregiver(p.id)}>
                          Xác nhận liên kết
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {!loading && patients.length === 0 && (
          <p className="surface-card p-8 text-center text-sm text-muted-foreground">
            Chưa có bệnh nhân nào.
          </p>
        )}
      </div>
    </div>
  );
}
