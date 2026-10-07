import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const origin = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${origin}/api/v1/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(7000),
    });
    const body = await response.json();
    if (![200, 503].includes(response.status) ||
        !["ready", "unavailable"].includes(body.status) ||
        !["connected", "unavailable"].includes(body.database) ||
        !["available", "missing", "unknown"].includes(body.vector)) {
      throw new Error("Unexpected health response");
    }
    return NextResponse.json({
      api: "connected", status: body.status,
      database: body.database, vector: body.vector,
    }, { status: response.status });
  } catch {
    return NextResponse.json({
      api: "unavailable", status: "unavailable", database: "unknown", vector: "unknown",
    }, { status: 503 });
  }
}
