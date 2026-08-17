#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from urllib.parse import quote
from typing import Dict, Set, Optional, Any
import urllib.request
import urllib.error

# ================================================
# AUTO DEPENDENCY CHECK
# ================================================
def check_and_install_dependencies():
    """Check and install required packages"""
    required_packages = {
        'telegram': 'python-telegram-bot',
        'aiohttp': 'aiohttp',
        'requests': 'requests'
    }
    
    missing_packages = []
    
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"📦 Installing missing packages: {', '.join(missing_packages)}")
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"✅ Installed: {package}")
            except Exception as e:
                print(f"❌ Failed to install {package}: {e}")
                sys.exit(1)

check_and_install_dependencies()

# Now import required modules
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import aiohttp

# ================================================
# CONFIGURATION
# ================================================
BOT_TOKEN = "7956395880:AAECDuPZaKhwZjTawZPabEMKfbE0Uhb1NgE"  # BotFather থেকে প্রাপ্ত token
ADMIN_IDS = [8636806039]  # Admin user ID(s)
CHANNEL_ID = -1003916049925
CHANNEL_LINK = "https://t.me/CODE_X_RAHAT"
JOIN_REWARD = 5
REFERRAL_REWARD = 1
SMS_COST = 1
SMS_API_URL = "https://api.lmnx9.shop/custom/sms2.php"

# ================================================
# LOGGING CONFIGURATION
# ================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================================================
# IN-MEMORY STORAGE
# ================================================
users_db = {}  # user_id: {user_data}
coupons_db = {}  # coupon_code: {coupon_data}
referrals_db = {}  # referrer_id: [referred_user_ids]
bot_start_time = time.time()

class UserData:
    def __init__(self, user_id: int, username: str = ""):
        self.user_id = user_id
        self.username = username
        self.points = 0
        self.sms_used = 0
        self.successful_referrals = 0
        self.join_reward_claimed = False
        self.is_banned = False
        self.referred_by = None
        self.coupons_used = {}  # coupon_code: True
        self.join_verified = False
        self.created_at = datetime.now()

# ================================================
# HELPER FUNCTIONS
# ================================================
def get_user_data(user_id: int, username: str = "") -> UserData:
    """Get or create user data"""
    if user_id not in users_db:
        users_db[user_id] = UserData(user_id, username)
    elif username and not users_db[user_id].username:
        users_db[user_id].username = username
    return users_db[user_id]

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def format_points(points: int) -> str:
    """Format points display"""
    return f"⭐ {points} Points"

def get_bot_username(application: Application) -> str:
    """Get bot username"""
    return application.bot.username

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user has joined the required channel"""
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

def create_main_keyboard():
    """Create main reply keyboard"""
    keyboard = [
        ["📱 Send SMS", "💰 Balance"],
        ["🎁 Referral", "🎟 Coupon"],
        ["👤 Profile", "📊 Statistics"],
        ["ℹ️ Help"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_admin_keyboard():
    """Create admin reply keyboard"""
    keyboard = [
        ["👥 Users", "📊 Bot Stats"],
        ["➕ Add Points", "➖ Remove Points"],
        ["🎟 Add Coupon", "🚫 Ban User"],
        ["✅ Unban User", "📢 Broadcast"],
        ["🔙 User Menu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_force_join_keyboard():
    """Create force join inline keyboard"""
    keyboard = [
        [InlineKeyboardButton("📢 JOIN CHANNEL", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ VERIFY MEMBERSHIP", callback_data="verify_membership")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_sms_api(number: str, message: str) -> bool:
    """Send SMS via API (non-blocking)"""
    try:
        # URL encode parameters
        encoded_number = quote(number)
        encoded_message = quote(message)
        url = f"{SMS_API_URL}?number={encoded_number}&message={encoded_message}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        # Check if API returned success
                        if data.get('status') in ['success', 'ok', 1, '1', True]:
                            return True
                        else:
                            logger.error(f"SMS API returned failure: {data}")
                            return False
                    except ValueError:
                        # Response is not JSON, check raw text
                        text = await response.text()
                        logger.error(f"SMS API returned non-JSON response: {text[:100]}")
                        return False
                else:
                    logger.error(f"SMS API returned status code: {response.status}")
                    return False
    except asyncio.TimeoutError:
        logger.error("SMS API timeout")
        return False
    except aiohttp.ClientError as e:
        logger.error(f"SMS API network error: {e}")
        return False
    except Exception as e:
        logger.error(f"SMS API unexpected error: {e}")
        return False

# ================================================
# COMMAND HANDLERS
# ================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if not update.effective_user or not update.effective_chat:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    # Check if user is banned
    if user_data.is_banned:
        await update.message.reply_text(
            "🚫 **BANNED**\n\n"
            "আপনি এই bot ব্যবহার করতে পারবেন না।\n"
            "Admin এর সাথে যোগাযোগ করুন।",
            parse_mode='HTML'
        )
        return
    
    # Check for referral
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id and not user_data.referred_by:
                user_data.referred_by = referrer_id
        except (ValueError, IndexError):
            pass
    
    # Check channel membership
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            "🔐 **CHANNEL VERIFICATION**\n\n"
            "Bot ব্যবহার করার আগে আমাদের official channel-এ join করুন।\n\n"
            "👇 নিচের বাটনে click করে channel-এ join করুন এবং তারপর verify করুন।",
            reply_markup=create_force_join_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # User is verified
    user_data.join_verified = True
    
    # First time join reward
    if not user_data.join_reward_claimed:
        user_data.points += JOIN_REWARD
        user_data.join_reward_claimed = True
        await update.message.reply_text(
            "🎉 **WELCOME!**\n\n"
            "✅ Channel verification successful!\n"
            f"🎁 Join reward: +{JOIN_REWARD} points\n"
            f"💰 Current balance: {user_data.points} points\n\n"
            "নিচের menu থেকে feature select করুন:",
            reply_markup=create_main_keyboard(),
            parse_mode='HTML'
        )
        
        # Process referral reward
        if user_data.referred_by and user_data.referred_by in users_db:
            referrer = users_db[user_data.referred_by]
            if user.id not in referrals_db.get(user_data.referred_by, []):
                referrer.points += REFERRAL_REWARD
                referrer.successful_referrals += 1
                if user_data.referred_by not in referrals_db:
                    referrals_db[user_data.referred_by] = []
                referrals_db[user_data.referred_by].append(user.id)
                
                # Notify referrer
                try:
                    await context.bot.send_message(
                        chat_id=user_data.referred_by,
                        text=f"🎉 **REFERRAL SUCCESS**\n\n"
                             f"👤 New user: @{user.username or user.id}\n"
                             f"💎 Reward: +{REFERRAL_REWARD} point\n"
                             f"💰 Balance: {referrer.points} points"
                    )
                except:
                    pass
    else:
        await update.message.reply_text(
            "👋 **WELCOME BACK!**\n\n"
            "নিচের menu থেকে feature select করুন:",
            reply_markup=create_main_keyboard(),
            parse_mode='HTML'
        )

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verify membership callback"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_data = get_user_data(user.id, user.username or "")
    
    # Check if user is banned
    if user_data.is_banned:
        await query.edit_message_text(
            "🚫 **BANNED**\n\nআপনি এই bot ব্যবহার করতে পারবেন না।",
            parse_mode='HTML'
        )
        return
    
    # Check channel membership
    if not await check_channel_membership(update, context):
        await query.edit_message_text(
            "❌ **VERIFICATION FAILED**\n\n"
            "আগে আমাদের channel-এ join করুন, তারপর Verify করুন।\n\n"
            "👇 নিচের বাটনে click করে join করুন:",
            reply_markup=create_force_join_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # User is verified
    user_data.join_verified = True
    
    if not user_data.join_reward_claimed:
        user_data.points += JOIN_REWARD
        user_data.join_reward_claimed = True
        
        # Process referral reward
        if user_data.referred_by and user_data.referred_by in users_db:
            referrer = users_db[user_data.referred_by]
            if user.id not in referrals_db.get(user_data.referred_by, []):
                referrer.points += REFERRAL_REWARD
                referrer.successful_referrals += 1
                if user_data.referred_by not in referrals_db:
                    referrals_db[user_data.referred_by] = []
                referrals_db[user_data.referred_by].append(user.id)
                
                try:
                    await context.bot.send_message(
                        chat_id=user_data.referred_by,
                        text=f"🎉 **REFERRAL SUCCESS**\n\n"
                             f"👤 New user: @{user.username or user.id}\n"
                             f"💎 Reward: +{REFERRAL_REWARD} point\n"
                             f"💰 Balance: {referrer.points} points"
                    )
                except:
                    pass
        
        await query.edit_message_text(
            "✅ **VERIFICATION SUCCESSFUL**\n\n"
            f"🎁 Join reward: +{JOIN_REWARD} points\n"
            f"💰 Current balance: {user_data.points} points\n\n"
            "Welcome! নিচের menu থেকে feature select করুন:",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text(
            "✅ **ALREADY VERIFIED**\n\n"
            "আপনি already verified আছেন।\n"
            "নিচের menu থেকে feature select করুন:",
            parse_mode='HTML'
        )

async def sms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sms command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    # Check if user is banned
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    # Check channel membership
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            "🔐 **CHANNEL VERIFICATION REQUIRED**\n\n"
            "SMS পাঠানোর আগে channel-এ join করুন:",
            reply_markup=create_force_join_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "📱 **SEND SMS**\n\n"
            "Usage: `/sms NUMBER MESSAGE`\n\n"
            "Example: `/sms 018XXXXXXXX Hello`\n\n"
            f"💎 Cost: {SMS_COST} point per SMS",
            parse_mode='HTML'
        )
        return
    
    number = context.args[0]
    message = ' '.join(context.args[1:])
    
    # Validate number (basic validation)
    if not number.replace('+', '').isdigit() or len(number) < 6:
        await update.message.reply_text("❌ Invalid number format। সঠিক number দিন।")
        return
    
    # Check points balance
    if user_data.points < SMS_COST:
        await update.message.reply_text(
            "❌ **INSUFFICIENT POINTS**\n\n"
            f"💰 Balance: {user_data.points} points\n"
            f"📱 SMS Cost: {SMS_COST} point\n\n"
            "Referral system-এর মাধ্যমে আরো points earn করুন!"
        )
        return
    
    # Send SMS (non-blocking)
    loading_msg = await update.message.reply_text("📤 Sending SMS...")
    
    success = await send_sms_api(number, message)
    
    await loading_msg.delete()
    
    if success:
        # Deduct point only after successful API confirmation
        user_data.points -= SMS_COST
        user_data.sms_used += 1
        
        await update.message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━━━╮\n"
            "       ✅ SMS SENT\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "📨 Message sent successfully!\n\n"
            f"💰 Remaining Points: {user_data.points}\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "╭━━━━━━━━━━━━━━━━━━━━╮\n"
            "      ❌ SEND FAILED\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "Message could not be sent.\n\n"
            "💰 No points were deducted.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode='HTML'
        )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle balance command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    await update.message.reply_text(
        "💰 **BALANCE**\n\n"
        f"⭐ Current Points: {user_data.points}\n"
        f"📱 SMS Cost: {SMS_COST} point",
        parse_mode='HTML'
    )

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle referral command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    bot_username = get_bot_username(context.application)
    referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    
    keyboard = [
        [InlineKeyboardButton("📤 Share Referral Link", url=f"https://t.me/share/url?url={referral_link}")]
    ]
    
    await update.message.reply_text(
        "🎁 **REFERRAL**\n\n"
        f"🔗 Your Referral Link:\n`{referral_link}`\n\n"
        f"👥 Successful Referrals: {user_data.successful_referrals}\n"
        f"💎 Reward Per Referral: {REFERRAL_REWARD} point\n\n"
        "Share your referral link এবং points earn করুন!\n"
        "প্রতিটি successful referral-এর জন্য আপনি points পাবেন।",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /coupon command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "🎟 **COUPON**\n\n"
            "Usage: `/coupon CODE`\n\n"
            "Example: `/coupon ABC123`",
            parse_mode='HTML'
        )
        return
    
    code = context.args[0].upper()
    
    if code not in coupons_db:
        await update.message.reply_text("❌ Invalid or expired coupon।")
        return
    
    coupon = coupons_db[code]
    
    # Check if coupon is active
    if not coupon['active']:
        await update.message.reply_text("❌ Invalid or expired coupon।")
        return
    
    # Check if user already used this coupon
    if code in user_data.coupons_used:
        await update.message.reply_text("⚠️ You already used this coupon।")
        return
    
    # Check if coupon has remaining uses
    if coupon['used_count'] >= coupon['max_uses']:
        await update.message.reply_text("❌ Invalid or expired coupon।")
        return
    
    # Apply coupon
    user_data.points += coupon['reward']
    user_data.coupons_used[code] = True
    coupon['used_count'] += 1
    
    await update.message.reply_text(
        "🎟 **COUPON SUCCESS**\n\n"
        f"🎁 Reward: +{coupon['reward']} points\n"
        f"💰 Balance: {user_data.points}",
        parse_mode='HTML'
    )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profile command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    await update.message.reply_text(
        "👤 **MY PROFILE**\n\n"
        f"🆔 User ID: `{user.id}`\n"
        f"👤 Username: @{user.username or 'N/A'}\n"
        f"⭐ Current Points: {user_data.points}\n"
        f"📱 SMS Used: {user_data.sms_used}\n"
        f"👥 Successful Referrals: {user_data.successful_referrals}\n"
        f"🎁 Join Reward Status: {'✅ Claimed' if user_data.join_reward_claimed else '❌ Not Claimed'}\n"
        f"🚫 Ban Status: {'✅ Banned' if user_data.is_banned else '✅ Active'}",
        parse_mode='HTML'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle statistics command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    await update.message.reply_text(
        "📊 **YOUR STATISTICS**\n\n"
        f"⭐ Points: {user_data.points}\n"
        f"📱 SMS Requests: {user_data.sms_used}\n"
        f"👥 Successful Referrals: {user_data.successful_referrals}\n"
        f"🎁 Join Reward Status: {'✅ Claimed' if user_data.join_reward_claimed else '❌ Not Claimed'}",
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help command"""
    await update.message.reply_text(
        "ℹ️ **HELP**\n\n"
        "Available Commands:\n"
        "/start - Start the bot\n"
        "/sms - Send SMS\n"
        "/balance - Check balance\n"
        "/referral - Get referral link\n"
        "/coupon - Redeem coupon\n"
        "/profile - View profile\n"
        "/stats - View statistics\n"
        "/help - Show this help\n\n"
        "For more information, contact admin।",
        parse_mode='HTML'
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    await update.message.reply_text(
        "👑 **ADMIN PANEL**\n\n"
        "Admin commands:\n"
        "/addpoints USER_ID AMOUNT - Add points\n"
        "/removepoints USER_ID AMOUNT - Remove points\n"
        "/addcoupon CODE POINTS USES - Add coupon\n"
        "/ban USER_ID - Ban user\n"
        "/unban USER_ID - Unban user\n"
        "/broadcast MESSAGE - Broadcast message\n"
        "/botstats - Bot statistics\n\n"
        "নিচের menu থেকে select করুন:",
        reply_markup=create_admin_keyboard(),
        parse_mode='HTML'
    )

async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add points command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addpoints USER_ID AMOUNT")
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid input। সঠিক ID এবং amount দিন।")
        return
    
    target = get_user_data(target_id)
    target.points += amount
    
    await update.message.reply_text(
        "✅ **POINTS UPDATED**\n\n"
        f"👤 User: {target_id}\n"
        f"➕ Added: {amount}\n"
        f"💰 New Balance: {target.points}",
        parse_mode='HTML'
    )

async def remove_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remove points command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removepoints USER_ID AMOUNT")
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid input। সঠিক ID এবং amount দিন।")
        return
    
    target = get_user_data(target_id)
    target.points = max(0, target.points - amount)  # Prevent negative balance
    
    await update.message.reply_text(
        "✅ **POINTS UPDATED**\n\n"
        f"👤 User: {target_id}\n"
        f"➖ Removed: {amount}\n"
        f"💰 New Balance: {target.points}",
        parse_mode='HTML'
    )

async def add_coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add coupon command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /addcoupon CODE POINTS USES")
        return
    
    code = context.args[0].upper()
    try:
        reward = int(context.args[1])
        max_uses = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid input। সঠিক points এবং uses দিন।")
        return
    
    coupons_db[code] = {
        'code': code,
        'reward': reward,
        'max_uses': max_uses,
        'used_count': 0,
        'active': True,
        'created_at': datetime.now()
    }
    
    await update.message.reply_text(
        "✅ **COUPON ADDED**\n\n"
        f"🎟 Code: {code}\n"
        f"🎁 Reward: {reward} points\n"
        f"👥 Max Uses: {max_uses}",
        parse_mode='HTML'
    )

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ban command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /ban USER_ID")
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID।")
        return
    
    target = get_user_data(target_id)
    target.is_banned = True
    
    await update.message.reply_text(
        "✅ **USER BANNED**\n\n"
        f"👤 User: {target_id}",
        parse_mode='HTML'
    )

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unban command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unban USER_ID")
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID।")
        return
    
    target = get_user_data(target_id)
    target.is_banned = False
    
    await update.message.reply_text(
        "✅ **USER UNBANNED**\n\n"
        f"👤 User: {target_id}",
        parse_mode='HTML'
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /broadcast MESSAGE")
        return
    
    message = ' '.join(context.args)
    success_count = 0
    failed_count = 0
    
    for user_id, user_data in users_db.items():
        if user_data.is_banned:
            continue
        
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
            await asyncio.sleep(0.05)  # Rate limit protection
        except:
            failed_count += 1
    
    await update.message.reply_text(
        "📢 **BROADCAST COMPLETE**\n\n"
        f"✅ Success: {success_count}\n"
        f"❌ Failed: {failed_count}",
        parse_mode='HTML'
    )

async def bot_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot statistics command"""
    if not update.effective_user:
        return
    
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("🚫 **Admin Only**")
        return
    
    total_users = len(users_db)
    verified_users = sum(1 for u in users_db.values() if u.join_verified)
    banned_users = sum(1 for u in users_db.values() if u.is_banned)
    total_points = sum(u.points for u in users_db.values())
    total_referrals = sum(len(v) for v in referrals_db.values())
    total_sms = sum(u.sms_used for u in users_db.values())
    total_coupons = len(coupons_db)
    uptime = int(time.time() - bot_start_time)
    
    # Format uptime
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60
    
    await update.message.reply_text(
        "📊 **BOT STATISTICS**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Verified Users: {verified_users}\n"
        f"🚫 Banned Users: {banned_users}\n"
        f"💰 Total Points Distributed: {total_points}\n"
        f"👥 Successful Referrals: {total_referrals}\n"
        f"📱 Total SMS Requests: {total_sms}\n"
        f"🎟 Total Coupons: {total_coupons}\n"
        f"⏱ Bot Uptime: {hours}h {minutes}m {seconds}s",
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    if not update.effective_user or not update.message or not update.message.text:
        return
    
    user = update.effective_user
    user_data = get_user_data(user.id, user.username or "")
    
    if user_data.is_banned:
        await update.message.reply_text("🚫 আপনি banned আছেন।")
        return
    
    text = update.message.text
    
    # Handle keyboard buttons
    if text == "📱 Send SMS":
        await update.message.reply_text(
            "📱 **SEND SMS**\n\n"
            "Usage: `/sms NUMBER MESSAGE`\n\n"
            "Example: `/sms 018XXXXXXXX Hello`\n\n"
            f"💎 Cost: {SMS_COST} point per SMS",
            parse_mode='HTML'
        )
    elif text == "💰 Balance":
        await balance_command(update, context)
    elif text == "🎁 Referral":
        await referral_command(update, context)
    elif text == "🎟 Coupon":
        await update.message.reply_text(
            "🎟 **COUPON**\n\n"
            "Usage: `/coupon CODE`\n\n"
            "Example: `/coupon ABC123`",
            parse_mode='HTML'
        )
    elif text == "👤 Profile":
        await profile_command(update, context)
    elif text == "📊 Statistics":
        await stats_command(update, context)
    elif text == "ℹ️ Help":
        await help_command(update, context)
    elif text == "👥 Users":
        if is_admin(user.id):
            total = len(users_db)
            await update.message.reply_text(f"👥 Total Users: {total}")
    elif text == "📊 Bot Stats":
        if is_admin(user.id):
            await bot_stats_command(update, context)
    elif text == "🔙 User Menu":
        if is_admin(user.id):
            await update.message.reply_text(
                "User menu-এ ফিরে এসেছেন।",
                reply_markup=create_main_keyboard()
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred। Please try again later।"
            )
    except:
        pass

# ================================================
# MAIN FUNCTION
# ================================================
def main():
    """Main function to start the bot"""
    # Print startup banner
    print("=" * 40)
    print("     PROFESSIONAL TELEGRAM BOT")
    print("=" * 40)
    print()
    print("🚀 Starting...")
    print("📢 Force Join: @CODE_X_RAHAT")
    print("💾 Storage: RAM")
    print("🟢 Bot Running")
    print()
    
    # Validate token
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your BOT_TOKEN in the CONFIG section!")
        sys.exit(1)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sms", sms_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("coupon", coupon_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("addpoints", add_points_command))
    application.add_handler(CommandHandler("removepoints", remove_points_command))
    application.add_handler(CommandHandler("addcoupon", add_coupon_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("botstats", bot_stats_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(verify_callback, pattern="verify_membership"))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    print("✅ Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()