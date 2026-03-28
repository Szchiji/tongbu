# 用户账户模式指南

本文档详细介绍 tongbu 机器人的两种运行模式，帮助你根据需求选择合适的配置方式。

## 模式对比

| 特性 | Bot 账户模式 | 用户账户模式 |
|------|-------------|-------------|
| 配置复杂度 | 简单（只需 BOT_TOKEN） | 较复杂（需要手机号或 session 字符串） |
| 同步普通用户消息 | ✅ 支持 | ✅ 支持 |
| 同步其他机器人消息 | ❌ 不支持（Telegram 限制） | ✅ 支持 |
| 隐藏消息来源 | ✅ 支持（使用 copy 方法） | ✅ 支持 |
| 账号安全风险 | 低（Bot Token 即可） | 较高（使用个人账号） |
| Telegram 封号风险 | 无 | 自动化行为存在封号风险 |
| 适用场景 | 只需同步普通用户消息 | 需要同步其他机器人发送的内容 |

## 模式选择建议

- **大多数场景**：使用 **Bot 账户模式**即可，配置简单、安全稳定。
- **需要同步机器人消息**：使用 **用户账户模式**，例如群内有其他机器人（公告机器人、游戏机器人等）发送内容需要同步时。

> ⚠️ **警告**：使用个人 Telegram 账号运行自动化脚本存在违反 Telegram 服务条款的风险，可能导致账号被封禁。建议使用专用的小号进行操作。

---

## Bot 账户模式（默认）

### 工作原理

设置 `BOT_TOKEN` 环境变量后，机器人以 Bot 账号身份运行。Telegram 平台限制 Bot 之间不互相推送消息，因此无法同步其他机器人发送的内容。

### 配置步骤

1. 通过 [@BotFather](https://t.me/BotFather) 创建机器人，获取 `BOT_TOKEN`
2. 通过 [@userinfobot](https://t.me/userinfobot) 获取你的 `OWNER_ID`
3. 设置以下环境变量：

```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
OWNER_ID=123456789
BASE_URL=https://your-app.up.railway.app
```

4. 将机器人添加为所有需要同步的群组的管理员
5. 使用 `/addgroup` 或 `/addall` 添加同步群组

---

## 用户账户模式

### 工作原理

**不设置** `BOT_TOKEN` 环境变量（或将其留空），机器人将以普通用户账号身份登录 Telegram。用户账号可以接收群内所有消息，包括其他机器人发送的内容。

### 获取 Session 字符串

Pyrogram 支持使用 **Session 字符串** 进行用户账号认证，无需在服务器上输入手机号验证码。

#### 方法：本地生成 Session 字符串

1. 在本地机器上安装 Python 和 Pyrogram：

   ```bash
   pip install pyrogram tgcrypto
   ```

2. 访问 [`my.telegram.org`](https://my.telegram.org)，登录后进入 "API development tools"，创建应用获取 `api_id` 和 `api_hash`

3. 运行以下脚本生成 Session 字符串：

   ```python
   from pyrogram import Client

   api_id = 12345678       # 替换为你的 api_id
   api_hash = "your_api_hash"  # 替换为你的 api_hash

   with Client("my_account", api_id=api_id, api_hash=api_hash) as app:
       print(app.export_session_string())
   ```

4. 按提示输入手机号和验证码完成登录，脚本会输出 Session 字符串（一长串字符）

5. 将生成的 Session 字符串保存好，后续配置使用

### 配置步骤

1. 按上述方式获取 Session 字符串和 API 凭证

2. 设置以下环境变量（**不要**设置 `BOT_TOKEN`）：

```env
# 不设置 BOT_TOKEN，或留空
# BOT_TOKEN=

API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
SESSION_STRING=BQA...（你的 Session 字符串）

OWNER_ID=123456789
BASE_URL=https://your-app.up.railway.app
```

3. 修改 `bot.py` 中的 Client 初始化代码，使用 `session_string` 参数：

```python
app_tg = Client(
    "tg_sync_bot",
    api_id=api_id,
    api_hash=api_hash,
    session_string=os.getenv("SESSION_STRING", None),
    # bot_token 不设置，即可使用用户账号模式
)
```

4. 确保该用户账号已加入所有需要同步的群组
5. 使用 `/addgroup` 或 `/addall` 添加同步群组

### 用户账户模式的注意事项

- **账号安全**：Session 字符串相当于账号的登录凭证，请妥善保管，不要泄露给他人
- **封号风险**：频繁转发消息可能触发 Telegram 的反垃圾机制，建议控制同步的群组数量
- **管理员权限**：用户账号不需要额外申请管理员权限，但消息同步仍需账号在对应群组中
- **Session 过期**：如果账号在其他设备上注销，Session 字符串会失效，需要重新生成

---

## 环境变量速查

### Bot 账户模式所需变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `BOT_TOKEN` | ✅ | 机器人 Token（@BotFather 获取） |
| `OWNER_ID` | ✅ | 主人用户 ID |
| `BASE_URL` | ✅ | 后台访问地址 |
| `REDIS_URL` | ⚡ | Redis 连接（Railway 自动注入） |
| `API_ID` | ⚡ | 可选，默认使用 Pyrogram 内置 API |
| `API_HASH` | ⚡ | 可选，默认使用 Pyrogram 内置 API |

### 用户账户模式所需变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `BOT_TOKEN` | ❌ | **不设置**此变量 |
| `API_ID` | ✅ | 你的 Telegram API ID |
| `API_HASH` | ✅ | 你的 Telegram API Hash |
| `SESSION_STRING` | ✅ | 用户账号 Session 字符串 |
| `OWNER_ID` | ✅ | 主人用户 ID |
| `BASE_URL` | ✅ | 后台访问地址 |
| `REDIS_URL` | ⚡ | Redis 连接（Railway 自动注入） |

---

## 常见问题

### Q：为什么 Bot 模式无法同步其他机器人的消息？

这是 Telegram 平台的设计限制，不是代码问题。Bot 账号之间默认不会互相推送消息，目的是防止机器人之间形成消息循环和垃圾消息。详见 [Telegram Bot API 文档](https://core.telegram.org/bots/faq#why-doesn-39t-my-bot-see-messages-from-other-bots)。

### Q：用户账户模式会被封号吗？

存在一定风险。Telegram 对自动化账号有监控机制，频繁操作可能导致账号被限制或封禁。建议：
- 使用专用小号，不要用主账号
- 控制同步的群组数量
- 避免高频率消息转发

### Q：Session 字符串泄露了怎么办？

立即在 Telegram 的 **设置 → 隐私和安全 → 活跃会话** 中终止对应的 Session，然后重新生成新的 Session 字符串。

### Q：如何从 Bot 模式切换到用户账户模式？

1. 删除 `BOT_TOKEN` 环境变量（或置空）
2. 添加 `API_ID`、`API_HASH`、`SESSION_STRING` 环境变量
3. 修改 `bot.py` 中的 Client 初始化代码（见上文）
4. 重新部署应用
