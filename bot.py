"""
Telegram Group Assignment Bot
────────────────────────────────────────────────────────────────────────
Flow:
  1. User opens Mini App from /start button
  2. User clicks "Assign me" → Mini App calls POST /assign
  3. Bot generates a styled image and posts it to the main group

Requirements:
  pip install python-telegram-bot Pillow fastapi uvicorn

Run:
  python bot.py
"""

import io
import json
import math
import random
import asyncio
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


# ── CONFIGURE HERE ────────────────────────────────────────────────────
BOT_TOKEN    = "YOUR_BOT_TOKEN"               # From @BotFather
MINI_APP_URL = "https://your-app.vercel.app"  # Where you hosted index.html
MAIN_GROUP_ID = -1001234567890                # Your main Telegram group chat ID
                                               # (negative number — get it via /id command)

TEAMS = {
    "Team A": {
        "bg":     (30,  58,  138),   # dark blue
        "accent": (59,  130, 246),   # bright blue
    },
    "Team B": {
        "bg":     (6,   78,  59),    # dark green
        "accent": (16,  185, 129),   # bright green
    },
    "Team C": {
        "bg":     (124, 45,  18),    # dark orange
        "accent": (249, 115, 22),    # bright orange
    },
}

FONT_BOLD   = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
FONT_ITALIC = "/usr/share/fonts/truetype/google-fonts/Poppins-LightItalic.ttf"

MAX_PER_TEAM = 10   # ← change this to whatever limit you want per team
# ──────────────────────────────────────────────────────────────────────


# In-memory storage — replace with SQLite/Redis for production
assignments:  dict[int, str] = {}        # user_id -> team name
group_counts: dict[str, int] = defaultdict(int)

# Telegram app reference (set after build)
tg_app: Application | None = None


# ── Image generator ───────────────────────────────────────────────────

def make_announcement_image(user_name: str, team: str) -> io.BytesIO:
    W, H = 900, 480
    cfg  = TEAMS[team]
    bg   = cfg["bg"]
    acc  = cfg["accent"]

    img  = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Subtle diagonal texture
    for x in range(-H, W + H, 30):
        stripe = tuple(min(c + 12, 255) for c in bg)
        draw.line([(x, 0), (x + H, H)], fill=stripe, width=1)

    # Left accent bar
    draw.rectangle([0, 0, 8, H], fill=acc)

    # Load fonts (fallback to default if missing)
    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    f_label = font(FONT_BOLD,   18)
    f_name  = font(FONT_BOLD,   68)
    f_team  = font(FONT_BOLD,   52)
    f_sub   = font(FONT_ITALIC, 26)
    f_small = font(FONT_BOLD,   22)
    f_big   = font(FONT_BOLD,  120)

    # "NEW MEMBER" pill
    pill = "NEW MEMBER"
    ptw  = draw.textlength(pill, font=f_label)
    px, py = 48, 36
    draw.rounded_rectangle([px-14, py-8, px+ptw+14, py+28], radius=20, fill=acc)
    draw.text((px, py), pill, font=f_label, fill="white")

    # User name — truncate if very long
    display_name = user_name if len(user_name) <= 20 else user_name[:18] + "…"
    draw.text((48, 86), display_name, font=f_name, fill="white")

    # Divider
    draw.rectangle([48, 168, 430, 172], fill=acc)

    # Subtitle
    draw.text((48, 184), "has been assigned to", font=f_sub, fill=(200, 200, 200))

    # Team name
    draw.text((48, 220), team, font=f_team, fill=acc)

    # Right circle with team initial
    cx, cy, r = 700, 240, 130
    circle_bg  = tuple(min(c + 30, 255) for c in bg)
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=circle_bg, outline=acc, width=4)
    initial = team.split()[-1][0]          # "A", "B", or "C"
    tw = draw.textlength(initial, font=f_big)
    draw.text((cx - tw / 2, cy - 68), initial, font=f_big, fill=acc)

    # Bottom bar
    bar_bg = tuple(max(c - 20, 0) for c in bg)
    draw.rectangle([0, H - 52, W, H], fill=bar_bg)
    draw.text((48, H - 38), "Welcome to the team!  🎉", font=f_small, fill=(180, 180, 180))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Telegram bot handlers ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton(
            "✦  Join a group",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]]
    await update.message.reply_text(
        "👋 Tap the button below to be randomly assigned to a team!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called when the Mini App posts via tg.sendData().
    Used as a fallback — the /assign endpoint is the primary path.
    """
    raw  = update.effective_message.web_app_data.data
    data = json.loads(raw)
    team = data.get("group")
    user = update.effective_user
    if not team or team not in TEAMS:
        return

    # Post announcement image to main group
    img_buf   = make_announcement_image(user.full_name, team)
    await context.bot.send_photo(
        chat_id=MAIN_GROUP_ID,
        photo=img_buf,
        caption=f"🎉 {user.full_name} has joined {team}!"
    )

    await update.message.reply_text(f"✅ You've been assigned to {team}!")


# ── FastAPI backend ───────────────────────────────────────────────────

api = FastAPI()


@api.post("/assign")
async def assign(request: Request):
    body    = await request.json()
    user_id = body.get("user_id")
    name    = body.get("name", "A member")

    if not user_id:
        return JSONResponse({"error": "no user_id"}, status_code=400)

    # Already assigned?
    if user_id in assignments:
        return JSONResponse({"group": assignments[user_id], "error": "already_assigned"})

    # Only consider teams that still have room
    available = [t for t in TEAMS if group_counts[t] < MAX_PER_TEAM]

    if not available:
        return JSONResponse({"error": "all_full"}, status_code=409)

    # Pick randomly from available teams
    team = random.choice(available)

    assignments[user_id] = team
    group_counts[team]  += 1

    # Post announcement image to main group (async via bot)
    if tg_app:
        img_buf = make_announcement_image(name, team)
        await tg_app.bot.send_photo(
            chat_id=MAIN_GROUP_ID,
            photo=img_buf,
            caption=f"🎉 {name} has joined {team}!"
        )

    return JSONResponse({"group": team})


@api.get("/counts")
async def counts():
    return JSONResponse({"counts": dict(group_counts), "max_per_team": MAX_PER_TEAM})


# ── Entry point ───────────────────────────────────────────────────────

async def main():
    global tg_app

    # Build Telegram bot
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler)
    )

    # Run FastAPI in the same event loop — no threads, no loop conflict
    import uvicorn
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(api, host="0.0.0.0", port=8000, log_level="info")
    )

    # Start bot manually so we control the loop
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)

    # Both run concurrently in the same event loop
    await uvicorn_server.serve()

    # Graceful shutdown
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())