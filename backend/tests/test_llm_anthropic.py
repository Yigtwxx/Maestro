"""Tests for the Anthropic Messages API adapter (no real network calls)."""

from __future__ import annotations

import pytest

from app.services.llm_service import AnthropicAdapter, ChatMessage, LLMError


def test_split_system_separates_system_from_turns():
    adapter = AnthropicAdapter(api_key="k")
    system, turns = adapter._split_system(
        [ChatMessage("system", "S"), ChatMessage("user", "U")]
    )
    assert system == "S"
    assert turns == [{"role": "user", "content": "U"}]


async def test_chat_builds_request_and_parses_response(monkeypatch):
    adapter = AnthropicAdapter(api_key="k")
    captured: dict = {}

    async def fake_post(payload: dict) -> dict:
        captured.update(payload)
        return {
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 3, "output_tokens": 4},
        }

    monkeypatch.setattr(adapter, "_post", fake_post)
    resp = await adapter.chat(
        [ChatMessage("system", "S"), ChatMessage("user", "hi")], max_tokens=64
    )
    assert resp.content == "hello"
    assert resp.tokens_used == 7
    assert captured["system"] == "S"
    assert captured["max_tokens"] == 64  # Anthropic requires this field


async def test_chat_without_api_key_raises():
    adapter = AnthropicAdapter()  # no BYOK key
    with pytest.raises(LLMError):
        await adapter.chat([ChatMessage("user", "hi")])
