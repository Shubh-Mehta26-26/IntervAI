import { KnowledgeGapDetail } from "@/components/memory-workspace";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <KnowledgeGapDetail identifier={id} />;
}
