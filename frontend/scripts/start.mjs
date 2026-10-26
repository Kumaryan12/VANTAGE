import { cpSync } from "node:fs";
import { spawn } from "node:child_process";

// Standalone output excludes static files; copy them for reproducible local startup.
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
const server = spawn(process.execPath, [".next/standalone/server.js"], {
  stdio: "inherit",
  env: { ...process.env, HOSTNAME: process.env.HOSTNAME || "127.0.0.1" },
});
for (const signal of ["SIGTERM", "SIGINT"])
  process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code || 0));
