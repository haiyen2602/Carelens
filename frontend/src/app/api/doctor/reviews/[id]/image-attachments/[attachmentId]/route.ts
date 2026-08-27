// Proxy ảnh riêng tư của một handoff BUILD-44/B-07. Backend vẫn là nơi kiểm
// tra bác sĩ đang đăng nhập có đúng là người được phân công hay không; proxy
// chỉ chuyển tiếp Authorization và giữ nguyên response nhị phân.

import { forwardAuthorization } from "../../../authorization";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; attachmentId: string }> },
) {
  const { id, attachmentId } = await params;
  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/doctor/reviews/${encodeURIComponent(id)}/image-attachments/${encodeURIComponent(attachmentId)}`,
    { headers: forwardAuthorization(request) },
  );

  if (!upstream.ok) {
    const data = await upstream.text();
    return new Response(data, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": upstream.headers.get("Content-Type") ?? "image/jpeg",
    },
  });
}
