import { NextResponse } from "next/server";
import { env } from "@/lib/env";

/** The bookmarklet body. It runs on SEGA's gateway page, reads the session cookie there and posts it back here. */
function script(baseUrl: string): string {
  return `!function(d){const BASE_URL=${JSON.stringify(baseUrl)};if(d.location.host!=='lng-tgk-aime-gw.am-all.net'){alert('Please run this on the maimai Aime gateway page.');return;}function post(path,params){const form=d.createElement('form');form.method='POST';form.action=path;for(const key in params){if(Object.prototype.hasOwnProperty.call(params,key)){const hiddenField=d.createElement('input');hiddenField.type='hidden';hiddenField.name=key;hiddenField.value=params[key];form.appendChild(hiddenField);}}d.body.appendChild(form);form.submit();}const params=new URLSearchParams(d.location.hash.substring(1));const code=params.get('code');const user=params.get('user');const region=params.get('region')||'intl';if(region!=='intl'){alert('Rasmai can only link International maimai accounts for now. Japan and China accounts sign in somewhere else, so this page cannot hand their login over.');return;}if(!code||!/^[A-Za-z0-9_-]{20,64}$/.test(code)){alert('Missing or invalid login code. Please restart the login flow.');return;}if(!user){alert('Missing user identifier. Please restart the login flow.');return;}const cookieMap=Object.fromEntries(d.cookie.split(';').map(function(c){const idx=c.indexOf('=');const name=idx===-1?c.trim():c.slice(0,idx).trim();const value=idx===-1?'':c.slice(idx+1);return [name,value];}));const clal=cookieMap.clal;if(!clal||clal.trim().length!==64){alert("Couldn't retrieve login data. Sign out of this page, sign in again, then press the bookmark. If your account is from the Japanese or Chinese version of maimai DX, it can't be linked yet: only International accounts sign in here.");return;}post(BASE_URL+'/api/login',{code,user,token:clal.trim(),region});}(document);`;
}

export async function GET() {
  return new NextResponse(script(env.publicUrl()), {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      // loaded by the bookmarklet on lng-tgk-aime-gw.am-all.net
      "Cross-Origin-Resource-Policy": "cross-origin",
    },
  });
}
