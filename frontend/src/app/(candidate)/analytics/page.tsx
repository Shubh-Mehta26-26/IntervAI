import { AnalyticsWorkspace } from "@/components/phase12-workspace";
import { requireSession } from "@/lib/server-api";
export default async function Page() { const session = await requireSession(); if (session.user.role !== "candidate") return <p>This workspace is for candidate accounts.</p>; return <AnalyticsWorkspace />; }
