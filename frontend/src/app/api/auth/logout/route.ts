import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { REFRESH_COOKIE_NAME } from "../login/route";

export async function POST() {
  const cookieStore = await cookies();
  cookieStore.delete(REFRESH_COOKIE_NAME);
  return NextResponse.json({ ok: true });
}
