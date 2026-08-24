import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const REQUEST_HEADER_ALLOWLIST = [
  "accept",
  "content-type",
  "idempotency-key",
  "if-match",
  "if-none-match",
  "last-event-id",
  "range",
] as const;

const RESPONSE_HEADER_ALLOWLIST = [
  "cache-control",
  "content-disposition",
  "content-length",
  "content-range",
  "content-type",
  "etag",
  "retry-after",
  "x-request-id",
] as const;

function backendBaseUrl(): URL | null {
  const configured = process.env.COOLPROOF_API_BASE_URL?.trim();
  if (!configured) return null;
  try {
    const url = new URL(configured);
    if (!(["http:", "https:"] as string[]).includes(url.protocol) || url.username || url.password) return null;
    return url;
  } catch {
    return null;
  }
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const base = backendBaseUrl();
  if (!base) {
    return NextResponse.json(
      { error: { code: "backend_not_configured", message: "AWS API is not configured", retryable: false } },
      { status: 503 },
    );
  }

  const cookieStore = await cookies();
  const token = cookieStore.get("coolproof_id_token")?.value;
  const organizationId = cookieStore.get("coolproof_organization_id")?.value;
  const target = new URL(path.map(encodeURIComponent).join("/"), `${base.toString().replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;

  // Build a narrow upstream header set. In particular, never forward the
  // browser Cookie header: it contains the Cognito refresh token, which the
  // FastAPI service neither needs nor should receive.
  const headers = new Headers();
  for (const name of REQUEST_HEADER_ALLOWLIST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (organizationId) headers.set("x-organization-id", organizationId);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store" });
    const responseHeaders = new Headers();
    for (const name of RESPONSE_HEADER_ALLOWLIST) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    if (!responseHeaders.has("content-type")) responseHeaders.set("content-type", "application/json");
    return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return NextResponse.json({ error: { code: "backend_unavailable", message: "AWS API is unavailable", retryable: true } }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
