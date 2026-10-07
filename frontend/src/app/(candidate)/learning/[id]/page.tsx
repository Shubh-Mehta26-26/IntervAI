import { LearningDetail } from "@/components/learning-workspace";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { return <LearningDetail identifier={(await params).id} />; }
