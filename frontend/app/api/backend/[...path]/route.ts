import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const token = (await cookies()).get("coolproof_id_token")?.value;
  const organizationId = (await cookies()).get("coolproof_organization_id")?.value;
  const base = (process.env.COOLPROOF_API_BASE_URL ?? "https://3.15.34.25.sslip.io").replace(/\/$/, "");
  const target = `${base}/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (organizationId) headers.set("x-organization-id", organizationId);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
    return new NextResponse(upstream.body, { status: upstream.status, headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ error: { code: "backend_unavailable", message: "AWS API is unavailable", retryable: true } }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
