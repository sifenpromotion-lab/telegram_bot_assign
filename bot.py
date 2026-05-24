"""
Telegram Group Assignment Bot
"""

import io
import os
import json
import random
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes


# ── CONFIGURE HERE ────────────────────────────────────────────────────
BOT_TOKEN     = "8772107339:AAFQjJH4Npqr4xWI8eoQzwY5t0-48sf3usI"
MINI_APP_URL  = "https://telegrambotassign-production.up.railway.app"
_group_id     = "-5060583183"
MAIN_GROUP_ID = int(_group_id)

MAX_PER_TEAM  = 4   # ← maximum members per team

TEAMS = {
    "Team A": {"bg": (30,  58,  138), "accent": (59,  130, 246)},
    "Team B": {"bg": (6,   78,  59),  "accent": (16,  185, 129)},
    "Team C": {"bg": (124, 45,  18),  "accent": (249, 115, 22)},
}

FONT_BOLD   = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
FONT_ITALIC = "/usr/share/fonts/truetype/google-fonts/Poppins-LightItalic.ttf"
# ──────────────────────────────────────────────────────────────────────

print(f"✅ Config loaded: group={MAIN_GROUP_ID}, max_per_team={MAX_PER_TEAM}")

# In-memory storage
assignments:  dict[int, str] = {}
group_counts: dict[str, int] = defaultdict(int)
tg_app: Application | None = None


# ── Image generator ───────────────────────────────────────────────────

def make_announcement_image(user_name: str, team: str) -> io.BytesIO:
    W, H = 900, 480
    cfg  = TEAMS[team]
    bg   = cfg["bg"]
    acc  = cfg["accent"]

    img  = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    for x in range(-H, W + H, 30):
        stripe = tuple(min(c + 12, 255) for c in bg)
        draw.line([(x, 0), (x + H, H)], fill=stripe, width=1)

    draw.rectangle([0, 0, 8, H], fill=acc)

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

    pill = "NEW MEMBER"
    ptw  = draw.textlength(pill, font=f_label)
    px, py = 48, 36
    draw.rounded_rectangle([px-14, py-8, px+ptw+14, py+28], radius=20, fill=acc)
    draw.text((px, py), pill, font=f_label, fill="white")

    display_name = user_name if len(user_name) <= 20 else user_name[:18] + "…"
    draw.text((48, 86), display_name, font=f_name, fill="white")

    draw.rectangle([48, 168, 430, 172], fill=acc)
    draw.text((48, 184), "has been assigned to", font=f_sub, fill=(200, 200, 200))
    draw.text((48, 220), team, font=f_team, fill=acc)

    cx, cy, r = 700, 240, 130
    circle_bg = tuple(min(c + 30, 255) for c in bg)
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=circle_bg, outline=acc, width=4)
    initial = team.split()[-1][0]
    tw = draw.textlength(initial, font=f_big)
    draw.text((cx - tw / 2, cy - 68), initial, font=f_big, fill=acc)

    bar_bg = tuple(max(c - 20, 0) for c in bg)
    draw.rectangle([0, H - 52, W, H], fill=bar_bg)

    # Show member count on image e.g. "2 / 4 members"
    count = group_counts[team]
    draw.text((48, H - 38), f"Team members: {count} / {MAX_PER_TEAM}  🎉", font=f_small, fill=(180, 180, 180))

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
    raw  = update.effective_message.web_app_data.data
    data = json.loads(raw)
    team = data.get("group")
    user = update.effective_user
    if not team or team not in TEAMS:
        return

    try:
        img_buf = make_announcement_image(user.full_name, team)
        await context.bot.send_photo(
            chat_id=MAIN_GROUP_ID,
            photo=img_buf,
            caption=f"🎉 {user.full_name} has joined {team}! ({group_counts[team]}/{MAX_PER_TEAM} members)"
        )
        print(f"✅ Announcement sent for {user.full_name} → {team}")
    except Exception as e:
        print(f"❌ Failed to send photo: {e}")

    await update.message.reply_text(f"✅ You've been assigned to {team}!")


# ── FastAPI backend ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    global tg_app
    tg_app = Application.builder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler)
    )
    await tg_app.initialize()
    await tg_app.start()
    webhook_url = f"{MINI_APP_URL}/webhook/{BOT_TOKEN}"
    await tg_app.bot.set_webhook(webhook_url, drop_pending_updates=True)
    print(f"✅ Webhook set: {webhook_url}")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    await tg_app.bot.delete_webhook()
    await tg_app.stop()
    await tg_app.shutdown()

api = FastAPI(lifespan=lifespan)

# Allow requests from any origin (Mini App on Vercel → Railway backend)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@api.post("/assign")
async def assign(request: Request):
    body    = await request.json()
    user_id = body.get("user_id")
    name    = body.get("name", "A member")

    if not user_id:
        return JSONResponse({"error": "no user_id"}, status_code=400)

    if user_id in assignments:
        return JSONResponse({
            "group": assignments[user_id],
            "error": "already_assigned",
            "counts": dict(group_counts),
            "max_per_team": MAX_PER_TEAM
        })

    available = [t for t in TEAMS if group_counts[t] < MAX_PER_TEAM]
    if not available:
        return JSONResponse({"error": "all_full"}, status_code=409)

    team = random.choice(available)
    assignments[user_id] = team
    group_counts[team]  += 1

    if tg_app:
        try:
            img_buf = make_announcement_image(name, team)
            await tg_app.bot.send_photo(
                chat_id=MAIN_GROUP_ID,
                photo=img_buf,
                caption=f"🎉 {name} has joined {team}! ({group_counts[team]}/{MAX_PER_TEAM} members)"
            )
            print(f"✅ Announcement sent for {name} → {team}")
        except Exception as e:
            print(f"❌ Failed to send photo: {e}")

    return JSONResponse({
        "group": team,
        "counts": dict(group_counts),
        "max_per_team": MAX_PER_TEAM
    })


@api.get("/counts")
async def counts():
    return JSONResponse({"counts": dict(group_counts), "max_per_team": MAX_PER_TEAM})




@api.post(f"/webhook/{'{token}'}")
async def telegram_webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=403)
    data   = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return JSONResponse({"ok": True})


# ── Entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(api, host="0.0.0.0", port=port)