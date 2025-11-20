# bot.py  —— 直接复制到 Render 就能跑
from pyrogram import Client, filters, types
from pyrogram.types import ChatPrivileges
import asyncio
import os

app = Client(
    "tg_sync_bot",
    api_id=int(os.getenv("API_ID")),
    api_hash=os.getenv("API_HASH"),
    bot_token=os.getenv("BOT_TOKEN", None)  # 不填就用用户号
)

SYNC_GROUPS = set()          # 自动保存同步群
REQUIRED_CHANNELS = []       # 强制关注的频道列表
WELCOME_TEXT = "欢迎！请先关注以下频道才能发言，关注完成后自动解禁～"

# 主人ID（防止别人乱玩）
OWNER_ID = int(os.getenv("OWNER_ID"))

# —— 命令区 ——
@app.on_message(filters.private & filters.command("addall") & filters.user(OWNER_ID))
async def add_all_groups(c, m):
    async for dialog in c.get_dialogs():
        if dialog.chat.type in ["supergroup", "group"]:
            SYNC_GROUPS.add(dialog.chat.id)
    await m.reply(f"已自动添加 {len(SYNC_GROUPS)} 个群到同步列表！")

@app.on_message(filters.private & filters.command("setchannel") & filters.user(OWNER_ID))
async def set_channels(c, m):
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS = m.text.split()[1:]
    await m.reply(f"强制关注频道已更新为：{REQUIRED_CHANNELS or '无'}")

@app.on_message(filters.private & filters.command("status") & filters.user(OWNER_ID))
async def status(c, m):
    await m.reply(f"同步群数量：{len(SYNC_GROUPS)}\n强制频道：{REQUIRED_CHANNELS or '无'}")

# —— 检查是否关注所有频道 ——
async def is_subscribed(user_id):
    if not REQUIRED_CHANNELS:
        return True
    for ch in REQUIRED_CHANNELS:
        try:
            await app.get_chat_member(ch, user_id)
        except:
            return False
    return True

# —— 新成员入群自动禁言+发按钮 ——
@app.on_chat_member_updated()
async def handle_new_member(c, update):
    new = update.new_chat_member
    if new and new.status in ["member", "administrator"] and new.user.id != (await c.get_me()).id:
        if update.chat.id in SYNC_GROUPS and not await is_subscribed(new.user.id):
            # 禁言
            await app.restrict_chat_member(
                update.chat.id, new.user.id,
                ChatPrivileges(can_send_messages=False)
            )
            # 发私信按钮
            buttons = []
            for ch in REQUIRED_CHANNELS:
                if ch.startswith("@"):
                    ch = ch[1:]
                buttons.append([types.InlineKeyboardButton(f"关注 {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
            buttons.append([types.InlineKeyboardButton("已关注，点我解禁", callback_data="check_sub")])
            await app.send_message(new.user.id, WELCOME_TEXT, reply_markup=types.InlineKeyboardMarkup(buttons))

# —— 用户点“已关注”按钮后检查并解禁 ——
@app.on_callback_query(filters.regex("check_sub"))
async def check_and_unban(c, cq):
    if await is_subscribed(cq.from_user.id):
        for gid in SYNC_GROUPS:
            try:
                await app.restrict_chat_member(gid, cq.from_user.id, ChatPrivileges(can_send_messages=True))
            except: pass
        await cq.answer("解禁成功！欢迎发言～", show_alert=True)
        await app.send_message(cq.from_user.id, "已解禁所有同步群！")
    else:
        await cq.answer("检测到你还没关注完哦～", show_alert=True)

# —— 核心同步（发消息、删、编辑全同步）——
@app.on_message(filters.chat(SYNC_GROUPS))
async def sync_message(c, m):
    if m.from_user.id == (await c.get_me()).id:
        return
    if not await is_subscribed(m.from_user.id):
        await m.delete()
        return
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            await m.copy(gid)

@app.on_edited_message(filters.chat(SYNC_GROUPS))
async def sync_edit(c, m):
    for gid in list(SYNC_GROUPS):
        if gid != m.chat.id:
            await m.copy(gid)

@app.on_deleted_messages(filters.chat(SYNC_GROUPS))
async def sync_delete(c, chat, msg_ids):
    for gid in list(SYNC_GROUPS):
        if gid != chat.id:
            await c.delete_messages(gid, msg_ids)

print("10群同步 + 强制关注机器人已启动！")
app.run()
