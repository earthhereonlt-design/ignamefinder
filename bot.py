import os
import asyncio
import random
import time
import json
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# --- Health Check Server ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_health_check():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check server running on port {port}")
    server.serve_forever()

# --- Configuration & Environment Variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1"
]

# --- Global State ---
class BotState:
    def __init__(self):
        self.is_running = False
        self.attempts = 0
        self.available = 0
        self.taken = 0
        self.current_username = ""
        self.status_message_id = None
        self.chat_id = None
        self.loop_task = None

state = BotState()

# --- AI Username Generation ---
async def generate_usernames():
    prompt = """Generate 20 unique Instagram usernames in three styles:
1. TECH STYLE (ONLY for the name 'Aadi'): e.g., aadi.js, aadi.dev, aadi.node
2. NATURE STYLE: e.g., river.slow, forest.lost, sky.idle
3. SARCASTIC STYLE: e.g., too.lazy, barely.awake, just.existing (Max 12 chars)

Rules:
- Usernames must be readable.
- Avoid random strings.
- Avoid duplicates.
- Return ONLY a JSON list of strings.
"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "nvidia/nemotron-3-super:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        # Extract JSON list
        start = content.find("[")
        end = content.rfind("]") + 1
        return json.loads(content[start:end])
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return []

# --- Instagram Availability Check ---
async def check_instagram_availability(browser, username):
    context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
    page = await context.new_page()
    
    # Resource blocking to speed up
    await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
    
    try:
        await page.goto("https://www.instagram.com/accounts/emailsignup/", wait_until="networkidle", timeout=30000)
        
        # Wait for the username input
        username_input = await page.wait_for_selector('input[name="username"]', timeout=10000)
        await username_input.fill(username)
        
        # Trigger validation (click elsewhere or press tab)
        await page.keyboard.press("Tab")
        
        # Wait for the validation icon or error message
        # Instagram shows a green checkmark (Success) or a red X (Error)
        # We check for the presence of the success icon
        await asyncio.sleep(2) # Wait for async validation
        
        is_available = await page.evaluate("""() => {
            const success = document.querySelector('span[aria-label="Success"]');
            const error = document.querySelector('span[aria-label="Error"]');
            if (success) return true;
            if (error) return false;
            return null;
        }""")
        
        await context.close()
        return is_available
    except Exception as e:
        print(f"Check Error for {username}: {e}")
        await context.close()
        return None

# --- Message Management ---
async def send_and_delete(context, chat_id, text, delay):
    msg = await context.bot.send_message(chat_id=chat_id, text=text)
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except:
        pass

async def update_status(context):
    status_text = f"""
Searching usernames...

Attempts: {state.attempts}
Available: {state.available}
Taken: {state.taken}
Current username: {state.current_username}
"""
    try:
        if state.status_message_id:
            await context.bot.edit_message_text(
                chat_id=state.chat_id,
                message_id=state.status_message_id,
                text=status_text
            )
        else:
            msg = await context.bot.send_message(chat_id=state.chat_id, text=status_text)
            state.status_message_id = msg.message_id
    except Exception as e:
        print(f"Status Update Error: {e}")

# --- Main Loop ---
async def search_loop(context):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        while state.is_running:
            try:
                usernames = await generate_usernames()
                if not usernames:
                    await send_and_delete(context, state.chat_id, "⚠️ AI failed to generate names. Retrying...", 10)
                    continue
                
                for username in usernames:
                    if not state.is_running: break
                    
                    state.current_username = username
                    state.attempts += 1
                    await update_status(context)
                    
                    is_available = await check_instagram_availability(browser, username)
                    
                    if is_available is True:
                        state.available += 1
                        await context.bot.send_message(
                            chat_id=state.chat_id,
                            text=f"AVAILABLE USERNAME FOUND\n\n{username}"
                        )
                        # Auto delete after 2 mins (handled by a separate task or just ignored if it's a "found" message)
                        asyncio.create_task(delete_after_delay(context, state.chat_id, username, 120))
                    elif is_available is False:
                        state.taken += 1
                    else:
                        # Error or uncertain
                        error_msg = f"⚠️ Error checking @{username}. Restarting process..."
                        await send_and_delete(context, state.chat_id, error_msg, 10)
                    
                    # Anti-block delay
                    await asyncio.sleep(random.uniform(1.5, 4.0))
                    
            except Exception as e:
                error_msg = f"❌ Fatal Error: {e}. Restarting..."
                await send_and_delete(context, state.chat_id, error_msg, 10)
                await asyncio.sleep(5)
        
        await browser.close()

async def delete_after_delay(context, chat_id, username, delay):
    # This is a bit tricky since we need the message_id. 
    # For simplicity, we'll just send the message and delete it here.
    msg = await context.bot.send_message(chat_id=chat_id, text=f"AVAILABLE USERNAME FOUND\n\n{username}")
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except:
        pass

# --- Bot Commands ---
async def start_ig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.is_running:
        await update.message.reply_text("Bot is already running!")
        return
    
    state.is_running = True
    state.chat_id = update.effective_chat.id
    state.attempts = 0
    state.available = 0
    state.taken = 0
    state.status_message_id = None
    
    await update.message.reply_text("🚀 Starting Instagram Username Finder...")
    state.loop_task = asyncio.create_task(search_loop(context))

async def stop_ig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state.is_running:
        await update.message.reply_text("Bot is not running!")
        return
    
    state.is_running = False
    if state.loop_task:
        state.loop_task.cancel()
    
    await update.message.reply_text("🛑 Stopping Instagram Username Finder...")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found.")
        exit(1)
    
    # Start health check server in a background thread
    threading.Thread(target=run_health_check, daemon=True).start()
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("ig", start_ig))
    application.add_handler(CommandHandler("stop", stop_ig))
    
    print("Bot is starting...")
    application.run_polling()
