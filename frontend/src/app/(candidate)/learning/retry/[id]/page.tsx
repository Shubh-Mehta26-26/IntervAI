import { LearningAttemptRoom } from "@/components/learning-workspace";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { return <LearningAttemptRoom identifier={(await params).id} retry />; }
