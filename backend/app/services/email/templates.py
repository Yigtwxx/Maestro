"""Transactional email templates.

Kept out of the sending code (project rule: no inline copy in service logic).
Each function returns ``(subject, html, text)``; the caller supplies fully
absolute action links. Copy is English, matching the product UI.
"""

from __future__ import annotations

from app.core.constants import (
    EMAIL_VERIFY_TOKEN_TTL_HOURS,
    PASSWORD_RESET_TOKEN_TTL_MINUTES,
)

_STYLE_BODY = "font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;line-height:1.6"
_STYLE_CTA = (
    "display:inline-block;padding:10px 18px;border-radius:6px;"
    "background:#111111;color:#ffffff;text-decoration:none;font-weight:bold"
)
_STYLE_FINE = "font-size:12px;color:#666666"


def _html(title: str, paragraphs: list[str], cta: tuple[str, str] | None) -> str:
    """Assemble a minimal, client-safe HTML body (inline styles only)."""
    blocks = [f"<h2>{title}</h2>"]
    blocks += [f"<p>{p}</p>" for p in paragraphs]
    if cta is not None:
        label, link = cta
        blocks.append(f'<p><a href="{link}" style="{_STYLE_CTA}">{label}</a></p>')
        blocks.append(
            f'<p style="{_STYLE_FINE}">Or paste this link into your '
            f"browser:<br>{link}</p>"
        )
    blocks.append(f'<p style="{_STYLE_FINE}">&mdash; The Maestro team</p>')
    return f'<div style="{_STYLE_BODY}">' + "".join(blocks) + "</div>"


def verification_email(link: str) -> tuple[str, str, str]:
    """Sent on registration and on every "resend verification" request."""
    subject = "Verify your Maestro email address"
    paragraphs = [
        "Welcome to Maestro. Confirm this email address to unlock task runs "
        "and API key management.",
        f"This link expires in {EMAIL_VERIFY_TOKEN_TTL_HOURS} hours.",
    ]
    text = (
        "Welcome to Maestro.\n\n"
        "Confirm this email address to unlock task runs and API key "
        "management:\n"
        f"{link}\n\n"
        f"This link expires in {EMAIL_VERIFY_TOKEN_TTL_HOURS} hours."
    )
    return subject, _html("Verify your email", paragraphs, ("Verify email", link)), text


def password_reset_email(link: str) -> tuple[str, str, str]:
    """Sent from /auth/forgot-password when the account exists."""
    subject = "Reset your Maestro password"
    paragraphs = [
        "We received a request to reset your Maestro password.",
        f"This link expires in {PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes. "
        "If you did not request a reset, you can safely ignore this email.",
    ]
    text = (
        "We received a request to reset your Maestro password.\n\n"
        f"Reset it here:\n{link}\n\n"
        f"This link expires in {PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes. "
        "If you did not request a reset, you can safely ignore this email."
    )
    return (
        subject,
        _html("Reset your password", paragraphs, ("Reset password", link)),
        text,
    )


def deletion_requested_email(purge_date: str) -> tuple[str, str, str]:
    """Sent when the user schedules their account for deletion."""
    subject = "Your Maestro account is scheduled for deletion"
    paragraphs = [
        "Your account has been locked and is scheduled for permanent "
        f"deletion on {purge_date}.",
        "Changed your mind? Sign in any time before that date and restore "
        "your account from the locked-account screen.",
    ]
    text = (
        "Your account has been locked and is scheduled for permanent "
        f"deletion on {purge_date}.\n\n"
        "Changed your mind? Sign in any time before that date and restore "
        "your account from the locked-account screen."
    )
    return subject, _html("Account deletion scheduled", paragraphs, None), text


def deletion_cancelled_email() -> tuple[str, str, str]:
    """Sent when a scheduled deletion is cancelled (account restored)."""
    subject = "Your Maestro account has been restored"
    paragraphs = [
        "The scheduled deletion of your account has been cancelled. "
        "Everything is back to normal.",
        "If you did not do this, please change your password immediately.",
    ]
    text = (
        "The scheduled deletion of your account has been cancelled. "
        "Everything is back to normal.\n\n"
        "If you did not do this, please change your password immediately."
    )
    return subject, _html("Account restored", paragraphs, None), text
