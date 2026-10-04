# Visual Gifter demo

This project runs the visual demo from `server.txt`; the launcher feeds that file to Node as an ES module, so you do not need to rename it to `.mjs`.

## Deploy the web app on Render

1. Upload the files in this folder to a GitHub repository.
2. In Render, create **New → Blueprint** and select the repository (or create a Node Web Service).
3. Use a blank build command and start command `node launcher.cjs`.
4. Set `ADMIN_TOKEN` to a long random secret and keep it private. The Blueprint can generate one.
5. Deploy and open the service URL.

The server listens on Render's `PORT`. The displayed Robux/profile values are visual demo content only; they do not represent real Roblox currency or account changes. Do not collect Roblox passwords or authentication cookies.

The app currently stores configuration and keys under the operating system temp directory. Ephemeral hosting may erase them on restart/redeploy; use persistent storage or a database before relying on access control.

## Optional Telegram admin bot

Run the bot separately on a trusted host or as a background worker. Configure:
- `BOT_TOKEN`: token from BotFather
- `ADMIN_TOKEN`: same secret as the web service
- `SITE_URL`: deployed service URL
- `ADMIN_IDS`: comma-separated Telegram numeric IDs

Install with `pip install -r requirements.txt`, then run `python bot.py`.
