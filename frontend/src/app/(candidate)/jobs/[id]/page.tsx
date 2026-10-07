import { JobDetail } from "@/components/job-workspace";
import { requireSession } from "@/lib/server-api";
export default async function JobPage({ params }: { params: Promise<{ id: string }> }) { await requireSession(); return <JobDetail identifier={(await params).id} />; }
