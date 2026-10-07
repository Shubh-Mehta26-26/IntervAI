import { InterviewLibrary } from "@/components/interview-workspace";
import { requireSession } from "@/lib/server-api";
export default async function InterviewsPage() { await requireSession(); return <InterviewLibrary />; }
