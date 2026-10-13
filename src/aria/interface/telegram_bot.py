from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


class TelegramInterface:
    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        on_user_message: Callable[[str], Awaitable[str]],
        on_status: Callable[[], Awaitable[str]],
        on_health: Callable[[], Awaitable[str]],
        on_goal: Callable[[str], Awaitable[str]],
    ) -> None:
        self._chat_id = str(chat_id)
        self._on_user_message = on_user_message
        self._on_status = on_status
        self._on_health = on_health
        self._on_goal = on_goal
        self._app: Application = ApplicationBuilder().token(token).build()
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("health", self._handle_health))
        self._app.add_handler(CommandHandler("goal", self._handle_goal))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        assert self._app.updater is not None
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        assert self._app.updater is not None
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    async def send_message(self, text: str) -> None:
        await self._app.bot.send_message(chat_id=self._chat_id, text=text)

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.text is None:
            return
        if str(update.effective_chat.id) != self._chat_id:
            return
        reply = await self._on_user_message(update.message.text)
        await update.message.reply_text(reply)

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if str(update.effective_chat.id) != self._chat_id:
            return
        reply = await self._on_status()
        await update.message.reply_text(reply)

    async def _handle_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if str(update.effective_chat.id) != self._chat_id:
            return
        reply = await self._on_health()
        await update.message.reply_text(reply)

    async def _handle_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if str(update.effective_chat.id) != self._chat_id:
            return
        text = update.message.text or ""
        goal_text = text.removeprefix("/goal").strip()
        reply = await self._on_goal(goal_text)
        await update.message.reply_text(reply)
