// Starts the JavaScript source stored in server.txt without renaming it.
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const path = require("node:path");

const sourcePath = path.join(__dirname, "server.txt");
if (!fs.existsSync(sourcePath)) {
  console.error("Missing server.txt");
  process.exit(1);
}

const child = spawn(process.execPath, ["--input-type=module"], {
  stdio: ["pipe", "inherit", "inherit"],
});
child.on("error", (err) => {
  console.error("Could not start server:", err);
  process.exit(1);
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
child.stdin.end(fs.readFileSync(sourcePath));
