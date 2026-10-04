"""Run the web server and Telegram bot in one Render service."""
import os
import signal
import subprocess
import sys
import time

processes = []

def stop_all(*_):
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 8
    for proc in processes:
        if proc.poll() is None:
            try:
                proc.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                proc.kill()
    sys.exit(0)

signal.signal(signal.SIGTERM, stop_all)
signal.signal(signal.SIGINT, stop_all)

# Start the HTTP server first, then the Telegram polling bot.
processes.append(subprocess.Popen(["node", "launcher.cjs"]))
time.sleep(1)
if processes[0].poll() is not None:
    raise SystemExit("Web server exited during startup")
processes.append(subprocess.Popen([sys.executable, "bot.py"]))

while True:
    for proc in processes:
        code = proc.poll()
        if code is not None:
            print(f"Child process exited with code {code}; stopping service", flush=True)
            stop_all()
    time.sleep(1)
