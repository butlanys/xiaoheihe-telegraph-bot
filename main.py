#!/usr/bin/env python3
"""
小黑盒解析姬 — Telegram Bot
通过 WARP 代理解析小黑盒分享链接，上传到 Telegraph
"""

import os
import logging
import html as html_mod
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from xiaoheihe import process_share, parse_link_id

# ====== 配置 ======

TOKEN = os.environ.get("BOT_TOKEN", "")
WARP_PROXY = os.environ.get("WARP_PROXY", "socks5://127.0.0.1:40000")
DEBUG = os.environ.get("DEBUG", "0") == "1"

# ====== 日志 ======

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO,
)
logger = logging.getLogger("xiaoheihe-bot")


# ====== 处理器 ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """欢迎消息"""
    await update.message.reply_text(
        "👋 你好！我是小黑盒解析姬~\n\n"
        "📌 发送小黑盒分享链接，我会解析内容并上传到 Telegraph\n"
        "👥 支持群组使用"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助"""
    await update.message.reply_text(
        "🔍 **使用说明**\n\n"
        "直接发送小黑盒分享链接即可，例如：\n"
        "`https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?link_id=xxx`\n\n"
        "也支持纯 link_id\n"
        "支持群组中使用"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户消息"""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_type = update.message.chat.type if update.message.chat else "private"
    user_info = update.effective_user
    user_name = user_info.full_name if user_info else "未知用户"

    # 检查是否包含小黑盒链接
    link_id = parse_link_id(text)

    # 私聊也支持纯 link_id（8位以上十六进制）
    if not link_id and chat_type == 'private':
        m = re.search(r'([a-f0-9]{8,})', text, re.IGNORECASE)
        if m:
            link_id = m.group(1)

    if not link_id:
        # 群组中不回复无关消息
        if chat_type != "private":
            return
        await update.message.reply_text("❌ 未识别到小黑盒链接，请发送分享链接或 link_id")
        return

    logger.info(f"[{chat_type}] {user_name}: link_id={link_id}")

    # 发送正在处理
    status_msg = await update.message.reply_text("⏳ 正在解析...")

    try:
        result = process_share(text)

        # 成功回复（用 HTML parse_mode，避免标题/作者里的 _ * ` 等字符破坏 Markdown 解析）
        reply = (
            f"✅ <b>解析成功！</b>\n\n"
            f"📌 <b>{html_mod.escape(result['title'])}</b>\n"
            f"👤 作者：{html_mod.escape(result['author'])}\n"
            f"💬 评论：{result['comments']} 条\n\n"
            f"🔗 {html_mod.escape(result['url'])}"
        )

        # 添加按钮
        keyboard = [[
            InlineKeyboardButton("📖 打开 Telegraph", url=result['url'])
        ]]

        try:
            await status_msg.edit_text(
                reply,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        except Exception:
            # 兜底：纯文本发送，避免任何解析错误
            plain = (
                f"✅ 解析成功！\n\n"
                f"📌 {result['title']}\n"
                f"👤 作者：{result['author']}\n"
                f"💬 评论：{result['comments']} 条\n\n"
                f"🔗 {result['url']}"
            )
            await status_msg.edit_text(
                plain,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=DEBUG)
        error_msg = str(e)
        try:
            await status_msg.edit_text(f"❌ 解析失败: {error_msg}")
        except Exception:
            await status_msg.edit_text("❌ 解析失败，请稍后再试")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理"""
    logger.error(f"更新异常: {context.error}", exc_info=context.error)


def main():
    if not TOKEN:
        logger.error("请设置 BOT_TOKEN 环境变量")
        return

    # 创建 Application
    app = Application.builder().token(TOKEN).build()

    # 注册处理器
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    # 处理所有文本消息（群组和私聊）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 错误处理
    app.add_error_handler(error_handler)

    logger.info("小黑盒解析姬 Bot 启动中...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
