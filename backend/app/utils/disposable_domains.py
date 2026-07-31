"""Vendored blocklist of disposable ("throwaway") email providers.

A Python module rather than a data file: a normal import cannot silently fail
the way a missing `.txt` in a container image can, there is no import-time file
I/O, and ruff and git treat it like any other source.

Curated rather than exhaustive. The published 100k-entry lists carry their own
false positives (small legitimate domains appear on several of them), and
fetching one at runtime would break the zero-egress default the `SENTRY_DSN`
contract establishes. The operator extends this with `DISPOSABLE_DOMAINS_EXTRA`.

**Never add a privacy relay here.** `EMAIL_RELAY_DOMAINS` in `constants.py`
exists to keep Apple Private Relay, DuckDuckGo, SimpleLogin and Firefox Relay
out of this set: those are permanent addresses belonging to real users, and
blocking them would drive away exactly the people most careful about their data.
"""

from __future__ import annotations

DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "0-mail.com",
        "10minutemail.com",
        "10minutemail.net",
        "20minutemail.com",
        "33mail.com",
        "getairmail.com",
        "anonbox.net",
        "byom.de",
        "dispostable.com",
        "dropmail.me",
        "emailondeck.com",
        "emailtemporanea.net",
        "fakeinbox.com",
        "fakemailgenerator.com",
        "gettempmail.com",
        "grr.la",
        "guerrillamail.biz",
        "guerrillamail.com",
        "guerrillamail.de",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamailblock.com",
        "harakirimail.com",
        "inboxbear.com",
        "inboxkitten.com",
        "jetable.org",
        "mail-temporaire.fr",
        "mail7.io",
        "mailcatch.com",
        "maildrop.cc",
        "mailexpire.com",
        "mailforspam.com",
        "mailinator.com",
        "mailinator.net",
        "mailnesia.com",
        "mailsac.com",
        "mailtemp.top",
        "mintemail.com",
        "moakt.com",
        "mohmal.com",
        "mytemp.email",
        "nowmymail.com",
        "temp-mail.io",
        "temp-mail.org",
        "tempail.com",
        "tempinbox.com",
        "tempmail.dev",
        "tempmail.plus",
        "tempmailo.com",
        "tempr.email",
        "throwawaymail.com",
        "trashmail.com",
        "trashmail.de",
        "trashmail.me",
        "trashmail.net",
        "sharklasers.com",
        "spam4.me",
        "spamgourmet.com",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
        "zetmail.com",
    }
)
