import { NextRequest, NextResponse } from "next/server";

const publicPaths = new Set(["/", "/login"]);

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    publicPaths.has(pathname)
    || pathname.startsWith("/api/")
    || pathname.startsWith("/_next/")
    || pathname.includes(".")
  ) {
    return NextResponse.next();
  }
  if (!request.cookies.has("coolproof_id_token")) {
    const login = new URL("/login", request.url);
    login.searchParams.set("returnTo", pathname);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/:path*"] };
