const FORM = { "Content-Type": "application/x-www-form-urlencoded" };

/** A form POST when `form` is given, otherwise a GET with the bearer token; the parsed JSON answer, or an error naming `what`. */
export async function oauthJson<T>(url: string, what: string, { form, bearer }: { form?: Record<string, string>; bearer?: string }): Promise<T> {
  const response = await fetch(url, {
    method: form ? "POST" : "GET",
    headers: form ? FORM : { Authorization: `Bearer ${bearer}` },
    body: form && new URLSearchParams(form),
    signal: AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`${what} failed: ${response.status}`);
  return (await response.json()) as T;
}

/** The token has done its job: revoking it keeps nothing dangling on the provider's side, and a failure changes nothing. */
export function revoke(url: string, form: Record<string, string>): void {
  fetch(url, { method: "POST", headers: FORM, body: new URLSearchParams(form), signal: AbortSignal.timeout(10000) }).catch(() => undefined);
}
