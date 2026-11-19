import { decide } from "@/lib/provider";

export async function POST(request: Request) {
  return decide(request, "deny");
}
