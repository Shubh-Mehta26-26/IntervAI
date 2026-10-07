import { ResumeWorkspace } from "@/components/resume-workspace";
import { requireSession } from "@/lib/server-api";

export default async function ResumePage() { await requireSession(); return <ResumeWorkspace />; }
