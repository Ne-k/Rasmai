import http from "k6/http";
import exec from "k6/execution";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";
import { SharedArray } from "k6/data";

const visitReady = new Trend("visit_page_ready", true);

// What k6/serve_local.py wrote: the seeded user ids, the base address, and this run's secret.
// The ids are read once and shared: each VU holding its own copy of three thousand of them, and the
// bodies of everything it was sent, was what ran k6 out of memory at three thousand people.
const USERS = new SharedArray("users", () => JSON.parse(open(__ENV.RASMAI_K6_USERS)).users);
const { secret: SECRET, base } = JSON.parse(open(__ENV.RASMAI_K6_USERS));
const BASE = __ENV.RASMAI_K6_BASE || base;
const WARM = Number(__ENV.RASMAI_K6_WARM || 8);   // the first WARM users are touched in setup, the rest are left cold

// The dashboard's reads, weighted roughly the way a page load asks for them. /areas, /video and
// /play are left out on purpose: each reaches a site that is not ours, or needs a live maimai session.
const READS = [
  ["overview", "/internal/me", 3],
  ["picks", "/internal/me/picks", 2],
  ["charts", "/internal/me/charts", 2],
  ["new", "/internal/me/new", 1],
  ["search", "/internal/me/search?q=oshama", 1],
  ["titles", "/internal/me/titles?q=pand", 1],
];
const WEIGHTED = READS.flatMap(([name, path, weight]) => Array(weight).fill([name, path]));

function headers(user) {
  return {
    "X-Rasmai-Internal": SECRET,
    "X-Rasmai-User": JSON.stringify({ id: user, name: "k6", handle: "k6" }),
    "Accept-Encoding": "gzip",
  };
}

function read(name, path, user) {
  const res = http.get(`${BASE}${path}`, { headers: headers(user), tags: { name }, timeout: "120s" });
  check(res, { [`${name} 200`]: (r) => r.status === 200 });
  return res;
}

const SCENARIOS = {
  // cached analyses: how many requests a second the server gives the dashboard, and where it bends
  warm: {
    executor: "ramping-vus",
    exec: "warm",
    startVUs: 1,
    stages: [
      { duration: "20s", target: 10 },
      { duration: "30s", target: 25 },
      { duration: "30s", target: 50 },
      { duration: "20s", target: 50 },
      { duration: "10s", target: 0 },
    ],
  },
  // the dashboard's first request on its own, cached, at a steady load: the A/B scenario
  overview: {
    executor: "constant-vus",
    exec: "overviewOnly",
    vus: 20,
    duration: "25s",
  },
  // a new person opening the dashboard as a browser does: six requests at once, none cached yet
  visit: {
    executor: "ramping-arrival-rate",
    exec: "visit",
    startRate: 1,
    timeUnit: "1s",
    preAllocatedVUs: 20,
    maxVUs: 120,
    stages: [
      { duration: "10s", target: 1 },
      { duration: "20s", target: 2 },
      { duration: "20s", target: 4 },
    ],
  },
  // somebody whose analysis is already cached, loading their dashboard all through a burst of new
  // visitors: whether the people already here are held up by the people arriving
  probe: {
    executor: "constant-vus",
    exec: "probe",
    vus: 2,
    duration: "50s",
  },
  // first touches: every iteration is somebody opening their dashboard for the first time, so each
  // one builds a whole analysis. The arrival rate climbs until the server cannot keep up.
  cold: {
    executor: "ramping-arrival-rate",
    exec: "cold",
    startRate: 1,
    timeUnit: "1s",
    preAllocatedVUs: 20,
    maxVUs: 120,
    // sized to the 300 accounts serve_local.py seeds by default: about 195 first touches in all
    stages: [
      { duration: "10s", target: 2 },
      { duration: "20s", target: 4 },
      { duration: "20s", target: 8 },
    ],
  },
};

const CROWD = Number(__ENV.RASMAI_K6_CROWD || 1000);

// thousands of people on the site: each VU is one person with their own account, opening the
// dashboard, reading it for a while, and opening it again. Their first open is cold, so this is
// also what happens when a crowd arrives faster than analyses can be built.
SCENARIOS.crowd = {
  executor: "ramping-vus",
  exec: "crowd",
  startVUs: 0,
  stages: [
    { duration: "60s", target: CROWD },
    { duration: __ENV.RASMAI_K6_HOLD || "120s", target: CROWD },
    { duration: "20s", target: 0 },
  ],
  gracefulRampDown: "130s",
};

const chosen = (__ENV.SCENARIO || "warm").split(",");

export const options = {
  scenarios: Object.fromEntries(chosen.map((key) => [key, SCENARIOS[key]])),
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
  discardResponseBodies: true,     // only statuses and headers are read
  thresholds: {
    http_req_failed: ["rate<0.01"],
    // one sub-metric each, so the summary prints every endpoint's own percentiles
    ...Object.fromEntries(READS.map(([name]) => [`http_req_duration{name:${name}}`, ["p(95)<60000"]])),
    "http_req_duration{name:probe}": ["p(95)<60000"],
    "visit_page_ready{first:true}": ["p(95)<60000"],
    "visit_page_ready{first:false}": ["p(95)<60000"],
  },
};

export function setup() {
  // warm the cache for the users the warm scenario reads, so it measures cached reads only
  for (const user of USERS.slice(0, WARM)) read("overview", "/internal/me", user);
}

export function warm() {
  const user = USERS[Math.floor(Math.random() * Math.min(WARM, USERS.length))];
  const [name, path] = WEIGHTED[Math.floor(Math.random() * WEIGHTED.length)];
  read(name, path, user);
}

export function overviewOnly() {
  read("overview", "/internal/me", USERS[Math.floor(Math.random() * Math.min(WARM, USERS.length))]);
}

export function probe() {
  read("probe", "/internal/me", USERS[Math.floor(Math.random() * Math.min(WARM, USERS.length))]);
}

export function visit() {
  const index = WARM + exec.scenario.iterationInTest;
  if (index >= USERS.length) exec.test.abort(`ran out of cold users at ${index}; seed more with --users`);
  const user = USERS[index];
  const page = READS.map(([name, path]) => ["GET", `${BASE}${path}`, null,
    { headers: headers(user), tags: { name: `visit-${name}` }, timeout: "120s" }]);
  const answers = http.batch(page);
  answers.forEach((res, i) => check(res, { [`visit ${READS[i][0]} 200`]: (r) => r.status === 200 }));
  // the page is ready when its slowest part is
  visitReady.add(Math.max(...answers.map((r) => r.timings.duration)));
}

// a 503 that says "building" is the bot asking the page to come back, not a failure
const BUILDING_OK = http.expectedStatuses(200, 503);
const building = (r) => r.status === 503 && Boolean(r.headers["Retry-After"]);

export function crowd() {
  const user = USERS[(exec.vu.idInTest - 1) % USERS.length];
  const started = Date.now();
  let todo = READS.map((read, i) => i);
  const final = [];
  // as the page's getJSON does: ask again, after the time the bot gave, for whatever is still building
  for (let round = 0; todo.length && round < 40; round++) {
    const answers = http.batch(todo.map((i) => ["GET", `${BASE}${READS[i][1]}`, null,
      { headers: headers(user), tags: { name: `crowd-${READS[i][0]}` }, timeout: "120s", responseCallback: BUILDING_OK }]));
    const again = [];
    let wait = 0;
    answers.forEach((res, k) => {
      if (building(res)) {
        again.push(todo[k]);
        wait = Math.max(wait, Number(res.headers["Retry-After"]) || 3);
      } else {
        final[todo[k]] = res;
      }
    });
    todo = again;
    if (todo.length) sleep(wait);
  }
  READS.forEach(([name], i) => check(final[i] || { status: 0 }, { [`crowd ${name} 200`]: (r) => r.status === 200 }));
  visitReady.add(Date.now() - started, { first: String(exec.vu.iterationInScenario === 0) });
  sleep(10 + Math.random() * 20);    // reading the page before opening it again
}

export function cold() {
  // a user nobody has asked for yet, taken in order and never reused
  const index = WARM + exec.scenario.iterationInTest;
  if (index >= USERS.length) {
    exec.test.abort(`ran out of cold users at ${index}; seed more with --users`);
  }
  read("overview", "/internal/me", USERS[index]);
}
