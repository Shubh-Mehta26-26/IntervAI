import { AdminWorkspace } from "@/components/phase12-workspace";
import { requireSession } from "@/lib/server-api";
export default async function Page() { const session = await requireSession(); if (session.user.role !== "admin") return <p>This workspace is for administrator accounts.</p>; return <AdminWorkspace />; }
