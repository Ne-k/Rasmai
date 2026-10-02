import { authorizeUrl } from "@/lib/discord";
import { oauthReady } from "@/lib/env";
import { startSignIn } from "@/lib/signin";

const start = (request: Request) => startSignIn(request, "discord", oauthReady(), (flow) => authorizeUrl(flow.state));

export const GET = start;
export const POST = start;
