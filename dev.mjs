// Local dev in one command: `node dev.mjs` from the repo root. Backend (uvicorn, reloads, env from .env) on :8000
// and frontend (Vite, proxies /api to the backend) on :5173. Ctrl+C stops both; if one dies, the other is stopped.
import { spawn, spawnSync } from "node:child_process";
import { resolve } from "node:path";

const win = process.platform === "win32";
const python = resolve("backend", ".venv", win ? "Scripts/python.exe" : "bin/python");
const procs = [
  spawn(python, ["-m", "uvicorn", "app.main:app", "--reload", "--env-file", "../.env"], { cwd: "backend", stdio: "inherit" }),
  spawn(process.execPath, ["node_modules/vite/bin/vite.js"], { cwd: "frontend", stdio: "inherit" }),
];

// uvicorn --reload runs the server in a child process, so kill the whole tree (p.kill() on Windows leaves it behind)
const kill = (p) => (win ? spawnSync("taskkill", ["/PID", String(p.pid), "/T", "/F"]) : p.kill());
const stop = () => procs.forEach((p) => p.exitCode === null && kill(p));
procs.forEach((p) => p.on("exit", stop));
["SIGINT", "SIGTERM"].forEach((s) => process.on(s, stop));
