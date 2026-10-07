import { InterviewRoom } from "@/components/interview-workspace";
import { requireSession } from "@/lib/server-api";
export default async function InterviewPage({ params }: { params: Promise<{ id: string }> }) { await requireSession(); const { id } = await params; return <InterviewRoom identifier={id} />; }
