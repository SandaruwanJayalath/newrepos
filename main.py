import aiohttp
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, html
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberAdministrator
from aiogram.enums import ParseMode, ChatMemberStatus
import re
import os
from datetime import datetime

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_URL_TEMPLATE = os.environ.get("API_URL_TEMPLATE")
API_KEY = os.environ.get("API_KEY")

# Logging Configuration (Error විතරක් ලොග් වෙන්න හදලා තියෙන්නෙ)
logging.basicConfig(level=logging.ERROR)

# --- Initialize Bot and Dispatcher ---

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# --- User Request Tracking ---
# සීමිත පරිශීලකයන්ට දිනකට එක් ඉල්ලීමක් පමණක් සැකසීමට ඉඩ දීම සඳහා ශ්‍රිත සාදන්න

user_requests = {}  # Format: {user_id: {"last_request": datetime, "count": int}}

# --- Helper Functions ---

async def is_admin(chat_id: int, user_id: int) -> bool:
    """
    Check if the user is an admin in the given chat.
    Returns True if the user is an admin, False otherwise.
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)
    except Exception as e:
        logging.error(f"Error checking admin status: {e}")
        return False

async def check_rate_limit(user_id: int) -> bool:
    """
    Check if the user has exceeded the daily request limit.
    Returns True if the user can make a request, False otherwise.
    """
    today = datetime.now().date()
    if user_id in user_requests:
        if user_requests[user_id]["last_request"].date() == today:
            if user_requests[user_id]["count"] >= 1:
                return False  # Limit exceeded
            else:
                return True  # Limit not exceeded
        else:
            return True  # New day, limit reset
    else:
        return True  # First request, limit not exceeded

async def update_user_request(user_id: int):
    """
    Update the user's request count.
    """
    today = datetime.now().date()
    if user_id in user_requests:
        if user_requests[user_id]["last_request"].date() == today:
            user_requests[user_id]["count"] += 1
        else:
            user_requests[user_id] = {"last_request": datetime.now(), "count": 1}
    else:
        user_requests[user_id] = {"last_request": datetime.now(), "count": 1}

async def get_likes_info(uid: str, region: str) -> dict:
    """
    Fetch likes info from the Garena Free Fire API.
    Returns a dictionary containing the parsed API response, or None if an error occurred.
    """
    url = API_URL_TEMPLATE.format(uid=uid, key=API_KEY)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return parse_api_response(data)
                else:
                    logging.error(f"API Error: {response.status} - {await response.text()}")
                    return None
    except aiohttp.ClientError as e:
        logging.error(f"HTTP Client Error: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected Error: {e}")
        return None

def parse_api_response(data: str) -> dict:
    """
    Parse the API response and extract necessary values.
    Returns a dictionary containing the extracted values.
    """
    values = {}
    values["name"] = re.search(r"- Name > (.*?)\n", data)
    values["uid"] = re.search(r"- Uid > (\d+)\n", data)
    values["level"] = re.search(r"- Level > (\d+)\n", data)
    values["exp"] = re.search(r"\[Exp :\s*(\d+)\]", data)
    values["likes_before"] = re.search(r"- Likes BeFore > (\d+)\n", data)
    values["likes_after"] = re.search(r"- Likes After > (\d+)\n", data)
    values["likes_given"] = re.search(r"- Likes Given > (\d+)", data)

    return {
        "name": values["name"].group(1) if values["name"] else "N/A",
        "uid": values["uid"].group(1) if values["uid"] else "N/A",
        "level": values["level"].group(1) if values["level"] else "N/A",
        "exp": values["exp"].group(1) if values["exp"] else "N/A",
        "likes_before": values["likes_before"].group(1) if values["likes_before"] else "N/A",
        "likes_after": values["likes_after"].group(1) if values["likes_after"] else "N/A",
        "likes_given": values["likes_given"].group(1) if values["likes_given"] else "N/A",
    }

# --- Command Handlers ---

@dp.message(Command("like"))
async def cmd_like(message: Message):
    """
    Handle the /like command.
    Processes the command, checks for admin status, rate limits, and sends a request to the API.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    args = message.text.split()[1:]

    if len(args) != 2:
        await message.reply("වැරදි භාවිතය. නිවැරදි භාවිතය: /like <region> <UID>")
        return

    region, uid = args

    if not uid.isdigit():
        await message.reply("වලංගු නොවන UID ආකෘතිය. UID එකේ අංක පමණක් තිබිය යුතුය.")
        return

    # Check if the command is used in a group
    if chat_id > 0:
        await message.reply("මෙම විධානය සමූහයක භාවිත කළ යුතුය.")
        return

    # Check if the user is an admin
    if await is_admin(chat_id, user_id):
        likes_info = await get_likes_info(uid, region)
        # Update admin's request count (no limit)
        await update_user_request(user_id)
    else:
        if await check_rate_limit(user_id):
            likes_info = await get_likes_info(uid, region)
            if likes_info:
                await update_user_request(user_id)
        else:
            await message.reply("ඔබ අද දවස සඳහා ඔබගේ උපරිම like ඉල්ලීම් ගණන ඉක්මවා ඇත. කරුණාකර හෙට නැවත උත්සාහ කරන්න.")
            return

    if likes_info is None:
        await message.reply("API එකෙන් දත්ත ලබාගැනීමේදී දෝෂයක් ඇති විය. කරුණාකර පසුව නැවත උත්සාහ කරන්න.")
        return

    if likes_info["likes_given"] == "0":
        await message.reply(
            f"<b>{html.quote(likes_info['name'])}</b> හට අද දවස සඳහා උපරිම likes ගණන ලැබී ඇත. කරුණාකර හෙට නැවත උත්සාහ කරන්න, නැතහොත් වෙනත් UID එකක් ලබා දෙන්න.\n"
            f"UID: <code>{html.quote(likes_info['uid'])}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        response_text = (
            f"<b>✅ Like ඉල්ලීම සාර්ථකයි!</b>\n\n"
            f"<b>👤 නම:</b> {html.quote(likes_info['name'])}\n"
            f"<b>🆔 UID:</b> <code>{html.quote(likes_info['uid'])}</code>\n"
            f"<b>⭐ මට්ටම:</b> {html.quote(likes_info['level'])}\n"
            f"<b>📈 exp:</b> {html.quote(likes_info['exp'])}\n"
            f"<b>👍 Likes (පෙර):</b> {html.quote(likes_info['likes_before'])}\n"
            f"<b>👍 Likes (පසු):</b> {html.quote(likes_info['likes_after'])}\n"
            f"<b>❤️ ලබා දුන් Likes:</b> {html.quote(likes_info['likes_given'])}\n\n"
            f"ස්තූතියි!"
        )
        await message.reply(response_text, parse_mode=ParseMode.HTML)

# --- Main ---

async def main():
    """
    Start the bot polling.
    """
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
