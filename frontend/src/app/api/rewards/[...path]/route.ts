// Server-side proxy cho /api/v1/rewards/* cua backend that.
//
// Gop CA 5 endpoint (me / catalog / history / redeem / daily-checkin) vao 1
// route dong thay vi 5 file gan het nhau: chung deu chi lam dung mot viec -
// chuyen tiep Authorization roi tra nguyen van ket qua. Backend tu lay
// patient_id tu JWT nen khong co tham so nao can xu ly rieng.
//
// KHONG gan X-Internal-Secret o day (khac app/api/doses/route.ts): moi route
// rewards deu dung get_current_user, khong route nao dung
// require_internal_secret - gan thua chi lam lo mot bi mat khong can thiet.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Chi cho phep dung cac duong dan da biet - chan viec ghep chuoi tu URL
// nguoi dung thanh loi goi toi endpoint backend bat ky.
const DUONG_DAN_HOP_LE = new Set(["me", "catalog", "history", "redeem", "daily-checkin"]);

async function chuyenTiep(
  request: Request,
  path: string[],
  method: "GET" | "POST",
): Promise<Response> {
  const duongDan = path.join("/");
  if (!DUONG_DAN_HOP_LE.has(duongDan)) {
    return Response.json({ detail: "Không tìm thấy endpoint" }, { status: 404 });
  }

  const authorization = request.headers.get("authorization");
  const upstream = await fetch(`${BACKEND_URL}/api/v1/rewards/${duongDan}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    ...(method === "POST" ? { body: await request.text() } : {}),
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return chuyenTiep(request, path, "GET");
}

export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return chuyenTiep(request, path, "POST");
}
