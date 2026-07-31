"""The MX lookup: correctness of the fail-open path and the cache."""

from __future__ import annotations

import dns.exception
import dns.resolver
import pytest

from app.utils import mx_check


@pytest.fixture(autouse=True)
def _enabled_and_empty(mx_check_on, monkeypatch):  # noqa: ANN001, ANN202
    """Every test here exercises the real logic against an empty cache."""
    mx_check.reset_cache()
    yield
    mx_check.reset_cache()


def _resolver(*, raises: Exception | None = None, answers: list[str] | None = None):  # noqa: ANN202
    async def _resolve(domain: str, record_type: str, **kwargs: object):  # noqa: ANN202
        if raises is not None:
            raise raises
        return answers or []

    return _resolve


async def test_a_domain_with_mx_records_passes(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mx_check, "_resolve", _resolver(answers=["mx1"]))

    assert await mx_check.has_mx("someone@example.com") is True


async def test_a_nonexistent_domain_is_refused(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mx_check, "_resolve", _resolver(raises=dns.resolver.NXDOMAIN()))

    assert await mx_check.has_mx("someone@gmial.invalid") is False


async def test_a_domain_with_no_mx_falls_back_to_its_address_record(  # noqa: ANN001
    monkeypatch,
) -> None:
    """RFC 5321 implicit MX: a domain with an A record and no MX can still
    receive mail. Refusing it would fail a whole class of small real domains."""
    calls: list[str] = []

    async def _resolve(domain: str, record_type: str, **kwargs: object):  # noqa: ANN202
        calls.append(record_type)
        if record_type == "MX":
            raise dns.resolver.NoAnswer()
        return ["192.0.2.1"]

    monkeypatch.setattr(mx_check, "_resolve", _resolve)

    assert await mx_check.has_mx("someone@a-record-only.test") is True
    assert calls == ["MX", "A"]


async def test_a_domain_with_neither_mx_nor_address_is_refused(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mx_check, "_resolve", _resolver(raises=dns.resolver.NoAnswer()))

    assert await mx_check.has_mx("someone@empty.test") is False


async def test_a_dns_failure_fails_open(monkeypatch) -> None:  # noqa: ANN001
    """A DNS outage must never stop registration."""
    monkeypatch.setattr(mx_check, "_resolve", _resolver(raises=dns.exception.Timeout()))

    assert await mx_check.has_mx("someone@example.com") is True


async def test_a_transient_failure_is_not_cached(monkeypatch) -> None:  # noqa: ANN001
    """Caching a timeout would extend one blip across the whole TTL."""
    monkeypatch.setattr(mx_check, "_resolve", _resolver(raises=dns.exception.Timeout()))
    await mx_check.has_mx("someone@example.com")

    monkeypatch.setattr(mx_check, "_resolve", _resolver(raises=dns.resolver.NXDOMAIN()))

    assert await mx_check.has_mx("someone@example.com") is False


async def test_a_decided_domain_is_answered_from_cache(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mx_check, "_resolve", _resolver(answers=["mx1"]))
    await mx_check.has_mx("someone@example.com")

    def _explode(*args: object, **kwargs: object):  # noqa: ANN202
        raise AssertionError("the cache should have answered this")

    monkeypatch.setattr(mx_check, "_resolve", _explode)

    assert await mx_check.has_mx("other@example.com") is True


async def test_the_switch_skips_the_lookup_entirely(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mx_check.settings, "email_mx_check_enabled", False)

    def _explode(*args: object, **kwargs: object):  # noqa: ANN202
        raise AssertionError("no lookup should happen while the check is off")

    monkeypatch.setattr(mx_check, "_resolve", _explode)

    assert await mx_check.has_mx("someone@gmial.invalid") is True
