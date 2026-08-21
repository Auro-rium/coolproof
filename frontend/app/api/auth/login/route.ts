import { InitiateAuthCommand, CognitoIdentityProviderClient } from "@aws-sdk/client-cognito-identity-provider";
import { createHmac } from "node:crypto";
import { NextResponse } from "next/server";

const client = new CognitoIdentityProviderClient({ region: process.env.COGNITO_REGION ?? "us-east-2" });

export async function POST(request: Request) {
  const body = await request.json().catch(() => null) as { email?: string; password?: string; organizationId?: string } | null;
  if (!body?.email || !body.password || !body.organizationId) return NextResponse.json({ error: "Email, password, and organization ID are required" }, { status: 400 });
  const clientId = process.env.COGNITO_CLIENT_ID;
  const clientSecret = process.env.COGNITO_CLIENT_SECRET;
  if (!clientId || !clientSecret) return NextResponse.json({ error: "Authentication is not configured" }, { status: 503 });
  const secretHash = createHmac("sha256", clientSecret).update(`${body.email}${clientId}`).digest("base64");
  try {
    const result = await client.send(new InitiateAuthCommand({ AuthFlow: "USER_PASSWORD_AUTH", ClientId: clientId, AuthParameters: { USERNAME: body.email, PASSWORD: body.password, SECRET_HASH: secretHash } }));
    const idToken = result.AuthenticationResult?.IdToken;
    const refreshToken = result.AuthenticationResult?.RefreshToken;
    if (!idToken) return NextResponse.json({ error: "Cognito did not return an ID token" }, { status: 401 });
    const response = NextResponse.json({ ok: true });
    response.cookies.set("coolproof_id_token", idToken, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 3600 });
    if (refreshToken) response.cookies.set("coolproof_refresh_token", refreshToken, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 });
    response.cookies.set("coolproof_organization_id", body.organizationId, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 });
    return response;
  } catch (error) {
    const message = error instanceof Error && error.name === "NotAuthorizedException" ? "Cognito rejected the credentials" : "Unable to sign in right now";
    return NextResponse.json({ error: message }, { status: 401 });
  }
}
