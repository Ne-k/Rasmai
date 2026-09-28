#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
EXPORTS="${EXPORTS:-$REPO/debug}"                  # debug exports to seed the test accounts from
OTOGE="${OTOGE:-$REPO/otoge_cache}"                # the song catalog; the running bot's folder is fine, it is only read
IMAGE="${IMAGE:-ghcr.io/ne-k/rasmai:latest}"       # the bot's own image, for its Python and packages; the code is this checkout's
K6_IMAGE="${K6_IMAGE:-grafana/k6:2.3.0}"
ACCOUNTS="${ACCOUNTS:-3000}"
RUNS="${RUNS:-1000:120s 3000:480s}"                # people:how long they stay; each run gets a fresh server
OUT="$REPO/k6/results-$(date +%Y%m%d-%H%M)"
NET=rasmai-k6-net
SERVER=rasmai-k6-server

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<EOF
Load-tests Rasmai's internal API on this machine: the code in $REPO, run in the bot's
image over a scratch database seeded from debug exports, with k6 in a container beside it.
Nothing opens data/ or talks to the running bot; what it shares with production is the CPU.

  EXPORTS=folder of debug/*.json   (default $REPO/debug)
  OTOGE=otoge_cache folder         (default $REPO/otoge_cache)
  RUNS="1000:120s 3000:480s"       people:hold for each run
  ACCOUNTS=3000                    test accounts seeded
Results go to k6/results-<date>/, and a summary to paste back is printed at the end.
EOF
  exit 0
fi

[ -f "$OTOGE/songs_cache.pkl" ] || { echo "no songs_cache.pkl in $OTOGE: set OTOGE to the bot's otoge_cache folder"; exit 1; }
ls "$EXPORTS"/*.json >/dev/null 2>&1 || { echo "no exports in $EXPORTS: copy debug/*.json there from the dev machine"; exit 1; }
command -v docker >/dev/null || { echo "docker is not on PATH"; exit 1; }

mkdir -p "$OUT"
docker network create "$NET" >/dev/null 2>&1 || true
cleanup() {
  [ -n "${SAMPLER:-}" ] && kill "$SAMPLER" 2>/dev/null || true
  docker rm -f "$SERVER" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

{
  echo "machine: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m), $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
  echo "docker: $(docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes, {{.OperatingSystem}}')"
  echo "code: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null) $(git -C "$REPO" status --short 2>/dev/null | wc -l | tr -d ' ') files changed"
  echo "running beside it: $(docker ps --format '{{.Names}}' | grep -v "$SERVER" | tr '\n' ' ')"
} > "$OUT/machine.txt"
cat "$OUT/machine.txt"

for run in $RUNS; do
  crowd=${run%%:*}; hold=${run#*:}; label="crowd$crowd"
  echo "== $label: seeding $ACCOUNTS accounts"
  docker rm -f "$SERVER" >/dev/null 2>&1 || true
  # only the code, the test's own files, the exports and the catalog go in, all read-only; the
  # scratch database lives in the container's /tmp and goes with it
  docker run -d --name "$SERVER" --network "$NET" --ulimit nofile=65536:65536 \
    -v "$REPO/rasmai":/src/rasmai:ro -v "$REPO/k6":/src/k6:ro \
    -v "$EXPORTS":/exports:ro -v "$OTOGE":/src/otoge_cache:ro -v "$OUT":/results \
    -w /src --entrypoint python "$IMAGE" \
    k6/serve_local.py --host 0.0.0.0 --users "$ACCOUNTS" --exports /exports --out /results/users.json >/dev/null
  until docker logs "$SERVER" 2>&1 | grep -q "internal API on"; do
    if [ -z "$(docker ps -q -f name=^/$SERVER$)" ]; then docker logs "$SERVER" 2>&1 | tail -20; exit 1; fi
    sleep 2
  done
  docker logs "$SERVER" 2>&1 | grep "seeded" | tee "$OUT/$label-seed.txt"
  docker exec "$SERVER" sh -c 'ls -l /tmp/rasmai-k6.sqlite3 | awk "{print \"scratch database\", \$5, \"bytes\"}"' | tee -a "$OUT/$label-seed.txt"

  ( while docker exec "$SERVER" true 2>/dev/null; do
      echo "$(date +%T) $(docker exec "$SERVER" sh -c 'grep -E "^(VmRSS|Threads):" /proc/1/status' | tr -s ' \t\n' ' ') cpu $(docker stats --no-stream --format '{{.CPUPerc}}' "$SERVER")"
      sleep 5
    done ) > "$OUT/$label-server.log" 2>/dev/null &
  SAMPLER=$!

  echo "== $label: $crowd people for $hold (about $(( ${hold%s} / 60 + 4 )) minutes)"
  docker run --rm --network "$NET" --ulimit nofile=65536:65536 --user "$(id -u):$(id -g)" \
    -v "$REPO/k6":/src/k6:ro -v "$OUT":/results \
    -e RASMAI_K6_USERS=/results/users.json -e RASMAI_K6_BASE="http://$SERVER:18765" \
    -e SCENARIO=crowd,probe -e RASMAI_K6_CROWD="$crowd" -e RASMAI_K6_HOLD="$hold" -e RASMAI_K6_WARM=8 \
    "$K6_IMAGE" run --quiet --summary-export "/results/$label-summary.json" /src/k6/dashboard.js \
    > "$OUT/$label-k6.txt" 2>&1 || true      # k6 exits non-zero when a threshold is crossed; the numbers are still wanted

  kill "$SAMPLER" 2>/dev/null || true; SAMPLER=
  docker logs "$SERVER" 2>&1 | grep -iE "error|exception|traceback" | sort | uniq -c | sort -rn | head -20 > "$OUT/$label-server-errors.txt" || true
  docker rm -f "$SERVER" >/dev/null
done

echo
echo "================ paste everything below this line back ================"
cat "$OUT/machine.txt"
for f in "$OUT"/*-k6.txt; do
  label=$(basename "$f" -k6.txt)
  echo
  echo "== $label"
  cat "$OUT/$label-seed.txt"
  grep -v "level=warning" "$f" | grep -E "http_req_failed|visit_page_ready|first:|http_reqs|name:probe|crowd [a-z]+ 200|probe 200|%" || true
  echo "failures by kind:"
  grep "level=warning" "$f" | grep -oE "(connection refused|request timeout|reset by peer|EOF|cannot assign|too many open|i/o timeout)" | sort | uniq -c || true
  awk '{for (i = 1; i < NF; i++) { if ($i == "VmRSS:" && $(i+1) + 0 > r) r = $(i+1); if ($i == "Threads:" && $(i+1) + 0 > t) t = $(i+1) }}
       END {printf "server: peak %.0f MB, most threads %d\n", r / 1024, t}' "$OUT/$label-server.log"
  echo "server errors (count, line):"; head -5 "$OUT/$label-server-errors.txt"
done
echo "======================================================================="
echo "full results: $OUT"
