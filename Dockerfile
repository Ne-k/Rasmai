# syntax=docker/dockerfile:1.7
#
# Two images from one file:
#   --target web   the website: Next.js server, public, talks to the bot over the compose network
#   --target bot   the Discord bot with its internal API, Chromium and the chart database

# ---------------------------------------------------------------- website
# The Next.js build runs once on the runner's own platform: its compiler crashes under
# emulation, and the standalone output it produces is plain JavaScript that runs anywhere.
FROM --platform=$BUILDPLATFORM node:22-alpine AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --no-audit --no-fund
COPY web/ ./
RUN --mount=type=cache,target=/web/.next/cache,sharing=locked \
    npm run build

FROM node:22-alpine AS web
WORKDIR /web
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=webbuild /web/.next/standalone ./
COPY --from=webbuild /web/.next/static ./.next/static
COPY --from=webbuild /web/public ./public
EXPOSE 3000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/health >/dev/null || exit 1
USER node
CMD ["node", "server.js"]

# ---------------------------------------------------------------- bot
FROM python:3.12-slim-bookworm AS bot

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MAIMAI_WEBSERVER_HOST=0.0.0.0 \
    MAIMAI_WEBSERVER_PORT=8765 \
    MAIMAI_DATABASE_PATH=/app/data/maimai.sqlite3 \
    HF_HOME=/app/models

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Chromium and its system libraries get their own layer, keyed only on the
# Playwright version, so editing requirements.txt never re-downloads them. Keep it the same as the
# pin there.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install "playwright==1.60.0" \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -r requirements.txt

# The decision model behind the "laya" beta, off unless asked for: torch is 454 MB on linux/arm64
# and the checkpoint another 808 MB, and a bot nobody will switch the feature on for should carry
# neither. Built without it the beta picker says so, rather than offering a switch that does
# nothing. Build with:  docker build --target bot --build-arg WITH_LAYA=1 .
ARG WITH_LAYA=0
COPY requirements-laya.txt .
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ "$WITH_LAYA" = "1" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch \
   && pip install -r requirements-laya.txt; \
    fi

# The bot and the headless Chromium it drives (launched with --no-sandbox, see images/render.py) run
# as this user rather than root, so a renderer exploit lands in an account that can write the data
# folders and nothing else. The ids are build args because a bind mount on a Linux host keeps the
# host's numbers: build with the ids that own ./data, or chown those folders to these.
ARG BOT_UID=1000
ARG BOT_GID=1000
RUN groupadd --gid "$BOT_GID" bot \
 && useradd --uid "$BOT_UID" --gid "$BOT_GID" --create-home --home-dir /home/bot --shell /usr/sbin/nologin bot \
 && git config --system --add safe.directory /app/otoge_cache/repo \
 && git config --system --add safe.directory /app/simai_cache/repo
ENV HOME=/home/bot

# Everything the process writes at run time lives in these folders (the relative paths in config.py,
# otoge/db.py and simai_bulk.py resolve against /app; HF_HOME is models). They are made and owned
# here, before VOLUME, so a fresh named or anonymous volume copies this ownership. /app itself and
# the code stay root-owned and read-only to the bot.
RUN mkdir -p /app/data /app/otoge_cache /app/models /app/simai_cache /app/debug \
 && chown -R bot:bot /app/data /app/otoge_cache /app/models /app/simai_cache /app/debug

COPY rasmai/ ./rasmai/
COPY brand/emoji/png/ ./brand/emoji/png/
# the linking walkthroughs, so /login can play one in Discord rather than sending people away
COPY web/public/walkthrough/ ./walkthrough/

VOLUME ["/app/data", "/app/otoge_cache", "/app/models", "/app/simai_cache", "/app/debug"]
EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)" || exit 1

USER bot
CMD ["python", "-m", "rasmai"]
