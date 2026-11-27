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

# ---------------------------------------------------------------- image renderer
# Builds blitz/ (Blitz plus the patched crates in blitz/vendor) into the blitz binary, which draws most images in place of
# Chromium. It builds on the runner's own platform and cross-compiles for the target, since compiling Stylo under
# emulation takes hours.
# fontconfig is opened at run time rather than linked (blitz/Cargo.toml turns that on), so the cross build needs no
# target libraries: the bot image has fontconfig, with Playwright's CJK fonts for the characters the site's typefaces lack.
# Stylo's build script generates its property code with Python, so python3 must be there.
FROM --platform=$BUILDPLATFORM rust:1.98-bookworm AS blitz
ARG TARGETARCH
RUN command -v python3 >/dev/null || (apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*)
RUN case "$TARGETARCH" in \
      amd64) target=x86_64-unknown-linux-gnu; gnu=x86_64-linux-gnu ;; \
      arm64) target=aarch64-unknown-linux-gnu; gnu=aarch64-linux-gnu ;; \
      *) echo "no blitz build for $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && echo "$target" > /rust-target \
 && rustup target add "$target" \
 && if [ "$(uname -m)" != "${gnu%%-*}" ]; then \
      apt-get update && apt-get install -y --no-install-recommends "gcc-$(echo "$gnu" | tr _ -)" "libc6-dev-$TARGETARCH-cross" \
      && rm -rf /var/lib/apt/lists/* \
      && echo "$gnu-gcc" > /rust-linker; \
    fi
WORKDIR /src
COPY blitz/ ./
RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    target="$(cat /rust-target)" \
 && if [ -f /rust-linker ]; then export "CARGO_TARGET_$(echo "$target" | tr a-z- A-Z_)_LINKER=$(cat /rust-linker)"; fi \
 && cargo build --release --locked --target "$target" \
 && cp "target/$target/release/blitz" /usr/local/bin/blitz

# ---------------------------------------------------------------- bot
FROM python:3.12-slim-bookworm AS bot

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MAIMAI_WEBSERVER_HOST=0.0.0.0 \
    MAIMAI_WEBSERVER_PORT=8765 \
    MAIMAI_DATABASE_PATH=/app/data/maimai.sqlite3

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates ffmpeg \
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

# rasmai/images/render.py runs the binary RASMAI_RENDERER names; Chromium stays for the pages blitz cannot draw or fails on
COPY --from=blitz /usr/local/bin/blitz /usr/local/bin/blitz
ENV RASMAI_RENDERER=/usr/local/bin/blitz

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
# otoge/db.py and simai_bulk.py resolve against /app). They are made and owned
# here, before VOLUME, so a fresh named or anonymous volume copies this ownership. /app itself and
# the code stay root-owned and read-only to the bot.
RUN mkdir -p /app/data /app/otoge_cache /app/simai_cache /app/debug \
 && chown -R bot:bot /app/data /app/otoge_cache /app/simai_cache /app/debug

COPY rasmai/ ./rasmai/
# the images are set in the site's typefaces (rasmai/images/markup.py reads them from here)
COPY web/app/fonts/ ./web/app/fonts/
COPY brand/emoji/png/ ./brand/emoji/png/

VOLUME ["/app/data", "/app/otoge_cache", "/app/simai_cache", "/app/debug"]
EXPOSE 8765

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)" || exit 1

USER bot
CMD ["python", "-m", "rasmai"]
