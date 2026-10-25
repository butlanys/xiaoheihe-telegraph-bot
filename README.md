# 小黑盒解析姬 (xiaoheihe-telegraph-bot)

一个类似「bilibili 解析姬」的 Telegram 机器人：把**小黑盒（xiaoheihe.cn）分享链接**解析成
干净的 **Telegraph 页面**——正文、**原文行内位置的图片（原图）**、以及**热门评论（含评论图片）**。

支持**群组**和**私聊**使用。

## ✨ 功能特性

- 📄 **正文完整提取** — 兼容小黑盒多种帖子格式（JSON 块数组 / 内嵌 HTML / `type=html`）
- 🖼️ **图片保持在原文行内位置** — 不会被堆到文末
- 🔍 **原图质量** — 自动把 CDN 缩略图 URL 还原为原图（体积 1~3 倍，压缩更少）
- 💬 **评论解析** — 前 15 条热门评论，每条带最多 5 条回复，支持 @提及 / 游戏链接
- 🖼️ **评论图片** — 渲染评论对象 `imgs` 字段中的图片
- 😀 **小黑盒 cube 表情** → Unicode emoji 映射
- 🔐 **hkey v2 签名** — 适配 2026 年新版小黑盒 API 签名算法
- 🌐 **双通道网络** — WARP SOCKS5 / 直连自动 failover，配合 Cookie 认证规避限频
- 🐳 **Docker 一键部署**

## 🚀 快速开始

### 1. 获取必要凭据

| 凭据 | 获取方式 |
|------|----------|
| `BOT_TOKEN` | Telegram [@BotFather](https://t.me/BotFather) 创建机器人 |
| `TELEGRAPH_TOKEN` | `curl -s 'https://api.telegra.ph/createAccount?short_name=xhh&author_name=xhh'` 取 `result.access_token` |
| `XHH_TOKEN` | 浏览器打开 xiaoheihe.cn，F12 → 任意 API 请求 → Cookie 里的 `x_xhh_tokenid` 值 |

> `XHH_TOKEN` 强烈建议配置：小黑盒的 `show_captcha` 限频主要针对**未认证**请求，
> 带上 Cookie 后直连即可稳定工作。

### 2. 配置

```bash
cp .env.example .env
vim .env          # 填入上面的三个 token
```

### 3. 运行

**Docker（推荐）**

```bash
docker compose up -d --build
docker compose logs -f
```

**本地运行**

```bash
pip install -r requirements.txt
export BOT_TOKEN=... XHH_TOKEN=... TELEGRAPH_TOKEN=...
python3 main.py
```

### 4. 使用

- 私聊：发送小黑盒分享链接，或直接发 `link_id`（8 位以上十六进制）
- 群组：发送包含小黑盒链接的消息（非小黑盒链接不响应，避免误触发）

```
https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=xxxxxxxxxxxx
```

机器人会回复 Telegraph 页面链接。

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BOT_TOKEN` | Telegram Bot Token（**必填**） | — |
| `TELEGRAPH_TOKEN` | Telegraph access_token（**必填**） | — |
| `XHH_TOKEN` | 小黑盒 `x_xhh_tokenid` Cookie（**强烈建议**） | 空 |
| `PROXY_MODE` | `warp` / `direct` / `auto` | `direct` |
| `WARP_PROXY` | WARP SOCKS5 地址 | `socks5://127.0.0.1:40000` |
| `TZ` | 时区 | `Asia/Shanghai` |
| `DEBUG` | `1` 输出调试日志 | `0` |

## 🧠 工作原理

```
用户/群组 → Telegram Bot(polling)
                │
                ├─ hkey v2 签名 ──→ 小黑盒 API /bbs/app/link/tree
                │                      （文章 + 评论）
                ├─ /bbs/app/comment/sub/comments（补齐回复）
                │
                └─ 内容 → Telegraph Node 结构 ──→ api.telegra.ph/createPage
```

### 关键点

**hkey v2 签名**（2026 新版，`xiaoheihe.py` 内联实现）
字符集 `AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89`，由 timestamp / 规范化路径 / nonce
三个分量交错混淆后取 MD5 派生。详见源码 `get_hkey()`。

**原图还原**：小黑盒 CDN 图片有两级地址——

```
缩略图: https://imgheybox1.max-c.com/bbs/2026/07/18/<hash>/thumb.png?imageMogr2/...thumbnail/850x1450%3E
原图:   https://imgheybox1.max-c.com/bbs/2026/07/18/<hash>.png
```

去掉查询参数 + 去掉路径中的 `/thumb` 段即可拿到原图（扩展名保持不变）。

**Telegraph Node**：Telegraph API 不接受 Markdown，所有内容以 Node 结构提交，
链接用 `{"tag":"a","attrs":{"href":...}}`，图片用 `{"tag":"img","attrs":{"src":...}}`。

## 📁 项目结构

```
.
├── main.py             # Telegram Bot 入口（消息处理）
├── xiaoheihe.py        # 核心：hkey 签名 + API 客户端 + 内容解析 + Telegraph 上传
├── hkey_v2.py          # hkey v2 算法独立参考实现
├── hkey.py             # hkey 旧版算法（存档参考）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## ⚠️ 已知限制

- **限频**：小黑盒对未认证请求有 IP 级限频（返回 `{"status":"show_captcha"}`，
  注意这只是频率限制，**没有需要人工过的验证码**）。配置 `XHH_TOKEN` 后基本不受影响。
- **图片托管**：Telegraph 会抓取并转存图片，图片较多的长文页面生成稍慢。
- **评论数量**：默认前 15 条主评论 + 每条最多 5 条回复，可在 `build_telegraph_content()`
  里调整 `max_top_level` / `max_replies`。
- **WARP**：公共 WARP IP 池较小且易被整体限频，因此默认推荐 `direct` + Cookie。

## 📜 免责声明

本项目仅供**个人学习与技术研究**使用。使用者应遵守小黑盒、Telegram、Telegraph
各自的服务条款及当地法律法规，不得用于任何商业用途或大规模抓取。
因使用本项目产生的一切后果由使用者自行承担。

## 📄 License

[MIT](LICENSE)
