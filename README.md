# InstaGhost: Instagram Username Finder Bot

A production-ready Telegram bot that continuously finds available Instagram usernames using AI generation and Playwright automation.

## Features
- **AI Generation**: Uses OpenRouter (Nemotron-3) for high-value username styles.
- **Stealth Check**: Playwright automation with rotating User-Agents and human-like delays.
- **Live Status**: Real-time updates on attempts, hits, and current target.
- **Auto-Cleanup**: Messages automatically delete to keep the chat clean.

## Commands
- `/ig`: Start the continuous search loop.
- `/stop`: Stop the search loop.

## Render Deployment Guide
1. **GitHub**: Create a new repository and upload `bot.py`, `requirements.txt`, `Procfile`, `runtime.txt`, and `README.md`.
2. **Render**:
   - Go to [render.com](https://render.com) and create a new **Web Service** (or Background Worker).
   - Connect your GitHub repository.
   - **Environment Variables**:
     - `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather.
     - `OPENROUTER_API_KEY`: Your API key from OpenRouter.
   - **Build Command**: `pip install -r requirements.txt && playwright install chromium`
   - **Start Command**: `python bot.py`
3. **Deploy**: Click deploy and wait for the bot to start.

## How it Works
1. The bot generates 20 usernames per batch using the OpenRouter AI.
2. It uses Playwright to navigate to the Instagram signup page.
3. It inputs each username and checks for the "Success" validation icon.
4. Available names are sent to Telegram and deleted after 2 minutes.
5. The process repeats indefinitely until stopped.
