# Rasmai status page

A public page for Vercel: whether the bot is up now, 90 days of uptime per part, and the last day's response time. It holds no data of its own; it reads Rasmai's protected `/api/statuspage` endpoints and shows what they say.

## Set up

1. In Rasmai's `.env`, set `STATUSPAGE_TOKEN` to a long random string (`openssl rand -hex 32`) and restart the bot and website.
2. In Vercel, import this repository and set the project's **Root Directory** to `status`.
3. Add two environment variables to the Vercel project:
   - `RASMAI_URL`: the public address of the site, for example `https://rasmai.lol`
   - `RASMAI_STATUS_TOKEN`: the same value as `STATUSPAGE_TOKEN`
4. Deploy. Add a domain such as `status.rasmai.lol` under the project's Domains.

Try it locally with `npm install`, copy `.env.example` to `.env.local`, then `npm run dev`.

## How it works

- The bot records a reading of each part every 5 minutes into its own database and serves 90 days of them. A gap counts as down.
- The page asks Rasmai at most twice a minute per server instance. A failed read is shown as a failure, never replaced by an older good one.
- If the bot's website answers but the bot does not, the banner says Rasmai is down. If the website does not answer either, it says Rasmai isn't answering and hides the history.
- The history lives on the machine the bot runs on. If that machine is off, the page says so, and the days it was off show as down once it is back.
