# Contributing

PRs welcome. It's a small project so none of this is heavy.

## Getting set up

```bash
python dev.py setup
```

Makes the .venv, installs the Python and npm deps, grabs Chromium for playwright and writes you a starter `.env`. Put your `DISCORD_TOKEN` in it. If you want the site's sign-in working locally you also need `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` from the Developer Portal, with `http://localhost:3000/auth/callback` as a redirect.

```bash
python dev.py run
```

Starts the bot and the site together. `--bot-only` or `--web-only` if you only want one half. Site edits hot reload, the bot you restart yourself with `python dev.py bot`.

No Docker needed for any of this.

If you're changing anything about how charts get scored or picked, `python dev.py sample export.json` runs an exported account through the model and prints the profile, the picks and the traits. Quickest way to see if your change actually helped.

## Before you open a PR

```bash
python dev.py check
```

That's the verification sweep plus the site's type-check, the same two things CI runs. I'd rather you find it than the bot does.

The sweep is 58 checks and each one says in plain English what it's protecting, so a failure should tell you what broke without you having to go read the check itself. If you add something worth protecting, add a check for it.

CI also boots the bot with a fake token to make sure nothing explodes on import, and builds the site.

## Commits

Conventional commits, there's a bot that checks them:

```
feat(charts): read two more slide shapes out of the notes
fix(web): type the last two search boxes as text, like the other two
docs: reshoot the dashboard
```

If the subject doesn't explain itself, say why in the body. I write mine long, you don't have to.

## What I actually look at

Mostly whether it breaks something no check covers. Stuff that keeps coming up:

* if you add a route in `rasmai/web/dashboard/routes.py`, `return True` after you answer. Fall through and the server writes a second response on top of yours.
* no stray `print()` in anything that runs per request. It goes to the container logs in prod.
* if you change how a chart is measured or how a pick is scored, I check it against real account exports before it goes in, so expect me to ask for numbers.
* keep the UI snappy. If you move a filter to the server, keep the instant client-side one as a pre-filter so typing doesn't lag.

## Style

Look at the file you're editing and match it. Roughly: docstrings on anything public, comments say why and not what, a constant gets a line above it explaining what it's for. No banner headers at the top of files.

## Data and secrets

`.env`, `data/` and `debug/` are gitignored and they stay that way. `debug/` holds score exports from real accounts, so never commit one, and don't paste anyone's scores or Discord id into an issue or a PR.

## Licence

GPL-3.0. Contributing means you're fine with your changes going out under it.
