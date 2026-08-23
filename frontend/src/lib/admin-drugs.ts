export type MappingStatus = "ACTIVE" | "AMBIGUOUS" | "RETIRED" | "UNMAPPED";

// Dong nay den tu dau (them 2026-08-21, FB-14). CANONICAL = artifact
// Canonical V2 co provenance. DRUG_REQUEST = thuoc bac si xin bo sung da
// duoc admin duyet - chua co trong artifact, chua co du lieu RAG.
export type DrugSource = "CANONICAL" | "DRUG_REQUEST";

export type AdminDrugItem = {
  id: string;
  legacy_drug_id: string | null;
  display_name: string;
  dosage_form: string | null;
  route: string | null;
  strength_text: string | null;
  packaging: string | null;
  category_id: string | null;
  category_name: string | null;
  severity: string | null;
  ingredients: string[];
  mapping_status: MappingStatus | null;
  source: DrugSource;
  mappings: Array<{
    id: string;
    legacy_drug_id: string;
    drug_product_id: string;
    mapping_status: MappingStatus;
    source_manifest_version: string | null;
  }>;
};

export type AdminDrugDetail = AdminDrugItem & {
  cong_dung?: string | null;
  cach_dung?: string | null;
  tac_dung_phu?: string | null;
  bao_quan?: string | null;
};

export type AdminDrugFilters = {
  dosage_forms: string[];
  routes: string[];
};

export type AdminDrugListResponse = {
  items: AdminDrugItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type AdminDrugCreatePayload = {
  display_name: string;
  dosage_form?: string;
  route?: string;
  strength_text?: string;
  packaging?: string;
  category?: string;
  severity?: string;
  mapping_status?: MappingStatus;
  cong_dung?: string;
  cach_dung?: string;
  tac_dung_phu?: string;
  bao_quan?: string;
};

export type AdminDrugUpdatePayload = {
  display_name?: string;
  dosage_form?: string;
  route?: string;
  strength_text?: string;
  packaging?: string;
  category?: string;
  severity?: string;
  mapping_status?: MappingStatus;
  cong_dung?: string;
  cach_dung?: string;
  tac_dung_phu?: string;
  bao_quan?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function buildAdminDrugsUrl(
  options: {
    q?: string;
    dosageForm?: string;
    route?: string;
    mappingStatus?: MappingStatus;
    page?: number;
    pageSize?: number;
  } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
  });
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.dosageForm && options.dosageForm !== "__tat_ca__") {
    params.set("dosage_form", options.dosageForm);
  }
  if (options.route && options.route !== "__tat_ca__") {
    params.set("route", options.route);
  }
  if (options.mappingStatus) params.set("mapping_status", options.mappingStatus);
  return `${API_BASE}/api/v1/admin/drugs?${params}`;
}

export async function getAdminDrugFilters(
  accessToken?: string | null,
  signal?: AbortSignal,
): Promise<AdminDrugFilters> {
  const response = await fetch(`${API_BASE}/api/v1/admin/drugs/filters`, {
    signal,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể tải bộ lọc thuốc (${response.status})`,
    );
  }
  return response.json() as Promise<AdminDrugFilters>;
}

export async function listAdminDrugs(
  options: {
    q?: string;
    dosageForm?: string;
    route?: string;
    mappingStatus?: MappingStatus;
    page?: number;
    pageSize?: number;
    accessToken?: string | null;
    signal?: AbortSignal;
  } = {},
): Promise<AdminDrugListResponse> {
  const response = await fetch(buildAdminDrugsUrl(options), {
    signal: options.signal,
    headers: options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể tải dữ liệu thuốc (${response.status})`,
    );
  }
  return response.json() as Promise<AdminDrugListResponse>;
}

export async function getAdminDrugDetail(
  drugId: string,
  accessToken?: string | null,
  signal?: AbortSignal,
): Promise<AdminDrugDetail> {
  const response = await fetch(`${API_BASE}/api/v1/admin/drugs/${encodeURIComponent(drugId)}`, {
    signal,
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể tải chi tiết thuốc (${response.status})`,
    );
  }
  return response.json() as Promise<AdminDrugDetail>;
}

export async function createAdminDrug(
  payload: AdminDrugCreatePayload,
  accessToken?: string | null,
): Promise<AdminDrugDetail> {
  const response = await fetch(`${API_BASE}/api/v1/admin/drugs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể thêm thuốc mới (${response.status})`,
    );
  }
  return response.json() as Promise<AdminDrugDetail>;
}

export async function updateAdminDrug(
  drugId: string,
  input: AdminDrugUpdatePayload,
  accessToken?: string | null,
): Promise<AdminDrugDetail> {
  const response = await fetch(`${API_BASE}/api/v1/admin/drugs/${encodeURIComponent(drugId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể cập nhật dữ liệu thuốc (${response.status})`,
    );
  }
  return response.json() as Promise<AdminDrugDetail>;
}

export async function deleteAdminDrug(
  drugId: string,
  accessToken?: string | null,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/admin/drugs/${encodeURIComponent(drugId)}`, {
    method: "DELETE",
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể xóa dữ liệu thuốc (${response.status})`,
    );
  }
}
