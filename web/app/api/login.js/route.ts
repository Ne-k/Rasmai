import { NextResponse } from "next/server";
import { env } from "@/lib/env";

/** What a connect bookmark saved before SEGA hid the gateway's sign-in from scripts does now: says so, and opens the connect page the link named. */
function script(baseUrl: string): string {
  return `!function(d){const BASE_URL=${JSON.stringify(baseUrl)};const p=new URLSearchParams(d.location.hash.substring(1));const code=p.get('code');const user=p.get('user');alert('This bookmark no longer works: SEGA changed the gateway so no bookmark can read the sign-in. Rasmai links another way now; the connect page shows the steps.');if(code&&user&&/^[A-Za-z0-9_-]{20,64}$/.test(code)){d.location.href=BASE_URL+'/connect/?code='+encodeURIComponent(code)+'&user='+encodeURIComponent(user);}else{d.location.href=BASE_URL+'/link/';}}(document);`;
}

export async function GET() {
  return new NextResponse(script(env.publicUrl()), {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      // still loaded by the old bookmark on lng-tgk-aime-gw.am-all.net
      "Cross-Origin-Resource-Policy": "cross-origin",
    },
  });
}
