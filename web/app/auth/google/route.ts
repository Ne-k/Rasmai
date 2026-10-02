import { googleReady } from "@/lib/env";
import { authorizeUrl } from "@/lib/google";
import { startSignIn } from "@/lib/signin";

const start = (request: Request) => startSignIn(request, "google", googleReady(), authorizeUrl);

export const GET = start;
export const POST = start;
