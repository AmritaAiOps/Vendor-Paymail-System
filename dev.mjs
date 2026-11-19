// Local dev in one command: `node dev.mjs` from the repo root. Backend (uvicorn, reloads, env from .env) on :8000
// and frontend (Vite, proxies /api to the backend) on :5173. Ctrl+C stops both; if one dies, the other is stopped.
// `node dev.mjs --fresh` first deletes the SQLite dev database and the history Excel file: a clean slate for testing.
import { spawn, spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { resolve } from "node:path";

const win = process.platform === "win32";
const python = resolve("backend", ".venv", win ? "Scripts/python.exe" : "bin/python");

// bring the dev database up to date first: a missing migration otherwise shows up as 500s on whatever page needs it
process.loadEnvFile(".env");
if (process.argv.includes("--fresh")) {
  const db = (process.env.DATABASE_URL ?? "sqlite:///./dev.db").match(/^sqlite:\/\/\/(.+)$/)?.[1];
  if (!db) throw new Error("--fresh only wipes a SQLite DATABASE_URL; refusing to touch " + process.env.DATABASE_URL);
  for (const f of [db, process.env.HISTORY_XLSX_PATH ?? "./data/email_history.xlsx"]) rmSync(resolve("backend", f), { force: true });
  console.log("--fresh: wiped the dev database and history file");
}
if (spawnSync(python, ["-m", "alembic", "upgrade", "head"], { cwd: "backend", stdio: "inherit" }).status !== 0) process.exit(1);

const procs = [
  spawn(python, ["-m", "uvicorn", "app.main:app", "--reload", "--env-file", "../.env"], { cwd: "backend", stdio: "inherit" }),
  spawn(process.execPath, ["node_modules/vite/bin/vite.js"], { cwd: "frontend", stdio: "inherit" }),
];

// uvicorn --reload runs the server in a child process, so kill the whole tree (p.kill() on Windows leaves it behind)
const kill = (p) => (win ? spawnSync("taskkill", ["/PID", String(p.pid), "/T", "/F"]) : p.kill());
const stop = () => procs.forEach((p) => p.exitCode === null && kill(p));
procs.forEach((p) => p.on("exit", stop));
["SIGINT", "SIGTERM"].forEach((s) => process.on(s, stop));
