"""Tests for the layered JSON extraction in ``app.agents.base.extract_json``."""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.base import extract_json


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"domain": "software"}', {"domain": "software"}),
        ('  {"a": 1}  ', {"a": 1}),
        # Fenced code blocks, with and without the json language tag.
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Here you go:\n```\n{"a": 1}\n```\nDone.', {"a": 1}),
        # Object wrapped in prose.
        ('Sure! The answer is {"domain": "seo"} as requested.', {"domain": "seo"}),
        # Nested braces.
        (
            '{"assignments": [{"member": "coder", "brief": "x"}]}',
            {"assignments": [{"member": "coder", "brief": "x"}]},
        ),
        # Braces inside string values must not break the balance scan.
        ('{"a": "b{c}d"}', {"a": "b{c}d"}),
        ('{"a": "quote \\" and {brace}"}', {"a": 'quote " and {brace}'}),
        # Multiple objects: the first parseable one wins.
        ('{"first": 1} and later {"second": 2}', {"first": 1}),
        # Invalid object followed by a valid one.
        ('{broken json} then {"ok": true}', {"ok": True}),
        # Qwen3-style reasoning prefix.
        ('<think>\nlet me think {a: 1}\n</think>\n{"a": 1}', {"a": 1}),
        # Think block plus prose plus fenced JSON.
        (
            '<think>hmm</think>Answer:\n```json\n{"domain": "data"}\n```',
            {"domain": "data"},
        ),
    ],
)
def test_extract_json_parses(text: str, expected: dict[str, Any]) -> None:
    assert extract_json(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        "[1, 2, 3]",  # top-level array is not an object
        '["a", "b"]',
        "{broken: json}",
        "<think>only thoughts</think>",
        "```json\nnot json\n```",
    ],
)
def test_extract_json_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        extract_json(text)
