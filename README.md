# Visual Gifter demo — one Render service

This repository runs the Node web server and Telegram bot together in **one Docker-based Render Web Service**. `server.txt` remains a plain text file; `launcher.cjs` feeds it to Node as an ES module.

## Render setup

1. Push the repository contents to GitHub, including `Dockerfile`, `start.py`, `launcher.cjs`, and `server.txt`.
2. In Render, create one **Web Service** from the repository and choose **Docker** (or deploy using the included `render.yaml`).
3. Set these environment variables in that same service:
   - `BOT_TOKEN`: Telegram bot token from BotFather.
   - `ADMIN_TOKEN`: keep the generated value; use the same value for the site and bot.
   - `SITE_URL`: the public `https://...onrender.com` URL of this service.
   - `ADMIN_IDS`: optional comma-separated Telegram numeric user IDs for admins.
4. Deploy. Render builds the Dockerfile and starts both processes with `python3 start.py`. No separate bot service is needed.

The server listens on Render's `PORT`. The supervisor stops the whole service if either child process exits. Keep tokens private; never commit them to GitHub. This project should be used only as a clearly disclosed demo and must not collect Roblox passwords or session cookies.
