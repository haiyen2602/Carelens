"use client";

import { HeartHandshake, Plus, Stethoscope, Trash2, UserRound, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ACCOUNTS, LINKS, type PatientLink } from "@/lib/admin-mock";

const doctors = ACCOUNTS.filter((a) => a.role === "doctor");
const caregivers = ACCOUNTS.filter((a) => a.role === "caregiver");

export default function LinksPage() {
  const [links, setLinks] = useState<PatientLink[]>(LINKS);
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [caregiverName, setCaregiverName] = useState("");
  const [relationship, setRelationship] = useState("");

  const removeCaregiver = (linkId: string, cgId: string) =>
    setLinks((prev) =>
      prev.map((l) =>
        l.id === linkId ? { ...l, caregivers: l.caregivers.filter((c) => c.id !== cgId) } : l,
      ),
    );

  const changeDoctor = (linkId: string, doctorId: string) => {
    const d = doctors.find((x) => x.id === doctorId);
    if (!d) return;
    setLinks((prev) =>
      prev.map((l) => (l.id === linkId ? { ...l, doctor: d.name, doctorId: d.id } : l)),
    );
  };

  const addCaregiver = (linkId: string) => {
    if (!caregiverName.trim()) return;
    setLinks((prev) =>
      prev.map((l) =>
        l.id === linkId
          ? {
              ...l,
              caregivers: [
                ...l.caregivers,
                {
                  id: `CG-${Math.random().toString(36).slice(2, 7)}`,
                  name: caregiverName,
                  relationship: relationship || "Người thân",
                },
              ],
            }
          : l,
      ),
    );
    setAddingTo(null);
    setCaregiverName("");
    setRelationship("");
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">
          Liên kết bệnh nhân · bác sĩ · người thân
        </h1>
        <p className="text-sm text-muted-foreground">
          Mỗi bệnh nhân có đúng 1 bác sĩ phụ trách chính và 0..n người thân. Mọi truy vấn dữ liệu
          bệnh nhân đều dựa trên các liên kết này, không chỉ dựa trên vai trò.
        </p>
      </header>

      <div className="space-y-4">
        {links.map((l) => (
          <div key={l.id} className="surface-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                  {l.patient.charAt(0)}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-semibold">{l.patient}</p>
                  <p className="text-xs text-muted-foreground">{l.patientId}</p>
                </div>
              </div>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-border p-4">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Stethoscope className="h-3.5 w-3.5" /> Bác sĩ phụ trách chính
                </p>
                <select
                  value={l.doctorId}
                  onChange={(e) => changeDoctor(l.id, e.target.value)}
                  className="mt-2 h-10 w-full rounded-lg border border-input bg-card px-3 text-sm outline-none focus:border-primary"
                >
                  {doctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="rounded-xl border border-border p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <HeartHandshake className="h-3.5 w-3.5" /> Người thân liên kết
                  </p>
                  <button
                    onClick={() => setAddingTo(addingTo === l.id ? null : l.id)}
                    className="text-xs font-semibold text-primary"
                  >
                    <Plus className="mr-0.5 inline h-3.5 w-3.5" /> Thêm
                  </button>
                </div>

                <div className="mt-2 space-y-2">
                  {l.caregivers.length === 0 && (
                    <p className="text-sm text-muted-foreground">Chưa có người thân liên kết.</p>
                  )}
                  {l.caregivers.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-muted px-3 py-2"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <UserRound className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{c.name}</p>
                          <p className="text-xs text-muted-foreground">{c.relationship}</p>
                        </div>
                      </div>
                      <button
                        onClick={() => removeCaregiver(l.id, c.id)}
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                        title="Gỡ liên kết"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}

                  {addingTo === l.id && (
                    <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold">Thêm người thân</p>
                        <button onClick={() => setAddingTo(null)}>
                          <X className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="cg-name" className="text-xs">
                          Tên người thân
                        </Label>
                        <select
                          id="cg-name"
                          value={caregiverName}
                          onChange={(e) => setCaregiverName(e.target.value)}
                          className="h-9 w-full rounded-lg border border-input bg-card px-2 text-sm outline-none"
                        >
                          <option value="">Chọn tài khoản...</option>
                          {caregivers.map((c) => (
                            <option key={c.id} value={c.name}>
                              {c.name} ({c.id})
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
                        <Button size="sm" className="w-full" onClick={() => addCaregiver(l.id)}>
                          Xác nhận liên kết
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
