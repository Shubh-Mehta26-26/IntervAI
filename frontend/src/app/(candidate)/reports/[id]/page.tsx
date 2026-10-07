import { ReportDetail } from "@/components/phase12-workspace";
import { requireSession } from "@/lib/server-api";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const session = await requireSession(); if (session.user.role !== "candidate") return <p>This workspace is for candidate accounts.</p>; const { id } = await params; return <ReportDetail id={id} />; }
