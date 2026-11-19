import { Application } from "./Application";

export default async function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  return <Application id={(await params).id} />;
}
