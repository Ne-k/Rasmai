import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

// the project key stays out of the repo: it comes from the environment, the repo's .env, or a web/.env.local.
// Only that one line is read, so nothing else in those files reaches the CLI.
const NAME = "SIMPLELOCALIZED_PROJECT_API_KEY";
const fromFile = (file) =>
  existsSync(file) ? readFileSync(file, "utf8").match(new RegExp(`^\\s*${NAME}\\s*=\\s*(.+?)\\s*$`, "m"))?.[1]?.replace(/^["']|["']$/g, "") : undefined;

const apiKey = process.env[NAME] ?? fromFile("../.env") ?? fromFile(".env.local");
if (!apiKey) {
  console.error(`Set ${NAME} (SimpleLocalize > Settings > Credentials) in the environment, the repo's .env, or web/.env.local.`);
  process.exit(1);
}

const [command = "download", ...rest] = process.argv.slice(2);
const run = spawnSync("simplelocalize", [command, "--apiKey", apiKey, ...rest], { stdio: "inherit", shell: true });
process.exit(run.status ?? 1);
