# Telegram 群组同步机器人

一个支持多群组消息同步、强制频道关注验证、多管理员管理的 Telegram 机器人，专为 Railway 平台部署优化。

## 功能特性

- ✅ **无限群组同步**：支持添加无限数量的群组进行消息同步
- ✅ **数据持久化**：自动保存群组列表、管理员列表和频道配置到 JSON 文件
- ✅ **消息实时同步**：同步新消息、编辑消息和删除消息
- ✅ **强制频道关注**：新成员加群时自动禁言，关注指定频道后解禁
- ✅ **多管理员支持**：支持动态添加/删除管理员
- ✅ **Web 管理后台**：可视化界面管理群组、频道、管理员，支持 Telegram 身份验证
- ✅ **Web Service 模式**：内置 Flask 服务器，支持 Railway/Render 等平台部署
- ✅ **动态过滤器**：支持运行时动态添加群组，无需重启

## Railway 部署指南

### 前置要求

1. Telegram API 凭证：
   - 访问 https://my.telegram.org/apps 获取 `API_ID` 和 `API_HASH`
   - 通过 [@BotFather](https://t.me/BotFather) 创建机器人获取 `BOT_TOKEN`
   - 获取你的用户 ID 作为 `OWNER_ID`（可通过 [@userinfobot](https://t.me/userinfobot) 获取）

2. Railway 账号：访问 https://railway.app 注册账号

### 部署步骤

#### 方法 1：使用 GitHub 仓库部署

1. Fork 或克隆本仓库到你的 GitHub 账号
2. 登录 Railway 控制台
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择你的仓库
5. 添加以下环境变量：
   - `API_ID`：你的 Telegram API ID
   - `API_HASH`：你的 Telegram API Hash
   - `BOT_TOKEN`：你的机器人 Token
   - `OWNER_ID`：你的 Telegram 用户 ID
   - `BASE_URL`：你的 Railway 应用地址（部署后在项目设置中获取）
   - `PORT`：Railway 会自动注入，无需手动设置
6. 添加 Redis 数据库（用于 Web 管理后台）：
   - 在项目页面点击 "New" → "Database" → "Add Redis"
   - Railway 会自动添加 `REDIS_URL` 环境变量
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
railway variables set API_ID=你的API_ID
railway variables set API_HASH=你的API_HASH
railway variables set BOT_TOKEN=你的BOT_TOKEN
railway variables set OWNER_ID=你的用户ID

# 部署
railway up
```

### 环境变量说明

| 变量名 | 必需 | 说明 | 示例 |
|--------|------|------|------|
| `API_ID` | ✅ | Telegram API ID | `12345678` |
| `API_HASH` | ✅ | Telegram API Hash | `0123456789abcdef0123456789abcdef` |
| `BOT_TOKEN` | ✅ | 机器人 Token | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `OWNER_ID` | ✅ | 主人用户 ID | `123456789` |
| `BASE_URL` | ✅ | Web 管理后台访问地址 | `https://xxx.up.railway.app` |
| `REDIS_URL` | ✅ | Redis 连接地址（用于 Web 后台身份验证） | `redis://red-xxx:6379` |
| `SECRET_KEY` | ⚠️ | Flask Session 密钥（可选，不填自动生成） | `随机字符串` |
| `PORT` | ⚠️ | HTTP 服务端口（Railway 自动注入） | `10000` |

**注意：** 如需使用 Web 管理后台，`BASE_URL` 和 `REDIS_URL` 必须配置。Railway 平台可以在 Plugins 中添加 Redis 数据库。

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
  - **注意：** 非管理员发送此命令时，机器人不会有任何回复（静默忽略）
  - 链接 5 分钟内有效，使用后会自动创建登录会话

### Web 管理后台功能

通过 `/admin` 命令获取访问链接后，可以使用以下功能：

#### 🖥️ 仪表盘
- 查看同步群组数量、强制频道数量、管理员数量
- 快速访问各管理页面
- 查看最近添加的群组

#### 📋 群组管理
- 添加单个群组到同步列表
- 一键添加所有群组
- 删除指定群组
- 查看所有同步群组列表

#### 📡 频道管理
- 添加强制关注频道
- 删除指定频道
- 清空所有频道
- 查看所有强制关注频道

#### 👥 管理员管理
- 添加新管理员（通过用户 ID）
- 删除管理员（不能删除主人）
- 查看所有管理员列表

### 使用 Web 管理后台

1. **获取访问链接**：私聊机器人，发送 `/admin` 命令
2. **点击按钮**：点击返回消息中的 "🖥️ 进入管理后台" 按钮
3. **开始管理**：在浏览器中使用可视化界面管理机器人
4. **退出登录**：点击顶部导航栏的 "退出登录" 或关闭浏览器

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

机器人会自动将以下数据保存到 `bot_data.json` 文件：
- 同步群组列表 (`SYNC_GROUPS`)
- 强制关注频道列表 (`REQUIRED_CHANNELS`)
- 管理员列表 (`ADMINS`)

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
- 确认 API_ID、API_HASH 和 BOT_TOKEN 有效

### 消息不同步
- 确认群组已添加到同步列表（使用 `/status` 检查）
- 确认机器人在所有目标群组中都是管理员
- 检查机器人是否有发送消息权限

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
