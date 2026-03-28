# bot.py  —— 支持 Web Service 版本：添加 Flask HTTP 服务器 + 无上限群同步
from pyrogram import Client, filters, types
from pyrogram.types import ChatPrivileges
import asyncio
import os
import json
import logging
import threading  # 用于后台运行 Flask
import atexit  # 用于退出时保存数据
import time  # 用于消息去重时间戳
from flask import Flask  # 新增：Flask 库
import redis  # Redis 数据库

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Data persistence file path
DATA_FILE = "bot_data.json"
MESSAGE_MAP_FILE = "message_mapping.json"

# Redis connection
REDIS_URL = os.getenv("REDIS_URL")
r = None
if REDIS_URL:
    try:
        r = redis.from_url(REDIS_URL)
        logger.info("Redis connection initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Redis connection: {e}")
        logger.info("Falling back to JSON file storage")
        r = None

app_tg = Client(  # 改名，避免和 Flask 冲突
    "tg_sync_bot",
    bot_token=os.getenv("BOT_TOKEN", None)  # 不填就用用户号
    # 使用 Pyrogram 内置的默认 API ID 和 Hash，无需配置 API_ID / API_HASH
)

SYNC_GROUPS = set()          # 自动保存同步群，无上限
REQUIRED_CHANNELS = []       # 强制关注的频道列表
WELCOME_TEXT = "欢迎！请先关注以下频道才能发言，关注完成后自动解禁～"

# —— 频道同步配置 ——
SOURCE_CHANNEL = None        # 主频道（源频道）
TARGET_DESTINATIONS = []     # 目标频道/群组列表

# 管理员列表（初始只放您的 OWNER_ID）
OWNER_ID = int(os.getenv("OWNER_ID"))
ADMINS = [OWNER_ID]  # 支持多个，动态添加

# Bot ID cache
BOT_ID = None

# Message ID mapping: {original_chat_id:original_msg_id: {target_chat_id: target_msg_id, ...}}
MESSAGE_MAPPING = {}
MESSAGE_MAPPING_COUNTER = 0  # Counter for periodic saves

# Channel message ID mapping: {original_msg_id: {target_chat_id: target_msg_id, ...}}
CHANNEL_MESSAGE_MAPPING = {}
CHANNEL_MESSAGE_MAPPING_COUNTER = 0  # Counter for periodic saves

# Track synced message IDs to prevent re-syncing
# Format: {"chat_id:msg_id": timestamp}
# Used to detect messages that were sent by this bot as part of sync
SYNCED_MESSAGES = {}
SYNCED_MESSAGES_COUNTER = 0  # Counter for periodic cleanup

# —— Data Persistence Functions ——
def save_to_redis(key, value):
    """Helper function to save data to Redis with error handling"""
    if r:
        try:
            r.set(key, json.dumps(value))
            logger.info(f"{key} saved to Redis")
            return True
        except Exception as e:
            logger.error(f"Error saving {key} to Redis: {e}")
            return False
    return False

def save_sync_groups():
    """Save sync groups to Redis or JSON file"""
    if not save_to_redis("sync_groups", list(SYNC_GROUPS)):
        save_data()

def save_admins():
    """Save admins to Redis or JSON file"""
    if not save_to_redis("admins", ADMINS):
        save_data()

def save_channels():
    """Save channels to Redis or JSON file"""
    if not save_to_redis("channels", REQUIRED_CHANNELS):
        save_data()

def save_source_channel():
    """Save source channel to Redis or JSON file"""
    if not save_to_redis("source_channel", SOURCE_CHANNEL):
        save_data()

def save_target_destinations():
    """Save target destinations to Redis or JSON file"""
    if not save_to_redis("target_destinations", TARGET_DESTINATIONS):
        save_data()

def load_data():
    """Load persistent data from Redis or JSON file
    
    Note: We use in-place modifications (clear + update/extend) instead of
    reassignment to preserve references across modules. The web routes module
    imports these variables at init time, and reassigning them would cause
    the routes to use stale references.
    """
    global SOURCE_CHANNEL
    if r:
        # Load from Redis
        try:
            # Load sync groups (in-place update to preserve references)
            sync_groups_data = r.get("sync_groups")
            SYNC_GROUPS.clear()
            if sync_groups_data:
                SYNC_GROUPS.update(json.loads(sync_groups_data))
            
            # Load admins (in-place update to preserve references)
            admins_data = r.get("admins")
            ADMINS.clear()
            if admins_data:
                loaded_admins = json.loads(admins_data)
                # Ensure OWNER_ID is always in ADMINS
                if OWNER_ID not in loaded_admins:
                    loaded_admins.append(OWNER_ID)
                ADMINS.extend(loaded_admins)
            else:
                ADMINS.append(OWNER_ID)
            
            # Load channels (in-place update to preserve references)
            channels_data = r.get("channels")
            REQUIRED_CHANNELS.clear()
            if channels_data:
                REQUIRED_CHANNELS.extend(json.loads(channels_data))
            
            # Load source channel
            source_channel_data = r.get("source_channel")
            if source_channel_data:
                SOURCE_CHANNEL = json.loads(source_channel_data)
            else:
                SOURCE_CHANNEL = None
            
            # Load target destinations (in-place update to preserve references)
            target_data = r.get("target_destinations")
            TARGET_DESTINATIONS.clear()
            if target_data:
                TARGET_DESTINATIONS.extend(json.loads(target_data))
            
            logger.info(f"Loaded data from Redis: {len(SYNC_GROUPS)} groups, {len(REQUIRED_CHANNELS)} channels, {len(ADMINS)} admins, source_channel={SOURCE_CHANNEL}, {len(TARGET_DESTINATIONS)} targets")
        except Exception as e:
            logger.error(f"Error loading data from Redis: {e}")
            # Keep existing data on error (don't clear)
    else:
        # Load from JSON file (fallback for local testing)
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    json_data = json.load(f)
                    # In-place updates to preserve references
                    SYNC_GROUPS.clear()
                    SYNC_GROUPS.update(json_data.get('sync_groups', []))
                    
                    REQUIRED_CHANNELS.clear()
                    REQUIRED_CHANNELS.extend(json_data.get('required_channels', []))
                    
                    ADMINS.clear()
                    loaded_admins = json_data.get('admins', [OWNER_ID])
                    # Ensure OWNER_ID is always in ADMINS
                    if OWNER_ID not in loaded_admins:
                        loaded_admins.append(OWNER_ID)
                    ADMINS.extend(loaded_admins)
                    
                    # Load source channel
                    SOURCE_CHANNEL = json_data.get('source_channel', None)
                    
                    # Load target destinations (in-place update to preserve references)
                    TARGET_DESTINATIONS.clear()
                    TARGET_DESTINATIONS.extend(json_data.get('target_destinations', []))
                    
                    logger.info(f"Loaded data from JSON: {len(SYNC_GROUPS)} groups, {len(REQUIRED_CHANNELS)} channels, {len(ADMINS)} admins, source_channel={SOURCE_CHANNEL}, {len(TARGET_DESTINATIONS)} targets")
            else:
                logger.info("No data file found, starting with defaults")
        except Exception as e:
            logger.error(f"Error loading data from JSON: {e}")
            # Keep existing data on error (don't clear)

def save_data():
    """Save persistent data to JSON file"""
    try:
        data = {
            'sync_groups': list(SYNC_GROUPS),
            'required_channels': REQUIRED_CHANNELS,
            'admins': ADMINS,
            'source_channel': SOURCE_CHANNEL,
            'target_destinations': TARGET_DESTINATIONS
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# —— Message Mapping Functions ——
def load_message_mapping():
    """Load message mapping from JSON file"""
    global MESSAGE_MAPPING
    try:
        if os.path.exists(MESSAGE_MAP_FILE):
            with open(MESSAGE_MAP_FILE, 'r') as f:
                MESSAGE_MAPPING = json.load(f)
                logger.info(f"Loaded {len(MESSAGE_MAPPING)} message mappings")
        else:
            logger.info("No message mapping file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading message mapping: {e}")
        MESSAGE_MAPPING = {}

def save_message_mapping():
    """Save message mapping to JSON file"""
    try:
        with open(MESSAGE_MAP_FILE, 'w') as f:
            json.dump(MESSAGE_MAPPING, f)
        logger.debug("Message mapping saved")
    except Exception as e:
        logger.error(f"Error saving message mapping: {e}")

def add_message_mapping(original_chat_id, original_msg_id, target_chat_id, target_msg_id):
    """Add a message ID mapping"""
    global MESSAGE_MAPPING_COUNTER
    key = f"{original_chat_id}:{original_msg_id}"
    if key not in MESSAGE_MAPPING:
        MESSAGE_MAPPING[key] = {}
    # Store as integer for consistency
    MESSAGE_MAPPING[key][str(target_chat_id)] = int(target_msg_id)
    # Save periodically (every 5 new mappings) to reduce risk of data loss
    MESSAGE_MAPPING_COUNTER += 1
    if MESSAGE_MAPPING_COUNTER >= 5:
        save_message_mapping()
        MESSAGE_MAPPING_COUNTER = 0

def get_message_mapping(original_chat_id, original_msg_id):
    """Get message ID mappings for an original message"""
    key = f"{original_chat_id}:{original_msg_id}"
    return MESSAGE_MAPPING.get(key, {})

def delete_message_mapping(original_chat_id, original_msg_id):
    """Delete a message ID mapping"""
    key = f"{original_chat_id}:{original_msg_id}"
    if key in MESSAGE_MAPPING:
        del MESSAGE_MAPPING[key]
        save_message_mapping()

def cleanup_old_mappings(max_entries=10000):
    """Clean up old message mappings to prevent memory growth
    Keeps only the most recent max_entries mappings
    Uses insertion order since Python 3.7+ dicts maintain order
    """
    global MESSAGE_MAPPING
    if len(MESSAGE_MAPPING) > max_entries:
        # Python 3.7+ dicts maintain insertion order, so we can use that
        # Get all keys and keep only the most recent ones
        all_keys = list(MESSAGE_MAPPING.keys())
        keys_to_remove = all_keys[:-max_entries]
        for key in keys_to_remove:
            del MESSAGE_MAPPING[key]
        save_message_mapping()
        logger.info(f"Cleaned up {len(keys_to_remove)} old message mappings")

# —— Channel Message Mapping Functions ——
CHANNEL_MAP_FILE = "channel_message_mapping.json"

def load_channel_message_mapping():
    """Load channel message mapping from JSON file"""
    global CHANNEL_MESSAGE_MAPPING
    try:
        if os.path.exists(CHANNEL_MAP_FILE):
            with open(CHANNEL_MAP_FILE, 'r') as f:
                CHANNEL_MESSAGE_MAPPING = json.load(f)
                logger.info(f"Loaded {len(CHANNEL_MESSAGE_MAPPING)} channel message mappings")
        else:
            logger.info("No channel message mapping file found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading channel message mapping: {e}")
        CHANNEL_MESSAGE_MAPPING = {}

def save_channel_message_mapping():
    """Save channel message mapping to JSON file"""
    try:
        with open(CHANNEL_MAP_FILE, 'w') as f:
            json.dump(CHANNEL_MESSAGE_MAPPING, f)
        logger.debug("Channel message mapping saved")
    except Exception as e:
        logger.error(f"Error saving channel message mapping: {e}")

def add_channel_message_mapping(original_msg_id, target_chat_id, target_msg_id):
    """Add a channel message ID mapping"""
    global CHANNEL_MESSAGE_MAPPING_COUNTER
    key = str(original_msg_id)
    if key not in CHANNEL_MESSAGE_MAPPING:
        CHANNEL_MESSAGE_MAPPING[key] = {}
    CHANNEL_MESSAGE_MAPPING[key][str(target_chat_id)] = int(target_msg_id)
    # Save periodically (every 5 new mappings) to reduce risk of data loss
    CHANNEL_MESSAGE_MAPPING_COUNTER += 1
    if CHANNEL_MESSAGE_MAPPING_COUNTER >= 5:
        save_channel_message_mapping()
        CHANNEL_MESSAGE_MAPPING_COUNTER = 0

def get_channel_message_mapping(original_msg_id):
    """Get channel message ID mappings for an original message"""
    key = str(original_msg_id)
    return CHANNEL_MESSAGE_MAPPING.get(key, {})

def delete_channel_message_mapping(original_msg_id):
    """Delete a channel message ID mapping"""
    key = str(original_msg_id)
    if key in CHANNEL_MESSAGE_MAPPING:
        del CHANNEL_MESSAGE_MAPPING[key]
        save_channel_message_mapping()

# —— Synced Message Tracking Functions ——
def mark_message_as_synced(chat_id, msg_id):
    """Mark a message as synced by this bot
    
    This is used to prevent re-syncing messages that we sent as part of sync.
    Also triggers periodic cleanup to prevent memory growth.
    """
    global SYNCED_MESSAGES_COUNTER
    key = f"{chat_id}:{msg_id}"
    SYNCED_MESSAGES[key] = time.time()
    
    # Periodic cleanup (every 100 new entries)
    SYNCED_MESSAGES_COUNTER += 1
    if SYNCED_MESSAGES_COUNTER >= 100:
        cleanup_synced_messages()
        SYNCED_MESSAGES_COUNTER = 0

def is_synced_message(chat_id, msg_id):
    """Check if a message was synced by this bot
    
    Returns True if the message was sent by this bot as part of sync operation.
    """
    key = f"{chat_id}:{msg_id}"
    return key in SYNCED_MESSAGES

def cleanup_synced_messages(max_age_seconds=3600, max_entries=10000):
    """Clean up old synced message tracking entries
    
    Removes entries older than max_age_seconds to prevent memory growth.
    Also limits total entries to max_entries.
    """
    current_time = time.time()
    keys_to_remove = [
        key for key, timestamp in SYNCED_MESSAGES.items()
        if current_time - timestamp > max_age_seconds
    ]
    for key in keys_to_remove:
        del SYNCED_MESSAGES[key]
    
    # Also limit total entries if still too many
    if len(SYNCED_MESSAGES) > max_entries:
        # Remove oldest entries
        sorted_items = sorted(SYNCED_MESSAGES.items(), key=lambda x: x[1])
        num_to_remove = len(SYNCED_MESSAGES) - max_entries
        for key, _ in sorted_items[:num_to_remove]:
            del SYNCED_MESSAGES[key]
        keys_to_remove.extend([key for key, _ in sorted_items[:num_to_remove]])
    
    if keys_to_remove:
        logger.debug(f"Cleaned up {len(keys_to_remove)} old synced message entries")


# —— /start 和 /help 命令 ——
@app_tg.on_message(filters.private & filters.command("start"))
async def start_cmd(c, m):
    user_id = m.from_user.id
    if user_id in ADMINS:
        await m.reply(
            "👋 **欢迎使用群组同步机器人！**\n\n"
            "您已是管理员，可以使用 /help 查看可用命令。\n"
            "或使用 /admin 进入 Web 管理后台。"
        )
    else:
        await m.reply(
            "👋 **欢迎使用群组同步机器人！**\n\n"
            "此机器人用于同步多个群组的消息。\n"
            "如需使用，请联系管理员将您添加为机器人管理员。"
        )

@app_tg.on_message(filters.private & filters.command("help") & filters.user(ADMINS))
async def help_cmd(c, m):
    help_text = """
📖 **机器人命令帮助**

**群组管理：**
• `/addgroup -100群ID` - 添加群组到同步列表
• `/removegroup -100群ID` - 从同步列表移除群组
• `/addall` - 添加机器人所在的所有群组

**频道管理（强制关注）：**
• `/setchannel @频道1 @频道2` - 设置强制关注频道
• `/setchannel` - 清空强制关注频道

**📡 频道同步：**
• `/setsourcechannel @频道` - 设置主频道（源频道）
• `/addtarget @频道或群ID` - 添加目标频道/群组
• `/removetarget @频道或群ID` - 删除目标频道/群组
• `/listtargets` - 查看所有目标
• `/syncchannel` - 查看当前频道同步配置

**管理员管理：**
• `/addadmin 用户ID` 或 `/addadmin @用户名` - 添加管理员
• `/deladmin 用户ID` - 删除管理员
• `/listadmins` - 查看管理员列表

**其他：**
• `/status` - 查看机器人状态
• `/admin` - 进入 Web 管理后台
• `/help` - 显示此帮助信息

💡 **提示：** 群组 ID 通常以 -100 开头，可通过转发群消息到 @userinfobot 获取。
"""
    await m.reply(help_text)

# —— 新命令：添加/删除管理员 ——
@app_tg.on_message(filters.private & filters.command("addadmin") & filters.user(ADMINS))
async def add_admin(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /addadmin 用户ID 或 @用户名")
    target = m.text.split()[1]
    if target.startswith("@"):
        try:
            user = await c.get_users(target)
            user_id = user.id
        except Exception as e:
            logger.error(f"Failed to get user {target}: {e}")
            return await m.reply("找不到这个用户！")
    else:
        user_id = int(target)
    
    if user_id in ADMINS:
        return await m.reply("已经是管理员了！")
    ADMINS.append(user_id)
    save_admins()
    await m.reply(f"已添加 {user_id} 为管理员！")

@app_tg.on_message(filters.private & filters.command("deladmin") & filters.user(ADMINS))
async def del_admin(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /deladmin 用户ID")
    try:
        user_id = int(m.text.split()[1])
    except ValueError:
        return await m.reply("❌ 无效的用户 ID 格式！")
    if user_id == OWNER_ID:
        return await m.reply("不能删除主人！")
    if user_id in ADMINS:
        ADMINS.remove(user_id)
        save_admins()
        await m.reply(f"已移除 {user_id} 的管理员权限！")
    else:
        await m.reply("不是管理员！")

@app_tg.on_message(filters.private & filters.command("listadmins") & filters.user(ADMINS))
async def list_admins(c, m):
    await m.reply(f"当前管理员列表：{ADMINS}")

# —— 手动添加/删除单个群（支持无限群） ——
@app_tg.on_message(filters.private & filters.command("addgroup") & filters.user(ADMINS))
async def add_group(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /addgroup -100群ID\n💡 群组 ID 通常以 -100 开头")
    try:
        group_id = int(m.text.split()[1])
    except ValueError:
        return await m.reply("❌ 无效的群组 ID 格式！群组 ID 应为数字，通常以 -100 开头。")
    
    # Warn if group ID format looks unusual (but still allow it)
    if group_id > 0:
        await m.reply("⚠️ 注意：群组 ID 通常为负数（以 -100 开头）。如果同步不工作，请确认 ID 正确。\n💡 可通过转发群消息到 @userinfobot 获取正确的群组 ID。")
    
    if group_id in SYNC_GROUPS:
        return await m.reply(f"群组 {group_id} 已在同步列表中！")
    
    SYNC_GROUPS.add(group_id)
    save_sync_groups()
    await m.reply(f"✓ 已添加群 {group_id} 到同步列表！当前总 {len(SYNC_GROUPS)} 个。")

@app_tg.on_message(filters.private & filters.command("removegroup") & filters.user(ADMINS))
async def remove_group(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /removegroup -100群ID")
    try:
        group_id = int(m.text.split()[1])
    except ValueError:
        return await m.reply("❌ 无效的群组 ID 格式！")
    if group_id in SYNC_GROUPS:
        SYNC_GROUPS.remove(group_id)
        save_sync_groups()
        await m.reply(f"已移除群 {group_id}！当前总 {len(SYNC_GROUPS)} 个。")
    else:
        await m.reply("不在列表中！")

# —— 其他命令改成 filters.user(ADMINS) 限制多管理员 ——
@app_tg.on_message(filters.private & filters.command("addall") & filters.user(ADMINS))
async def add_all_groups(c, m):
    async for dialog in c.get_dialogs():
        if dialog.chat.type in ["supergroup", "group"]:
            SYNC_GROUPS.add(dialog.chat.id)
    save_sync_groups()
    await m.reply(f"已自动添加 {len(SYNC_GROUPS)} 个群到同步列表！")

@app_tg.on_message(filters.private & filters.command("setchannel") & filters.user(ADMINS))
async def set_channels(c, m):
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS = m.text.split()[1:]
    save_channels()
    await m.reply(f"强制关注频道已更新为：{REQUIRED_CHANNELS or '无'}")

@app_tg.on_message(filters.private & filters.command("status") & filters.user(ADMINS))
async def status(c, m):
    await m.reply(
        f"同步群数量：{len(SYNC_GROUPS)}\n"
        f"强制频道：{REQUIRED_CHANNELS or '无'}\n"
        f"管理员：{ADMINS}\n"
        f"主频道：{SOURCE_CHANNEL or '未设置'}\n"
        f"目标数量：{len(TARGET_DESTINATIONS)}"
    )

# —— 频道同步管理命令 ——
@app_tg.on_message(filters.private & filters.command("setsourcechannel") & filters.user(ADMINS))
async def set_source_channel(c, m):
    global SOURCE_CHANNEL
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply("用法: /setsourcechannel @频道名 或 -100频道ID\n💡 将此频道设为主频道（源频道）")
    channel = parts[1]
    SOURCE_CHANNEL = channel
    save_source_channel()
    await m.reply(f"✓ 已设置主频道为：{channel}")

@app_tg.on_message(filters.private & filters.command("addtarget") & filters.user(ADMINS))
async def add_target(c, m):
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply("用法: /addtarget @频道或群组 或 -100ID\n💡 添加目标频道/群组")
    target = parts[1]
    # Try to convert to int if it looks like a numeric ID
    try:
        target = int(target)
    except ValueError:
        pass  # Keep as string (username)
    if target in TARGET_DESTINATIONS:
        return await m.reply(f"目标 {target} 已在列表中！")
    TARGET_DESTINATIONS.append(target)
    save_target_destinations()
    await m.reply(f"✓ 已添加目标：{target}（当前共 {len(TARGET_DESTINATIONS)} 个）")

@app_tg.on_message(filters.private & filters.command("removetarget") & filters.user(ADMINS))
async def remove_target(c, m):
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply("用法: /removetarget @频道或群组 或 -100ID")
    target = parts[1]
    # Try to convert to int if it looks like a numeric ID
    try:
        target_int = int(target)
        # Remove either the int or string version
        if target_int in TARGET_DESTINATIONS:
            TARGET_DESTINATIONS.remove(target_int)
            save_target_destinations()
            return await m.reply(f"✓ 已删除目标：{target}（剩余 {len(TARGET_DESTINATIONS)} 个）")
    except ValueError:
        pass
    if target in TARGET_DESTINATIONS:
        TARGET_DESTINATIONS.remove(target)
        save_target_destinations()
        await m.reply(f"✓ 已删除目标：{target}（剩余 {len(TARGET_DESTINATIONS)} 个）")
    else:
        await m.reply(f"目标 {target} 不在列表中！")

@app_tg.on_message(filters.private & filters.command("listtargets") & filters.user(ADMINS))
async def list_targets(c, m):
    if not TARGET_DESTINATIONS:
        return await m.reply("目标列表为空。使用 /addtarget 添加目标频道/群组。")
    target_list = "\n".join(f"• {t}" for t in TARGET_DESTINATIONS)
    await m.reply(f"📋 **目标频道/群组列表（共 {len(TARGET_DESTINATIONS)} 个）：**\n\n{target_list}")

@app_tg.on_message(filters.private & filters.command("syncchannel") & filters.user(ADMINS))
async def sync_channel_status(c, m):
    source = SOURCE_CHANNEL or "未设置"
    if TARGET_DESTINATIONS:
        target_list = "\n".join(f"  • {t}" for t in TARGET_DESTINATIONS)
    else:
        target_list = "  （未设置）"
    await m.reply(
        f"📡 **频道同步配置**\n\n"
        f"**主频道（源）：** {source}\n\n"
        f"**目标列表（{len(TARGET_DESTINATIONS)} 个）：**\n{target_list}\n\n"
        f"💡 使用 /setsourcechannel 设置主频道，/addtarget 添加目标"
    )

# —— Web 管理后台入口 ——
@app_tg.on_message(filters.private & filters.command("admin"))
async def admin_panel(c, m):
    user_id = m.from_user.id
    # 只有管理员才回复
    if user_id not in ADMINS:
        return  # 不是管理员，静默忽略，不回复任何内容
    
    # 生成一次性 Token
    import secrets
    token = f"{user_id}:{secrets.token_urlsafe(32)}"
    
    # 存入 Redis，5分钟过期
    if r:
        try:
            r.setex(f"admin_token:{token}", 300, str(user_id))
        except Exception as e:
            logger.error(f"Failed to store admin token in Redis: {e}")
            return await m.reply("❌ 无法生成访问令牌，请检查 Redis 连接！")
    else:
        return await m.reply("❌ Redis 未配置，无法使用 Web 管理后台！")
    
    # 获取后台 URL
    base_url = os.getenv("BASE_URL", "").rstrip("/")
    if not base_url:
        return await m.reply("❌ 请先设置 BASE_URL 环境变量！")
    
    admin_url = f"{base_url}/admin?token={token}"
    
    # 发送带按钮的消息
    button = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("🖥️ 进入管理后台", url=admin_url)]
    ])
    await m.reply("点击下方按钮进入管理后台：\n\n⚠️ 链接5分钟内有效", reply_markup=button)

# —— 检查是否关注所有频道 ——
async def is_subscribed(user_id):
    if not REQUIRED_CHANNELS:
        return True
    for ch in REQUIRED_CHANNELS:
        try:
            await app_tg.get_chat_member(ch, user_id)
        except Exception as e:
            logger.debug(f"User {user_id} not subscribed to {ch}: {e}")
            return False
    return True

# —— 新成员入群自动禁言+发按钮 ——
@app_tg.on_chat_member_updated()
async def handle_new_member(c, update):
    new = update.new_chat_member
    if new and new.status in ["member", "administrator"] and new.user.id != (await c.get_me()).id:
        if update.chat.id in SYNC_GROUPS and not await is_subscribed(new.user.id):
            # 禁言
            await app_tg.restrict_chat_member(
                update.chat.id, new.user.id,
                ChatPrivileges(can_send_messages=False)
            )
            # 发私信按钮
            buttons = []
            for ch in REQUIRED_CHANNELS:
                ch_name = ch.lstrip('@')
                buttons.append([types.InlineKeyboardButton(f"关注 {ch_name}", url=f"https://t.me/{ch_name}")])
            buttons.append([types.InlineKeyboardButton("已关注，点我解禁", callback_data="check_sub")])
            await app_tg.send_message(new.user.id, WELCOME_TEXT, reply_markup=types.InlineKeyboardMarkup(buttons))

# —— 用户点“已关注”按钮后检查并解禁 ——
@app_tg.on_callback_query(filters.regex("check_sub"))
async def check_and_unban(c, cq):
    if await is_subscribed(cq.from_user.id):
        for gid in list(SYNC_GROUPS):
            try:
                await app_tg.restrict_chat_member(gid, cq.from_user.id, ChatPrivileges(can_send_messages=True))
            except Exception as e:
                logger.error(f"Failed to unban user {cq.from_user.id} in group {gid}: {e}")
        await cq.answer("解禁成功！欢迎发言～", show_alert=True)
        await app_tg.send_message(cq.from_user.id, "已解禁所有同步群！")
    else:
        await cq.answer("检测到你还没关注完哦～", show_alert=True)

# —— 核心同步（发消息、删、编辑全同步）——
# Use dynamic filter to check if message is from a sync group
# Note: If running as a bot account, Telegram doesn't deliver messages from other bots.
# To sync messages from other bots, run as a user account (leave BOT_TOKEN empty).
@app_tg.on_message(filters.group)
async def sync_message(c, m):
    global BOT_ID
    # Cache bot ID on first call
    if BOT_ID is None:
        BOT_ID = (await c.get_me()).id
    
    # Check if message is from a sync group
    if m.chat.id not in SYNC_GROUPS:
        return
    
    # Skip service messages (join, leave, etc.)
    if m.service:
        return
    
    # Skip empty messages
    if m.empty:
        return
    
    # Skip forwarded messages to prevent syncing user-forwarded content
    # Messages manually forwarded by users have forward_date attribute set
    # We skip these to avoid duplicate sync of already forwarded content
    if m.forward_date:
        return
    
    # Skip messages from this bot/user itself to prevent infinite loops
    if m.from_user and m.from_user.id == BOT_ID:
        return
    
    # Skip messages sent by this bot/user as channel/sender_chat
    if m.sender_chat and m.sender_chat.id == BOT_ID:
        return
    
    # Skip messages that were synced by this bot (deduplication check)
    # This handles edge cases where the bot sends as anonymous admin
    if is_synced_message(m.chat.id, m.id):
        return
    
    # Determine if message is from a bot (for logging purposes)
    is_from_bot = m.from_user and m.from_user.is_bot
    is_from_channel = m.sender_chat is not None
    
    # Check subscription only for regular users (not bots, not anonymous, not channels)
    # Messages from other bots and channels are synced without subscription check
    if m.from_user and not m.from_user.is_bot:
        if not await is_subscribed(m.from_user.id):
            try:
                await m.delete()
            except Exception as e:
                logger.error(f"Failed to delete unsubscribed user message: {e}")
            return
    
    # Log bot/channel messages for debugging
    if is_from_bot:
        logger.debug(f"Syncing message from bot {m.from_user.id} in group {m.chat.id}")
    elif is_from_channel:
        logger.debug(f"Syncing message from channel/sender_chat {m.sender_chat.id} in group {m.chat.id}")
    
    # Sync to all other groups
    # Use copy() instead of forward() to:
    # 1. Hide the "Forwarded from..." header (隐藏消息引用)
    # 2. Allow syncing messages from other bots (转发其他机器人发送的内容)
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            try:
                sent = await m.copy(gid)
                # Store message mapping for edit/delete sync
                add_message_mapping(m.chat.id, m.id, gid, sent.id)
                # Mark the synced message to prevent re-syncing
                mark_message_as_synced(gid, sent.id)
            except Exception as e:
                logger.error(f"Copy failed to {gid}: {e}")

@app_tg.on_edited_message(filters.group)
async def sync_edit(c, m):
    global BOT_ID
    if BOT_ID is None:
        BOT_ID = (await c.get_me()).id
    
    # Check if message is from a sync group
    if m.chat.id not in SYNC_GROUPS:
        return
    
    # Skip forwarded messages to prevent syncing user-forwarded content
    if m.forward_date:
        return
    
    # Skip messages from this bot/user itself to prevent infinite loops
    if m.from_user and m.from_user.id == BOT_ID:
        return
    
    # Skip messages sent by this bot/user as channel/sender_chat
    if m.sender_chat and m.sender_chat.id == BOT_ID:
        return
    
    # Skip messages that were synced by this bot (deduplication check)
    if is_synced_message(m.chat.id, m.id):
        return
    
    # Log bot/channel message edits for debugging
    if m.from_user and m.from_user.is_bot:
        logger.debug(f"Syncing edited message from bot {m.from_user.id} in group {m.chat.id}")
    elif m.sender_chat:
        logger.debug(f"Syncing edited message from channel/sender_chat {m.sender_chat.id} in group {m.chat.id}")
    
    # Try to use message mapping to edit the synced messages
    mapping = get_message_mapping(m.chat.id, m.id)
    
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            try:
                # If we have a mapping, try to edit the existing message
                target_msg_id = mapping.get(str(gid))
                if target_msg_id:
                    try:
                        # Determine message type and use appropriate edit method
                        if m.media:
                            # It's a media message - edit caption (can be empty or None)
                            await c.edit_message_caption(
                                chat_id=gid,
                                message_id=target_msg_id,
                                caption=m.caption or ""
                            )
                            logger.info(f"Edited caption of message {target_msg_id} in {gid}")
                        elif m.text:
                            # It's a text message
                            await c.edit_message_text(
                                chat_id=gid,
                                message_id=target_msg_id,
                                text=m.text
                            )
                            logger.info(f"Edited text of message {target_msg_id} in {gid}")
                        else:
                            # Message type cannot be edited (e.g., stickers, files without text/caption changes)
                            raise Exception("Message type does not support editing, will forward as new")
                    except Exception as e:
                        # If edit fails (e.g., message type changed), forward as new
                        logger.warning(f"Edit failed for {gid}, forwarding as new: {e}")
                        # Use copy() to hide forward header
                        try:
                            sent = await m.copy(gid)
                            add_message_mapping(m.chat.id, m.id, gid, sent.id)
                            mark_message_as_synced(gid, sent.id)
                        except Exception as copy_e:
                            logger.error(f"Copy failed to {gid}: {copy_e}")
                else:
                    # No mapping found, copy as new message
                    # Use copy() to hide forward header
                    try:
                        sent = await m.copy(gid)
                        add_message_mapping(m.chat.id, m.id, gid, sent.id)
                        mark_message_as_synced(gid, sent.id)
                    except Exception as copy_e:
                        logger.error(f"Copy failed to {gid}: {copy_e}")
            except Exception as e:
                logger.error(f"Edit sync failed to {gid}: {e}")

@app_tg.on_deleted_messages(filters.group)
async def sync_delete(c, messages):
    # Check if messages are from a sync group
    if not messages:
        return
    
    # Group messages by their original chat and collect mappings
    delete_targets = {}  # {target_chat_id: [msg_ids]}
    
    # Process each deleted message
    for m in messages:
        if m.chat.id not in SYNC_GROUPS:
            continue
        
        # Get the message mapping
        mapping = get_message_mapping(m.chat.id, m.id)
        
        if mapping:
            # Collect target messages to delete
            for gid_str, target_msg_id in mapping.items():
                gid = int(gid_str)
                if gid != m.chat.id:
                    if gid not in delete_targets:
                        delete_targets[gid] = []
                    delete_targets[gid].append(target_msg_id)
            
            # Clean up the mapping
            delete_message_mapping(m.chat.id, m.id)
        else:
            # No mapping found, just log it
            logger.info(f"Message {m.id} deleted in {m.chat.id}, but no mapping found")
    
    # Batch delete messages by group
    for gid, msg_ids in delete_targets.items():
        try:
            await c.delete_messages(gid, msg_ids)
            logger.info(f"Deleted {len(msg_ids)} synced message(s) in {gid}")
        except Exception as e:
            logger.error(f"Delete sync failed to {gid}: {e}")

# —— 频道消息同步（主频道 → 目标频道/群组）——
@app_tg.on_message(filters.channel)
async def sync_channel_message(c, m):
    """Sync messages from the source channel to all target destinations"""
    if not SOURCE_CHANNEL or not TARGET_DESTINATIONS:
        return
    
    # Determine source channel identifier (could be username or numeric ID)
    chat = m.chat
    source_match = False
    try:
        source_str = str(SOURCE_CHANNEL)
        # Match by username (@name) or numeric ID
        if source_str.startswith('@') and chat.username:
            source_match = chat.username.lower() == source_str.lstrip('@').lower()
        else:
            try:
                source_match = chat.id == int(source_str)
            except ValueError:
                pass
    except Exception:
        pass
    
    if not source_match:
        return
    
    # Skip empty/deleted messages (Telegram sends empty message objects for deleted messages)
    if m.empty:
        return
    
    logger.info(f"Syncing channel message {m.id} from {chat.id} to {len(TARGET_DESTINATIONS)} targets")
    
    # Copy to all target destinations
    for dest in list(TARGET_DESTINATIONS):
        try:
            sent = await m.copy(dest)
            # Store mapping for edit/delete sync
            add_channel_message_mapping(m.id, sent.chat.id, sent.id)
            # Mark as synced to prevent loops
            mark_message_as_synced(sent.chat.id, sent.id)
            logger.debug(f"Copied channel message {m.id} to {dest} as {sent.id}")
        except Exception as e:
            logger.error(f"Failed to copy channel message to {dest}: {e}")

@app_tg.on_edited_message(filters.channel)
async def sync_channel_edit(c, m):
    """Sync edited messages from the source channel to all target destinations"""
    if not SOURCE_CHANNEL or not TARGET_DESTINATIONS:
        return
    
    chat = m.chat
    source_match = False
    try:
        source_str = str(SOURCE_CHANNEL)
        if source_str.startswith('@') and chat.username:
            source_match = chat.username.lower() == source_str.lstrip('@').lower()
        else:
            try:
                source_match = chat.id == int(source_str)
            except ValueError:
                pass
    except Exception:
        pass
    
    if not source_match:
        return
    
    mapping = get_channel_message_mapping(m.id)
    
    for dest in list(TARGET_DESTINATIONS):
        try:
            # Resolve dest to a numeric chat_id if needed
            try:
                dest_id = int(dest)
            except (ValueError, TypeError):
                dest_id = dest
            
            target_msg_id = mapping.get(str(dest_id))
            if target_msg_id:
                try:
                    if m.media:
                        await c.edit_message_caption(
                            chat_id=dest_id,
                            message_id=target_msg_id,
                            caption=m.caption or ""
                        )
                    elif m.text:
                        await c.edit_message_text(
                            chat_id=dest_id,
                            message_id=target_msg_id,
                            text=m.text
                        )
                    else:
                        raise Exception("Cannot edit message: only text and media messages with captions are supported")
                    logger.info(f"Edited channel message {target_msg_id} in {dest_id}")
                except Exception as e:
                    logger.warning(f"Channel edit failed for {dest_id}, copying as new: {e}")
                    try:
                        sent = await m.copy(dest)
                        add_channel_message_mapping(m.id, sent.chat.id, sent.id)
                        mark_message_as_synced(sent.chat.id, sent.id)
                    except Exception as copy_e:
                        logger.error(f"Copy failed to {dest}: {copy_e}")
            else:
                # No mapping, copy as new
                try:
                    sent = await m.copy(dest)
                    add_channel_message_mapping(m.id, sent.chat.id, sent.id)
                    mark_message_as_synced(sent.chat.id, sent.id)
                except Exception as copy_e:
                    logger.error(f"Copy failed to {dest}: {copy_e}")
        except Exception as e:
            logger.error(f"Channel edit sync failed to {dest}: {e}")

@app_tg.on_deleted_messages(filters.channel)
async def sync_channel_delete(c, messages):
    """Sync deleted messages from the source channel to all target destinations"""
    if not SOURCE_CHANNEL or not TARGET_DESTINATIONS or not messages:
        return
    
    delete_targets = {}  # {target_chat_id: [msg_ids]}
    
    for m in messages:
        mapping = get_channel_message_mapping(m.id)
        if mapping:
            for dest_str, target_msg_id in mapping.items():
                try:
                    dest_id = int(dest_str)
                except ValueError:
                    dest_id = dest_str
                if dest_id not in delete_targets:
                    delete_targets[dest_id] = []
                delete_targets[dest_id].append(target_msg_id)
            delete_channel_message_mapping(m.id)
    
    for dest_id, msg_ids in delete_targets.items():
        try:
            await c.delete_messages(dest_id, msg_ids)
            logger.info(f"Deleted {len(msg_ids)} synced channel message(s) in {dest_id}")
        except Exception as e:
            logger.error(f"Channel delete sync failed to {dest_id}: {e}")

# 新增：Flask HTTP 服务器，让 Render Web Service 检测到端口
flask_app = Flask(__name__, template_folder='web/templates')

# Configure Flask session (using default cookie-based sessions)
# Generate a consistent secret key based on BOT_TOKEN if SECRET_KEY not provided
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    # Use BOT_TOKEN as seed for consistent secret key across restarts
    import hashlib
    bot_token = os.getenv("BOT_TOKEN", "")
    secret_key = hashlib.sha256(bot_token.encode()).hexdigest()
flask_app.secret_key = secret_key

# Import and initialize web routes
from web.routes import init_routes
init_routes(flask_app)

@flask_app.route('/')
def health_check():
    return "Bot is running!", 200  # 返回健康响应

def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render 默认端口 10000
    flask_app.run(host='0.0.0.0', port=port)

def graceful_shutdown():
    """Save all data before shutdown"""
    logger.info("正在保存数据...")
    save_data()
    save_message_mapping()
    save_channel_message_mapping()
    logger.info("数据保存完成，机器人关闭")

# Register atexit handler
atexit.register(graceful_shutdown)

if __name__ == "__main__":
    # Load persistent data
    load_data()
    
    # Load message mappings
    load_message_mapping()
    load_channel_message_mapping()
    
    # Clean up old mappings if too many
    cleanup_old_mappings()
    
    # 启动 Flask 在后台线程
    threading.Thread(target=run_flask, daemon=True).start()
    
    logger.info("无限群同步 + 强制关注 + 多管理员机器人已启动！（Web Service 模式）")
    app_tg.run()
