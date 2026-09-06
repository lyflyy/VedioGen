import { notFound } from "next/navigation";

import { AdminConsole } from "@/components/admin-console";

const sections = new Set(["model-providers", "credentials", "deployments", "routing", "playground", "invocations"]);

export default async function AdminSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!sections.has(section)) notFound();
  return <AdminConsole section={section} />;
}
