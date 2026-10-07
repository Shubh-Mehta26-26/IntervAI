import { redirect } from "next/navigation";
import { serverFetch } from "@/lib/server-api";

export const dynamic = "force-dynamic";
export default async function Home() {
  let signedIn = false;
  try { signedIn = (await serverFetch("/auth/session")).ok; } catch { /* Login exposes service failures. */ }
  redirect(signedIn ? "/dashboard" : "/login");
}
