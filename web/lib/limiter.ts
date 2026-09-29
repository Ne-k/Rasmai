const MAX_KEYS = 20000;

/** Sliding window per key: at most `limit` events in `windowSeconds`. In-process; the site runs as one server. */
export class RateLimiter {
  private events = new Map<string, number[]>();

  constructor(
    private limit: number,
    private windowSeconds: number,
  ) {}

  allow(key: string): boolean {
    const now = Date.now() / 1000;
    const recent = (this.events.get(key) ?? []).filter((t) => now - t < this.windowSeconds);
    if (recent.length >= this.limit) {
      this.events.set(key, recent);
      return false;
    }
    recent.push(now);
    this.events.set(key, recent);
    if (this.events.size > MAX_KEYS) {
      for (const [k, ts] of this.events) {
        if (!ts.length || now - ts[ts.length - 1] >= this.windowSeconds) this.events.delete(k);
        if (this.events.size <= MAX_KEYS / 2) break;
      }
    }
    return true;
  }
}

export const apiLimiter = new RateLimiter(240, 60); // dashboard and connect API calls per client
export const oauthLimiter = new RateLimiter(20, 600); // Discord sign-in callbacks per client
export const verifyLimiter = new RateLimiter(30, 600); // Turnstile checks per client
