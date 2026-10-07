import { NewJob } from "@/components/job-workspace";
import { requireSession } from "@/lib/server-api";
export default async function NewJobPage() { await requireSession(); return <NewJob />; }
