/**
 * JSON that can ride in an HTTP header: every character past ASCII is written as its \uXXXX escape.
 *
 * A header value may hold only Latin-1, so a name with Japanese, full-width letters or an emoji in it made fetch throw before
 * anything was sent, and the dashboard told that one person the bot was unreachable on every page. The bot reads the header with
 * json.loads, which turns the escapes back into the real name.
 */
export function headerJson(value: unknown): string {
  return JSON.stringify(value).replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);
}
