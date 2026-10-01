import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";

// the project key stays out of the repo: it comes from the environment, or a web/.env.local
if (existsSync(".env.local")) process.loadEnvFile(".env.local");
const apiKey = process.env.SIMPLELOCALIZED_PROJECT_API_KEY ?? process.env.SIMPLELOCALIZE_API_KEY;
if (!apiKey) {
  console.error("Set SIMPLELOCALIZED_PROJECT_API_KEY (SimpleLocalize > Settings > Credentials) in the environment or web/.env.local.");
  process.exit(1);
}

const [command = "download", ...rest] = process.argv.slice(2);
const run = spawnSync("simplelocalize", [command, "--apiKey", apiKey, ...rest], { stdio: "inherit", shell: true });
process.exit(run.status ?? 1);
