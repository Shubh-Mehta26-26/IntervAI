import { RecruiterWorkspace } from "@/components/phase12-workspace";
import { requireSession } from "@/lib/server-api";
export default async function Page() { const session = await requireSession(); if (session.user.role !== "recruiter") return <p>This workspace is for recruiter accounts.</p>; return <RecruiterWorkspace />; }
