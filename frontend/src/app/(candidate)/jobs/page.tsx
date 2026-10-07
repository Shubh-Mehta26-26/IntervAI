import { JobLibrary } from "@/components/job-workspace";
import { requireSession } from "@/lib/server-api";
export default async function JobsPage() { await requireSession(); return <JobLibrary />; }
