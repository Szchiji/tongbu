# Telegram 群组同步机器人

一个支持多群组消息同步、强制频道关注验证、多管理员管理、**Web 管理后台**的 Telegram 机器人，专为 Railway 平台部署优化。

## 功能特性

- ✅ **无限群组同步**：支持添加无限数量的群组进行消息同步
- ✅ **数据持久化**：自动保存群组列表、管理员列表和频道配置到 JSON 文件
- ✅ **消息实时同步**：同步新消息、编辑消息和删除消息
- ✅ **隐藏消息引用**：同步消息时不显示"转发自..."来源信息
- ✅ **支持同步机器人消息**：使用用户账号模式可同步其他机器人发送的内容
- ✅ **强制频道关注**：新成员加群时自动禁言，关注指定频道后解禁
- ✅ **多管理员支持**：支持动态添加/删除管理员
- ✅ **Web 管理后台**：通过 Web 界面管理群组、频道和管理员（无需密码）
- ✅ **Web Service 模式**：内置 Flask 服务器，支持 Railway/Render 等平台部署
- ✅ **动态过滤器**：支持运行时动态添加群组，无需重启

## Railway 部署指南

### 前置要求

1. Telegram API 凭证：
   - 通过 [@BotFather](https://t.me/BotFather) 创建机器人获取 `BOT_TOKEN`
   - 获取你的用户 ID 作为 `OWNER_ID`（可通过 [@userinfobot](https://t.me/userinfobot) 获取）
   - **无需** 获取 `API_ID` 和 `API_HASH`，机器人使用 Pyrogram 内置的默认 API

2. Railway 账号：访问 https://railway.app 注册账号

### 部署步骤

#### 方法 1：使用 GitHub 仓库部署

1. Fork 或克隆本仓库到你的 GitHub 账号
2. 登录 Railway 控制台
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择你的仓库
5. 添加 Redis 数据库：
   - 在项目中点击 "+ New" → "Database" → "Add Redis"
   - Railway 会自动将 `REDIS_URL` 注入到环境变量中
6. 添加以下环境变量：
   - `BOT_TOKEN`：你的机器人 Token
   - `OWNER_ID`：你的 Telegram 用户 ID
   - `BASE_URL`：你的应用访问地址（如 `https://tongbu-xxx.up.railway.app`）
   - `SECRET_KEY`：（可选）Flask Session 密钥，不填会自动生成
   - `PORT`：Railway 会自动注入，无需手动设置
   - `REDIS_URL`：Railway 添加 Redis 后会自动注入，无需手动设置
7. 点击 "Deploy"

#### 方法 2：使用 Railway CLI 部署

```bash
# 安装 Railway CLI
npm i -g @railway/cli

# 登录
railway login

# 初始化项目
railway init

# 添加环境变量
railway variables set BOT_TOKEN=你的BOT_TOKEN
railway variables set OWNER_ID=你的用户ID
railway variables set BASE_URL=https://你的应用地址.up.railway.app

# 部署
railway up
```

### 环境变量说明

| 变量名 | 必需 | 说明 | 示例 |
|--------|------|------|------|
| `BOT_TOKEN` | ✅ | 机器人 Token | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `OWNER_ID` | ✅ | 主人用户 ID | `123456789` |
| `BASE_URL` | ✅ | 后台访问地址（用于 Web 管理后台） | `https://tongbu-xxx.up.railway.app` |
| `SECRET_KEY` | ⚡ | Flask Session 密钥（可选，不填自动生成） | `random_secret_key_here` |
| `REDIS_URL` | ⚠️ | Redis 数据库连接 URL（Railway 自动注入） | `redis://default:password@host:port` |
| `PORT` | ⚠️ | HTTP 服务端口（Railway 自动注入） | `10000` |
| `API_ID` | ⚡ | Telegram API ID（可选，高级配置） | `12345678` |
| `API_HASH` | ⚡ | Telegram API Hash（可选，高级配置） | `0123456789abcdef0123456789abcdef` |

**注意**：
- `REDIS_URL` 环境变量在 Railway 部署时会自动注入。如果不存在此变量，机器人会回退到使用本地 JSON 文件存储数据（适用于本地测试）。
- `BASE_URL` 用于生成 Web 管理后台的访问链接，部署后可在 Railway 项目设置中查看你的应用地址。

### 高级配置：自定义 API_ID 和 API_HASH

机器人默认使用 Pyrogram 官方测试 API（`API_ID=6`），无需额外配置即可运行。

如果你需要使用自己的 API 凭证（推荐用于生产环境），可以：

1. 访问 https://my.telegram.org 登录你的 Telegram 账号
2. 进入 "API development tools"
3. 创建应用，获取 `api_id` 和 `api_hash`
4. 在 Railway 环境变量中设置 `API_ID` 和 `API_HASH`

**注意**：使用官方默认 API 可能存在速率限制，生产环境建议配置自己的 `API_ID` 和 `API_HASH`。

## 使用说明

### 管理员命令

所有命令需要在机器人私聊中使用：

#### 群组管理
- `/addgroup -100群ID` - 添加单个群组到同步列表
- `/removegroup -100群ID` - 从同步列表移除群组
- `/addall` - 自动添加机器人所在的所有群组
- `/status` - 查看当前同步群组数量和配置

#### 管理员管理
- `/addadmin 用户ID` 或 `/addadmin @用户名` - 添加管理员
- `/deladmin 用户ID` - 删除管理员（不能删除主人）
- `/listadmins` - 查看管理员列表

#### 频道管理
- `/setchannel @频道1 @频道2` - 设置强制关注的频道列表
- `/setchannel` - 清空强制关注频道列表

#### Web 管理后台
- `/admin` - 获取 Web 管理后台访问链接（仅管理员可用）
  - 生成一次性访问令牌（5分钟有效）
  - 通过 Web 界面管理群组、频道和管理员
  - 无需密码，通过 Telegram 身份验证

### Web 管理后台

Web 管理后台提供了友好的图形界面来管理机器人，支持移动端访问。

#### 访问方式

1. 私聊机器人发送 `/admin` 命令
2. 点击返回的按钮进入管理后台
3. 链接包含一次性令牌，5分钟内有效
4. 登录后保持会话，无需重复验证

**重要提示**：
- 只有在 `ADMINS` 列表中的用户才能访问管理后台
- 非管理员发送 `/admin` 命令时，机器人不会有任何回复（静默忽略）
- 必须配置 `BASE_URL` 环境变量才能使用此功能
- 需要 Redis 数据库支持（用于存储临时令牌）

#### 功能页面

**📊 仪表盘**
- 查看系统概览（群组数、频道数、管理员数）
- 快速访问各管理页面

**👥 群组管理**
- 添加/删除同步群组
- 查看所有已添加的群组列表
- 提示：批量添加建议使用 `/addall` 命令

**📢 频道管理**
- 添加/删除强制关注频道
- 查看所有强制频道列表
- 一键清空所有频道

**👤 管理员管理**
- 添加/删除管理员（通过用户 ID）
- 查看所有管理员列表
- OWNER 用户不可删除
- 提示：添加用户名需使用 `/addadmin @username` 命令

**🚪 退出登录**
- 清除会话，退出管理后台

#### 界面特性
- 🌙 深色主题设计
- 📱 响应式布局，支持手机访问
- 🎨 卡片式界面，操作直观
- ⚠️ 危险操作有确认提示
- ✅ 操作结果实时反馈

### 获取群组 ID

1. 将机器人添加到目标群组
2. 转发群组中的任意消息到 [@userinfobot](https://t.me/userinfobot)
3. 机器人会返回包含群组 ID 的信息（格式通常为 `-100xxxxxxxxxx`）

### 工作流程

1. **添加群组**：使用 `/addgroup` 命令添加要同步的群组
2. **设置频道**（可选）：使用 `/setchannel` 设置强制关注的频道
3. **自动同步**：
   - 在任何同步群组中发送的消息会自动转发到其他群组
   - 编辑和删除操作也会同步
   - 未关注频道的用户消息会被自动删除

## 数据持久化

机器人支持两种数据持久化方式：

### Redis 数据库（推荐用于生产环境）
当 `REDIS_URL` 环境变量存在时（如在 Railway 部署），机器人会使用 Redis 数据库存储以下数据：
- 同步群组列表 (`SYNC_GROUPS`)
- 强制关注频道列表 (`REQUIRED_CHANNELS`)
- 管理员列表 (`ADMINS`)

在 Railway 部署时：
1. 点击项目中的 "+ New" → "Database" → "Add Redis"
2. Railway 会自动将 Redis 服务的 `REDIS_URL` 注入到应用环境变量中
3. 无需手动配置，机器人会自动使用 Redis 存储数据
4. 数据会在重启和重新部署后保持不丢失

### JSON 文件（用于本地测试）
当 `REDIS_URL` 环境变量不存在时，机器人会回退到使用本地 `bot_data.json` 文件存储数据。这适用于本地开发和测试环境。

重启后数据会自动加载，无需重新配置。

## 技术特性

- **动态过滤器**：运行时添加群组即时生效，无需重启
- **正确的回调签名**：`on_deleted_messages` 使用正确的 `(client, messages)` 签名
- **异常处理**：所有异常都有具体类型和日志记录
- **标准日志**：使用 Python logging 模块，便于调试和监控
- **健康检查**：内置 HTTP 端点供平台健康检查

## 故障排查

### 机器人无法启动
- 检查环境变量是否正确设置
- 查看 Railway 日志确认错误信息
- 确认 BOT_TOKEN 有效

### 消息不同步
- 确认群组已添加到同步列表（使用 `/status` 检查）
- 确认机器人在所有目标群组中都是管理员
- 检查机器人是否有发送消息权限

### 其他机器人的消息不同步
**重要说明**：这是 Telegram 平台的限制，不是代码问题。

当以 **Bot 账号** 运行时（设置了 `BOT_TOKEN`），Telegram 不会将其他机器人发送的消息传递给您的机器人。这是 Telegram 的设计，用于防止机器人之间的垃圾消息循环。

**解决方案**：
1. **使用用户账号模式（推荐）**：不设置 `BOT_TOKEN` 环境变量，改用用户账号登录。这样可以接收并同步其他机器人发送的消息，且同步时会隐藏消息来源。
2. **接受限制**：如果必须使用 Bot 账号，则只能同步普通用户发送的消息，无法同步其他机器人的消息。

**关于消息引用**：本机器人使用 `copy()` 方法同步消息，同步后的消息不会显示"转发自..."的来源信息，保持消息整洁。

### 用户无法解禁
- 确认用户已关注所有设置的频道
- 确认机器人在群组中有禁言/解禁权限
- 检查频道用户名格式（应为 `@channelname`）

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

本项目采用 MIT 许可证。

## 支持

如有问题，请在 GitHub Issues 中提出。
