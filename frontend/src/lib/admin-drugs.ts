export type MappingStatus = "ACTIVE" | "AMBIGUOUS" | "RETIRED" | "UNMAPPED";

export type AdminDrugItem = {
  id: string;
  legacy_drug_id: string | null;
  display_name: string;
  dosage_form: string | null;
  route: string | null;
  strength_text: string | null;
  category_id: string | null;
  ingredients: string[];
  mapping_status: MappingStatus | null;
  mappings: Array<{
    id: string;
    legacy_drug_id: string;
    drug_product_id: string;
    mapping_status: MappingStatus;
    source_manifest_version: string | null;
  }>;
};

export type AdminDrugListResponse = {
  items: AdminDrugItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listAdminDrugs(
  options: {
    q?: string;
    mappingStatus?: MappingStatus;
    page?: number;
    pageSize?: number;
    accessToken?: string | null;
    signal?: AbortSignal;
  } = {},
): Promise<AdminDrugListResponse> {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 10),
  });
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.mappingStatus) params.set("mapping_status", options.mappingStatus);

  const response = await fetch(`${API_BASE}/api/v1/admin/drugs?${params}`, {
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
