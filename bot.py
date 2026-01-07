# bot.py  —— 支持 Web Service 版本：添加 Flask HTTP 服务器 + 无上限群同步
from pyrogram import Client, filters, types
from pyrogram.types import ChatPrivileges
import asyncio
import os
import json
import logging
import threading  # 用于后台运行 Flask
import atexit  # 用于退出时保存数据
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
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN", None)  # 不填就用用户号
)

SYNC_GROUPS = set()          # 自动保存同步群，无上限
REQUIRED_CHANNELS = []       # 强制关注的频道列表
WELCOME_TEXT = "欢迎！请先关注以下频道才能发言，关注完成后自动解禁～"

# 管理员列表（初始只放您的 OWNER_ID）
OWNER_ID = int(os.getenv("OWNER_ID"))
ADMINS = [OWNER_ID]  # 支持多个，动态添加

# Bot ID cache
BOT_ID = None

# Message ID mapping: {original_chat_id:original_msg_id: {target_chat_id: target_msg_id, ...}}
MESSAGE_MAPPING = {}
MESSAGE_MAPPING_COUNTER = 0  # Counter for periodic saves

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

def load_data():
    """Load persistent data from Redis or JSON file
    
    Note: We use in-place modifications (clear + update/extend) instead of
    reassignment to preserve references across modules. The web routes module
    imports these variables at init time, and reassigning them would cause
    the routes to use stale references.
    """
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
            
            logger.info(f"Loaded data from Redis: {len(SYNC_GROUPS)} groups, {len(REQUIRED_CHANNELS)} channels, {len(ADMINS)} admins")
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
                    
                    logger.info(f"Loaded data from JSON: {len(SYNC_GROUPS)} groups, {len(REQUIRED_CHANNELS)} channels, {len(ADMINS)} admins")
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
            'admins': ADMINS
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

**频道管理：**
• `/setchannel @频道1 @频道2` - 设置强制关注频道
• `/setchannel` - 清空强制关注频道

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
    await m.reply(f"同步群数量：{len(SYNC_GROUPS)}\n强制频道：{REQUIRED_CHANNELS or '无'}\n管理员：{ADMINS}")

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
    
    # Skip messages from the bot itself (sent by bot user)
    if m.from_user and m.from_user.id == BOT_ID:
        return
    
    # Skip messages sent by bot as channel/sender_chat
    if m.sender_chat and m.sender_chat.id == BOT_ID:
        return
    
    # Check subscription only for regular users (not bots, not anonymous, not channels)
    if m.from_user and not m.from_user.is_bot:
        if not await is_subscribed(m.from_user.id):
            try:
                await m.delete()
            except Exception as e:
                logger.error(f"Failed to delete unsubscribed user message: {e}")
            return
    
    # Sync to all other groups
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            try:
                sent = await m.copy(gid)
                # Store message mapping for edit/delete sync
                add_message_mapping(m.chat.id, m.id, gid, sent.id)
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
    
    # Skip messages from the bot itself
    if m.from_user and m.from_user.id == BOT_ID:
        return
    
    # Skip messages sent by bot as channel/sender_chat
    if m.sender_chat and m.sender_chat.id == BOT_ID:
        return
    
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
                            raise Exception("Message type does not support editing, will copy as new")
                    except Exception as e:
                        # If edit fails (e.g., message type changed), copy as new
                        logger.warning(f"Edit failed for {gid}, copying as new: {e}")
                        sent = await m.copy(gid)
                        add_message_mapping(m.chat.id, m.id, gid, sent.id)
                else:
                    # No mapping found, copy as new message
                    sent = await m.copy(gid)
                    add_message_mapping(m.chat.id, m.id, gid, sent.id)
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
    logger.info("数据保存完成，机器人关闭")

# Register atexit handler
atexit.register(graceful_shutdown)

if __name__ == "__main__":
    # Load persistent data
    load_data()
    
    # Load message mappings
    load_message_mapping()
    
    # Clean up old mappings if too many
    cleanup_old_mappings()
    
    # 启动 Flask 在后台线程
    threading.Thread(target=run_flask, daemon=True).start()
    
    logger.info("无限群同步 + 强制关注 + 多管理员机器人已启动！（Web Service 模式）")
    app_tg.run()
