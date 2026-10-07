import { CareerRoleDetail } from "@/components/career-workspace";
export default async function CareerRolePage({ params }: { params: Promise<{id:string}> }) { return <CareerRoleDetail identifier={(await params).id} />; }
