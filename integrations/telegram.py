"""
Agent Smith - Telegram Bot (Async v4.3).
Long message split, Markdown to HTML, 429/400 handling.
"""
import json
import logging
import asyncio
import httpx
import time
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger("telegram-bot")

# Telegram max message length
TG_MAX_LENGTH = 4000


def md_to_html(text: str) -> str:
    """Convert Markdown to Telegram-safe HTML."""
    # Escape HTML first
    result = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold **text**
    result = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', result)
    # Italic *text*
    result = re.sub(r'\*(.+?)\*', r'<i>\1</i>', result)
    # Inline code
    result = re.sub(r'`(.+?)`', r'<code>\1</code>', result)
    # Links [text](url)
    result = re.sub(r'\[(.+?)\]\((https?://[^\)]+)\)', r'<a href="\2">\1</a>', result)
    # Fix nested <i> inside <b> -> <b><i></i></b>
    result = result.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    result = result.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    result = result.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    return result


def split_long_text(text: str, max_len: int = TG_MAX_LENGTH) -> List[str]:
    """Split long text into Telegram-safe chunks at line boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current.strip())
            # If single line is too long, hard-split it
            while len(line) > max_len:
                chunks.append(line[:max_len])
                line = line[max_len:]
            current = line
        else:
            current += "\n" + line if current else line
    if current:
        chunks.append(current.strip())
    return chunks


class TelegramBot:
    def __init__(self, token: str, chat_id: str = None):
        self.token = token
        self.chat_id = chat_id
        self.api_url = "https://api.telegram.org/bot" + token
        self._offset = 0
        self._running = False
        self.client = httpx.AsyncClient(timeout=60.0)

    async def get_me(self) -> bool:
        try:
            resp = await self.client.get(self.api_url + "/getMe")
            if resp.status_code == 200:
                data = resp.json()
                logger.info("Telegram: @" + data["result"]["username"])
                return True
            return False
        except Exception as e:
            logger.error("Auth error: " + str(e))
            return False

    async def send_message(self, text: str, chat_id: str = None, **kwargs) -> dict:
        try:
            target = chat_id or self.chat_id
            if not target:
                return {}
            payload = {"chat_id": target, "text": text, "parse_mode": "HTML"}
            payload.update(kwargs)
            resp = await self.client.post(self.api_url + "/sendMessage", json=payload)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 3))
                logger.warning("429 send_message, wait " + str(retry_after) + "s")
                await asyncio.sleep(retry_after)
                resp = await self.client.post(self.api_url + "/sendMessage", json=payload)

            if resp.status_code == 400:
                # Try without HTML parse
                payload["parse_mode"] = None
                resp = await self.client.post(self.api_url + "/sendMessage", json=payload)

            return resp.json()
        except Exception as e:
            logger.error("Send failed: " + str(e))
            return {}

    async def edit_message(self, text: str, message_id: int, chat_id: str = None) -> dict:
        try:
            target = chat_id or self.chat_id
            resp = await self.client.post(self.api_url + "/editMessageText",
                json={"chat_id": target, "message_id": message_id, "text": text, "parse_mode": "HTML"})

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 3))
                await asyncio.sleep(retry_after)
                resp = await self.client.post(self.api_url + "/editMessageText",
                    json={"chat_id": target, "message_id": message_id, "text": text, "parse_mode": "HTML"})

            if resp.status_code == 400:
                logger.warning("400 edit, len=" + str(len(text)))

            return resp.json()
        except Exception as e:
            logger.error("Edit failed: " + str(e))
            return {}

    async def send_long_message(self, text: str, chat_id: str = None) -> dict:
        """Send a long message, splitting into multiple if needed."""
        chunks = split_long_text(text)
        result = {}
        for i, chunk in enumerate(chunks):
            result = await self.send_message(chunk, chat_id)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)  # small delay between parts
        return result

    async def send_chat_action(self, action: str = "typing", chat_id: str = None):
        try:
            await self.client.get(self.api_url + "/sendChatAction?chat_id=" +
                                  str(chat_id or self.chat_id) + "&action=" + action)
        except:
            pass

    async def get_updates(self, timeout: int = 30) -> list:
        try:
            resp = await self.client.get(self.api_url + "/getUpdates",
                                         params={"offset": self._offset, "timeout": timeout})
            return resp.json().get("result", [])
        except Exception as e:
            await asyncio.sleep(2)
            return []

    async def process_updates(self, agent):
        if not await self.get_me():
            logger.error("Bot unauthorized")
            return

        self._running = True
        logger.info("Bot listening...")

        while self._running:
            updates = await self.get_updates()
            for update in updates:
                self._offset = update["update_id"] + 1
                if "message" in update:
                    asyncio.create_task(self._handle_message(agent, update["message"]))

    async def _handle_message(self, agent, msg):
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")
        if not text:
            return

        await self.send_chat_action("typing", chat_id)

        # FIX: no initial placeholder - agent sends progress as it goes
        msg_id = None
        full_response = ""
        last_ui_update = 0
        last_sent_text = ""
        sent_message = False  # track if we need to send final as new message

        try:
            async for chunk in agent.process_message_stream(text):
                content = chunk.get("content")
                if content:
                    full_response += content

                now = time.time()
                if now - last_ui_update > 2.5 and full_response.strip():
                    display = md_to_html(full_response[:3500])
                    if display.strip() != last_sent_text:
                        if msg_id:
                            await self.edit_message(display + " |", msg_id, chat_id)
                        elif not sent_message and len(full_response) > 200:
                            # Send first preview message
                            sent = await self.send_message(display + " |", chat_id)
                            msg_id = sent.get("result", {}).get("message_id")
                            sent_message = True
                        last_sent_text = display.strip()
                        last_ui_update = now

            # Final render
            final_display = md_to_html(full_response)
            if len(final_display) > TG_MAX_LENGTH:
                # Long response: send as multiple messages
                if msg_id:
                    await self.edit_message(final_display[:TG_MAX_LENGTH], msg_id, chat_id)
                    rest = final_display[TG_MAX_LENGTH:]
                    chunks = split_long_text(rest)
                    for chunk in chunks:
                        await self.send_message(chunk, chat_id)
                        await asyncio.sleep(0.3)
                else:
                    await self.send_long_message(final_display, chat_id)
            elif msg_id and final_display.strip() != last_sent_text:
                await self.edit_message(final_display, msg_id, chat_id)
            elif not msg_id:
                await self.send_message(final_display, chat_id)

        except Exception as e:
            logger.error("Handler error: " + str(e))
            await self.send_message("Error: " + str(e)[:300], chat_id)

    async def stop(self):
        self._running = False
        await self.client.aclose()