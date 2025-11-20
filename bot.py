# bot.py  —— 支持 Web Service 版本：添加 Flask HTTP 服务器 + 无上限群同步
from pyrogram import Client, filters, types
from pyrogram.types import ChatPrivileges
import asyncio
import os
import threading  # 用于后台运行 Flask
from flask import Flask  # 新增：Flask 库

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
        except:
            return await m.reply("找不到这个用户！")
    else:
        user_id = int(target)
    
    if user_id in ADMINS:
        return await m.reply("已经是管理员了！")
    ADMINS.append(user_id)
    await m.reply(f"已添加 {user_id} 为管理员！")

@app_tg.on_message(filters.private & filters.command("deladmin") & filters.user(ADMINS))
async def del_admin(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /deladmin 用户ID")
    user_id = int(m.text.split()[1])
    if user_id == OWNER_ID:
        return await m.reply("不能删除主人！")
    if user_id in ADMINS:
        ADMINS.remove(user_id)
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
        return await m.reply("用法: /addgroup -100群ID")
    group_id = int(m.text.split()[1])
    SYNC_GROUPS.add(group_id)
    await m.reply(f"已添加群 {group_id} 到同步列表！当前总 {len(SYNC_GROUPS)} 个。")

@app_tg.on_message(filters.private & filters.command("removegroup") & filters.user(ADMINS))
async def remove_group(c, m):
    if len(m.text.split()) < 2:
        return await m.reply("用法: /removegroup -100群ID")
    group_id = int(m.text.split()[1])
    if group_id in SYNC_GROUPS:
        SYNC_GROUPS.remove(group_id)
        await m.reply(f"已移除群 {group_id}！当前总 {len(SYNC_GROUPS)} 个。")
    else:
        await m.reply("不在列表中！")

# —— 其他命令改成 filters.user(ADMINS) 限制多管理员 ——
@app_tg.on_message(filters.private & filters.command("addall") & filters.user(ADMINS))
async def add_all_groups(c, m):
    async for dialog in c.get_dialogs():
        if dialog.chat.type in ["supergroup", "group"]:
            SYNC_GROUPS.add(dialog.chat.id)
    await m.reply(f"已自动添加 {len(SYNC_GROUPS)} 个群到同步列表！")

@app_tg.on_message(filters.private & filters.command("setchannel") & filters.user(ADMINS))
async def set_channels(c, m):
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS = m.text.split()[1:]
    await m.reply(f"强制关注频道已更新为：{REQUIRED_CHANNELS or '无'}")

@app_tg.on_message(filters.private & filters.command("status") & filters.user(ADMINS))
async def status(c, m):
    await m.reply(f"同步群数量：{len(SYNC_GROUPS)}\n强制频道：{REQUIRED_CHANNELS or '无'}\n管理员：{ADMINS}")

# —— 检查是否关注所有频道 ——
async def is_subscribed(user_id):
    if not REQUIRED_CHANNELS:
        return True
    for ch in REQUIRED_CHANNELS:
        try:
            await app_tg.get_chat_member(ch, user_id)
        except:
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
            except: pass
        await cq.answer("解禁成功！欢迎发言～", show_alert=True)
        await app_tg.send_message(cq.from_user.id, "已解禁所有同步群！")
    else:
        await cq.answer("检测到你还没关注完哦～", show_alert=True)

# —— 核心同步（发消息、删、编辑全同步）——
@app_tg.on_message(filters.chat(list(SYNC_GROUPS)))
async def sync_message(c, m):
    if m.from_user.id == (await c.get_me()).id:
        return
    if not await is_subscribed(m.from_user.id):
        await m.delete()
        return
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            try:
                await m.copy(gid)
            except Exception as e:
                print(f"Copy failed: {e}")

@app_tg.on_edited_message(filters.chat(list(SYNC_GROUPS)))
async def sync_edit(c, m):
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            try:
                await m.copy(gid)
            except Exception as e:
                print(f"Edit failed: {e}")

@app_tg.on_deleted_messages(filters.chat(list(SYNC_GROUPS)))
async def sync_delete(c, chat, msg_ids):
    for gid in list(SYNC_GROUPS):
        if gid != chat.id:
            try:
                await c.delete_messages(gid, msg_ids)
            except Exception as e:
                print(f"Delete failed: {e}")

# 新增：Flask HTTP 服务器，让 Render Web Service 检测到端口
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Bot is running!", 200  # 返回健康响应

def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render 默认端口 10000
    flask_app.run(host='0.0.0.0', port=port)

# 启动 Flask 在后台线程
threading.Thread(target=run_flask, daemon=True).start()

print("无限群同步 + 强制关注 + 多管理员机器人已启动！（Web Service 模式）")
app_tg.run()
