import os
import asyncio
import random
import time
import json
import requests
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
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
    prompt = """Generate 30 unique Instagram usernames in exactly these three styles:

1. AADI + TECH (Clean dev style):
Examples: aadi.js, aadi.py, aadi.dev, aadi.sys, aadi.root, aadi.stack, aadi.node, aadi.core, aadi.code, aadi.logic, aadi.grid, aadi.proto, aadi.kernel, aadi.debug, aadi.cloud, aadi.build, aadi.script, aadi.deploy, aadi.server, aadi.engine.

2. NATURE (No "aadi"):
Examples: earth.drift, river.slow, sky.idle, ocean.calm, forest.deep, storm.low, cloud.soft, tide.low, wind.silent, rain.light, mist.fade, fog.grey, stone.cold, sand.soft, leaf.fall, wood.dark, sun.dim, moon.faded, wave.gentle, stream.slow.

3. SARCASTIC (Short, 10–12 chars, no dots):
Examples: notfineok, whateverok, idkbro, noideaman, whymepls, notagainok, okfinebro, surewhyok, sameoldbro, verycoolok, somaybeok, justwowok, niceoneok, coolstoryok, goodluckok.

Rules:
- Usernames must be readable and clean.
- Avoid random strings.
- Avoid duplicates.
- Return ONLY a JSON list of strings like ["aadi.js", "earth.drift", "notfineok"].
"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://render.com", # Required by some OpenRouter models
        "X-Title": "InstaGhostBot"
    }
    data = {
        "model": "arcee-ai/trinity-large-preview:free", # Updated model ID
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=30)
        if response.status_code != 200:
            logger.error(f"OpenRouter Error {response.status_code}: {response.text}")
            return get_fallback_usernames()
            
        resp_json = response.json()
        
        if 'choices' not in resp_json or not resp_json['choices']:
            logger.error(f"AI Error: Invalid response structure: {resp_json}")
            return get_fallback_usernames()
            
        content = resp_json['choices'][0]['message']['content']
        # Extract JSON list
        start = content.find("[")
        end = content.rfind("]") + 1
        if start == -1 or end == 0:
            logger.error(f"AI Error: Could not find JSON list in content: {content}")
            return get_fallback_usernames()
            
        usernames = json.loads(content[start:end])
        if not isinstance(usernames, list):
            return get_fallback_usernames()
            
        return [str(u).strip().lower() for u in usernames if u]
    except Exception as e:
        logger.exception(f"AI Generation Exception: {e}")
        return get_fallback_usernames()

def get_fallback_usernames():
    """Returns a list of usernames based on the user's specific examples."""
    aadi_tech = ["aadi.js", "aadi.py", "aadi.go", "aadi.rs", "aadi.ts", "aadi.dev", "aadi.sys", "aadi.root", "aadi.byte", "aadi.stack", "aadi.node", "aadi.loop", "aadi.core", "aadi.code", "aadi.data", "aadi.logic", "aadi.grid", "aadi.proto", "aadi.kernel", "aadi.debug", "aadi.cache", "aadi.array", "aadi.index", "aadi.queue", "aadi.hash", "aadi.cloud", "aadi.build", "aadi.compile", "aadi.script", "aadi.deploy", "aadi.server", "aadi.client", "aadi.engine", "aadi.stream", "aadi.thread", "aadi.process", "aadi.memory", "aadi.system", "aadi.module", "aadi.network"]
    nature = ["earth.drift", "river.slow", "sky.idle", "ocean.calm", "forest.deep", "storm.low", "cloud.soft", "tide.low", "wind.silent", "rain.light", "mist.fade", "fog.grey", "stone.cold", "sand.soft", "leaf.fall", "wood.dark", "sun.dim", "moon.faded", "wave.gentle", "stream.slow", "field.open", "hill.calm", "valley.deep", "lake.still", "shore.empty", "dawn.soft", "dusk.silent", "night.cold", "light.dim", "shadow.long", "breeze.light", "thunder.low", "drizzle.soft", "ice.cold", "snow.light", "glow.faint", "dust.light", "ash.grey", "root.deep", "branch.low"]
    sarcastic = ["notfineok", "whateverok", "idkbro", "noideaman", "whymepls", "notagainok", "okfinebro", "surewhyok", "sameoldbro", "verycoolok", "somaybeok", "justwowok", "niceoneok", "coolstoryok", "goodluckok", "tryagainok", "lolokbro", "mehwhatever", "nvmokbro", "kfineok", "idcanymore", "finewhatever", "brookfine", "okayigetit", "yeahnotsure", "idkreally", "notmyissue", "leaveitbro", "dontcareok", "stopitok"]
    
    all_examples = aadi_tech + nature + sarcastic
    random.shuffle(all_examples)
    return all_examples[:30]

# --- Instagram Availability Check ---
async def check_instagram_availability(browser, username):
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={'width': 1280, 'height': 720}
    )
    page = await context.new_page()
    
    # Resource blocking to speed up
    await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
    
    try:
        # Strategy 1: Profile Check
        url = f"https://www.instagram.com/{username}/"
        logger.info(f"Checking profile: {url}")
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        if response.status == 404:
            logger.info(f"Username @{username} returned 404. Available.")
            await context.close()
            return True
            
        content = await page.content()
        if "Page not found" in content or "Sorry, this page isn't available" in content:
            logger.info(f"Username @{username} content says not found. Available.")
            await context.close()
            return True
            
        if response.status == 200 and f"instagram.com/{username}" in page.url:
            # If we are on the profile page and it's 200, it's taken
            logger.info(f"Username @{username} profile exists. Taken.")
            await context.close()
            return False

        # Strategy 2: Signup Check (Fallback)
        logger.info(f"Profile check inconclusive for @{username}. Trying signup page...")
        await page.goto("https://www.instagram.com/accounts/emailsignup/", wait_until="networkidle", timeout=20000)
        
        # Handle Cookie Consent if it appears
        try:
            cookie_btn = await page.wait_for_selector('button:has-text("Allow all cookies"), button:has-text("Accept All")', timeout=5000)
            if cookie_btn:
                await cookie_btn.click()
                logger.info("Clicked cookie consent.")
        except:
            pass

        # Wait for the username input
        username_input = await page.wait_for_selector('input[name="username"], input[aria-label="Username"]', timeout=15000)
        if not username_input:
            logger.error(f"Could not find username input for @{username}")
            await context.close()
            return None

        await username_input.click()
        await username_input.fill("") 
        await username_input.type(username, delay=random.randint(50, 150))
        await page.keyboard.press("Tab")
        
        # Wait for validation
        await asyncio.sleep(5)
        
        is_available = await page.evaluate("""() => {
            // Check for success/error icons or text
            const success = document.querySelector('span[aria-label="Success"], .coreSpriteInputAccepted, [aria-label="User name is available"]');
            const error = document.querySelector('span[aria-label="Error"], .coreSpriteInputError, [aria-label="User name is not available"]');
            if (success) return true;
            if (error) return false;
            
            // Check for specific error text
            const bodyText = document.body.innerText;
            if (bodyText.includes("is not available") || bodyText.includes("Another account is using")) return false;
            
            return null;
        }""")
        
        logger.info(f"Signup check for @{username} result: {is_available}")
        await context.close()
        return is_available
    except Exception as e:
        logger.error(f"Check Error for @{username}: {e}")
        # Take a screenshot for debugging if it's a timeout
        if "Timeout" in str(e):
            try:
                await page.screenshot(path=f"debug_{username}.png")
                logger.info(f"Saved debug screenshot: debug_{username}.png")
            except:
                pass
        await context.close()
        return None

# --- Message Management ---
async def send_and_delete(context, chat_id, text, delay):
    formatted_text = f"ℹ️ {text}"
    msg = await context.bot.send_message(chat_id=chat_id, text=formatted_text, parse_mode='Markdown')
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except:
        pass

async def update_status(context, current_status=""):
    status_text = f"""
✨ *InstaGhost Dashboard* ✨
━━━━━━━━━━━━━━━━━━━━
📊 *Statistics:*
  ├ 🔄 *Attempts:* `{state.attempts}`
  ├ ✅ *Available:* `{state.available}`
  └ ❌ *Taken:* `{state.taken}`

🎯 *Current Target:*
  └ `@{state.current_username}`

📡 *Status:*
  └ {current_status}
━━━━━━━━━━━━━━━━━━━━
    """
    try:
        if state.status_message_id:
            await context.bot.edit_message_text(
                chat_id=state.chat_id,
                message_id=state.status_message_id,
                text=status_text,
                parse_mode='Markdown'
            )
        else:
            msg = await context.bot.send_message(
                chat_id=state.chat_id, 
                text=status_text,
                parse_mode='Markdown'
            )
            state.status_message_id = msg.message_id
    except Exception as e:
        # If message is not modified, ignore
        if "Message is not modified" not in str(e):
            logger.exception(f"Status Update Error: {e}")

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
                    await update_status(context, "🔄 Checking...")
                    
                    is_available = await check_instagram_availability(browser, username)
                    
                    if is_available is True:
                        state.available += 1
                        await update_status(context, "✅ *FOUND!*")
                        
                        success_msg = f"""
🎊 *JACKPOT! AVAILABLE USERNAME* 🎊
━━━━━━━━━━━━━━━━━━━━
💎 *Username:* `@{username}`
🔗 *Link:* [instagram.com/{username}](https://www.instagram.com/{username}/)
━━━━━━━━━━━━━━━━━━━━
🕒 _This message will self-destruct in 2 minutes._
                        """
                        
                        msg = await context.bot.send_message(
                            chat_id=state.chat_id,
                            text=success_msg,
                            parse_mode='Markdown',
                            disable_web_page_preview=True
                        )
                        # Auto delete after 2 mins
                        asyncio.create_task(delete_msg_after_delay(context, state.chat_id, msg.message_id, 120))
                    elif is_available is False:
                        state.taken += 1
                        await update_status(context, "❌ Taken")
                    else:
                        # Error or uncertain
                        await update_status(context, "⚠️ Error checking")
                        error_msg = f"⚠️ Error checking @{username}. Retrying..."
                        await send_and_delete(context, state.chat_id, error_msg, 5)
                    
                    # Anti-block delay
                    await asyncio.sleep(random.uniform(1.5, 4.0))
                    
            except Exception as e:
                logger.exception(f"Search Loop Error: {e}")
                error_msg = f"❌ Fatal Error: {e}. Restarting..."
                await send_and_delete(context, state.chat_id, error_msg, 10)
                await asyncio.sleep(5)
        
        await browser.close()

async def delete_msg_after_delay(context, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# --- Bot Commands ---
async def start_ig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.is_running:
        await update.message.reply_text("⚠️ *Bot is already running!*", parse_mode='Markdown')
        return
    
    state.is_running = True
    state.chat_id = update.effective_chat.id
    state.attempts = 0
    state.available = 0
    state.taken = 0
    state.status_message_id = None
    
    await update.message.reply_text("🚀 *Initializing search engine...*", parse_mode='Markdown')
    state.loop_task = asyncio.create_task(search_loop(context))

async def stop_ig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state.is_running:
        await update.message.reply_text("ℹ️ *Bot is not running!*", parse_mode='Markdown')
        return
    
    state.is_running = False
    if state.loop_task:
        state.loop_task.cancel()
    
    await update.message.reply_text("🛑 *Search stopped. Final stats will remain above.*", parse_mode='Markdown')

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found.")
        exit(1)
    
    # Start health check server in a background thread
    threading.Thread(target=run_health_check, daemon=True).start()
    
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("ig", start_ig))
    application.add_handler(CommandHandler("stop", stop_ig))
    
    logger.info("Bot is starting...")
    application.run_polling()
