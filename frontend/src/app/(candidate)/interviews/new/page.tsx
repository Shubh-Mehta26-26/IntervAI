import { NewInterview } from "@/components/interview-workspace";
import { requireSession } from "@/lib/server-api";
export default async function NewInterviewPage() { await requireSession(); return <NewInterview />; }
