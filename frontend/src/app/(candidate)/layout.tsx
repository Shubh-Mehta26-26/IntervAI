import { AppShell } from "@/components/app-shell";
import { requireSession } from "@/lib/server-api";
export const dynamic = "force-dynamic";
export default async function CandidateLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  return <AppShell user={session.user}>{children}</AppShell>;
}
