import { ProfileForm } from "@/components/profile-form";
import { getProfile, requireSession } from "@/lib/server-api";
export default async function ProfilePage() {
  const session = await requireSession();
  if (session.user.role !== "candidate") return null;
  return <ProfileForm initial={await getProfile()} />;
}
