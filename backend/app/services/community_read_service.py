"""Owned-community message reading across Discord, Slack and Telegram.

Backs the ``community_read`` tool for the ``community`` squad. The platform is a
tool argument dispatching to one of three adapters below — the same seam shape
as ``PaymentProvider`` / ``EmailProvider`` / the LLM adapters, so adding a
fourth platform is one function and one registry line, with no change to the
tool, the prompt, or the directive parser.

Each adapter normalizes into the same ``Message`` shape, so the squad's members
never learn which platform they are reading. Message text is user-generated and
injection-scanned per item before it reaches the model.

**Telegram is genuinely weaker than the other two and says so.** The Bot API has
no "fetch this channel's history" call; ``getUpdates`` returns only what has
recently been delivered to the bot itself. The result header states this, so the
agent reports a partial window rather than presenting it as complete.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.constants import (
    COMMUNITY_CHANNEL_PATTERN,
    COMMUNITY_PLATFORMS,
    COMMUNITY_READ_ITEM_MAX_CHARS,
    COMMUNITY_READ_RESULT_CLOSE,
    COMMUNITY_READ_RESULT_OPEN,
    CONNECTED_DEFAULT_WINDOW,
    CONNECTED_TOOL_MISSING_KEY_NOTICE,
    CONNECTED_WINDOWS,
    DISCORD_API_BASE_URL,
    SLACK_API_BASE_URL,
    TELEGRAM_API_BASE_URL,
    LLMProvider,
)
from app.services.connected_common import (
    drop_suspicious,
    failure,
    render_block,
    request_json,
    truncate,
)
from app.services.service_key_service import ServiceCredentials

logger = logging.getLogger(__name__)

_TOOL = "community_read"
_CHANNEL_RE = re.compile(COMMUNITY_CHANNEL_PATTERN)
_WINDOW_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}

# Which stored credential each platform authenticates with.
_PLATFORM_PROVIDERS: dict[str, LLMProvider] = {
    "discord": LLMProvider.DISCORD,
    "slack": LLMProvider.SLACK,
    "telegram": LLMProvider.TELEGRAM,
}

# Caveats surfaced in the block header so the agent can be honest about coverage.
_PLATFORM_NOTES: dict[str, str] = {
    "telegram": (
        "partial: the Bot API exposes only updates recently delivered to the bot, "
        "not full channel history"
    ),
}


@dataclass(slots=True)
class Message:
    """One community message, normalized across all three platforms."""

    text: str
    author: str
    timestamp: str
    replies: int | None = None


async def fetch(
    channel: str,
    *,
    platform: str,
    window: str = CONNECTED_DEFAULT_WINDOW,
    credentials: ServiceCredentials,
) -> str:
    """Return a delimited block of recent messages from one channel."""
    if not settings.community_read_enabled:
        return failure(_TOOL, "the tool is disabled")
    if platform not in COMMUNITY_PLATFORMS:
        allowed = ", ".join(sorted(COMMUNITY_PLATFORMS))
        return failure(_TOOL, f'"{platform}" is not a supported platform ({allowed})')
    target = (channel or "").strip()
    # The channel id reaches a URL path or query, so it is validated before it
    # can reach a request at all.
    if not _CHANNEL_RE.match(target):
        return failure(_TOOL, f'"{channel}" is not a valid channel identifier')
    if window not in CONNECTED_WINDOWS:
        window = CONNECTED_DEFAULT_WINDOW

    provider = _PLATFORM_PROVIDERS[platform]
    token = credentials.get(provider)
    if not token:
        return CONNECTED_TOOL_MISSING_KEY_NOTICE.format(provider=provider.value)

    messages = await _ADAPTERS[platform](target, token)
    if messages is None:
        return failure(
            _TOOL,
            f"{platform} returned no usable response (auth, scope, or channel id)",
        )

    cutoff = datetime.now(UTC) - timedelta(hours=_WINDOW_HOURS[window])
    messages = [m for m in messages if _within(m.timestamp, cutoff)]
    messages = drop_suspicious(messages, lambda m: m.text)
    if not messages:
        return failure(_TOOL, f"no messages in {target} within the last {window}")

    note = _PLATFORM_NOTES.get(platform)
    header = (
        f"Platform: {platform} | channel: {target} | window: {window} | "
        f"messages: {len(messages)}"
    )
    if note:
        header = f"{header} | coverage: {note}"
    return render_block(
        open_tag=COMMUNITY_READ_RESULT_OPEN,
        close_tag=COMMUNITY_READ_RESULT_CLOSE,
        header=header,
        payload={
            "messages": [
                {
                    "text": m.text,
                    "author": m.author,
                    "timestamp": m.timestamp,
                    "replies": m.replies,
                }
                for m in messages
            ]
        },
    )


def _within(timestamp: str, cutoff: datetime) -> bool:
    """Keep a message when it is inside the window, or when its time is unknown.

    Dropping unparseable timestamps would silently shrink the sample; an agent
    counting messages would then report a confident number computed from an
    unknown fraction of the channel.
    """
    if not timestamp:
        return True
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= cutoff


def _limit() -> int:
    return settings.community_read_max_results


# --- Platform adapters ---------------------------------------------------


async def _read_discord(channel: str, token: str) -> list[Message] | None:
    data = await request_json(
        f"{DISCORD_API_BASE_URL}/channels/{channel}/messages",
        # Discord distinguishes bot from user tokens by this prefix; a stored
        # bot token without it authenticates as nothing and 401s.
        headers={"Authorization": f"Bot {token}"},
        params={"limit": min(_limit(), 100)},
        timeout=settings.community_read_timeout_seconds,
    )
    if not isinstance(data, list):
        return None
    messages = []
    for item in data:
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        messages.append(
            Message(
                text=truncate(item.get("content") or "", COMMUNITY_READ_ITEM_MAX_CHARS),
                author=str(author.get("username") or "")
                if isinstance(author, dict)
                else "",
                timestamp=str(item.get("timestamp") or ""),
            )
        )
    return messages


async def _read_slack(channel: str, token: str) -> list[Message] | None:
    data = await request_json(
        f"{SLACK_API_BASE_URL}/conversations.history",
        headers={"Authorization": f"Bearer {token}"},
        params={"channel": channel, "limit": min(_limit(), 200)},
        timeout=settings.community_read_timeout_seconds,
    )
    # Slack answers 200 with {"ok": false, "error": "..."} for auth and scope
    # failures, so the status code alone proves nothing.
    if not isinstance(data, dict) or not data.get("ok"):
        if isinstance(data, dict):
            logger.warning("Slack conversations.history refused: %s", data.get("error"))
        return None
    messages = []
    for item in data.get("messages") or []:
        if not isinstance(item, dict):
            continue
        messages.append(
            Message(
                text=truncate(item.get("text") or "", COMMUNITY_READ_ITEM_MAX_CHARS),
                author=str(item.get("user") or item.get("bot_id") or ""),
                timestamp=_from_slack_ts(item.get("ts")),
                replies=item.get("reply_count"),
            )
        )
    return messages


def _from_slack_ts(raw: Any) -> str:
    """Slack timestamps are "1699999999.000100" epoch strings, not ISO."""
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC).isoformat()
    except (TypeError, ValueError):
        return ""


async def _read_telegram(channel: str, token: str) -> list[Message] | None:
    data = await request_json(
        f"{TELEGRAM_API_BASE_URL}/bot{token}/getUpdates",
        params={"limit": min(_limit(), 100)},
        timeout=settings.community_read_timeout_seconds,
        # The token is a PATH segment here, so the derived host+path label would
        # leak it into the log. Pass a redacted one instead.
        log_target="api.telegram.org/bot***/getUpdates",
    )
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    messages = []
    for update in data.get("result") or []:
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post") or {}
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") or {}
        # getUpdates is bot-wide, not channel-scoped: filter to the requested
        # chat by numeric id or @username, or the agent would be handed traffic
        # from every chat the bot belongs to.
        if not _matches_chat(chat, channel):
            continue
        sender = message.get("from") or {}
        messages.append(
            Message(
                text=truncate(message.get("text") or "", COMMUNITY_READ_ITEM_MAX_CHARS),
                author=str(sender.get("username") or "")
                if isinstance(sender, dict)
                else "",
                timestamp=_from_unix(message.get("date")),
            )
        )
    return messages


def _matches_chat(chat: Any, channel: str) -> bool:
    if not isinstance(chat, dict):
        return False
    wanted = channel.lstrip("@").casefold()
    username = str(chat.get("username") or "").casefold()
    return wanted in {str(chat.get("id")), username}


def _from_unix(raw: Any) -> str:
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC).isoformat()
    except (TypeError, ValueError):
        return ""


_ADAPTERS: dict[str, Callable[[str, str], Awaitable[list[Message] | None]]] = {
    "discord": _read_discord,
    "slack": _read_slack,
    "telegram": _read_telegram,
}
