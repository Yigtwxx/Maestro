"""Local and place intelligence over the Google Places API (New).

Backs the ``places_intel`` tool for the ``local`` squad. Two aspects:

* ``search`` — the competitor set in a geography, each with rating, review
  count, price level and category. That distribution is the whole point: it is
  what lets an agent say "the median competitor holds 4.2 over 180 reviews"
  instead of paraphrasing one listing.
* ``reviews`` — review text for the same set, for complaint and theme mining.

Reviews are user-generated and injection-scanned per item. The Places API (New)
is POST-based and requires an explicit field mask; requesting review text costs
a higher SKU, which is why it is a separate aspect rather than always included.

Best-effort: any failure returns a notice, never an exception.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.constants import (
    CONNECTED_TOOL_MISSING_KEY_NOTICE,
    GOOGLE_PLACES_API_BASE_URL,
    PLACES_INTEL_ASPECTS,
    PLACES_INTEL_DEFAULT_ASPECT,
    PLACES_INTEL_ITEM_MAX_CHARS,
    PLACES_INTEL_RESULT_CLOSE,
    PLACES_INTEL_RESULT_OPEN,
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

_TOOL = "places_intel"
_MAX_RESULTS = 20  # hard ceiling in the Places API itself

# Field masks are mandatory on the New API — an unmasked request is rejected.
# Keeping the two masks separate is what keeps a cheap competitor sweep cheap.
_SEARCH_MASK = (
    "places.displayName,places.formattedAddress,places.rating,"
    "places.userRatingCount,places.priceLevel,places.primaryTypeDisplayName,"
    "places.businessStatus"
)
_REVIEWS_MASK = "places.displayName,places.rating,places.userRatingCount,places.reviews"


async def fetch(
    query: str,
    *,
    location: str = "",
    aspect: str = PLACES_INTEL_DEFAULT_ASPECT,
    credentials: ServiceCredentials,
) -> str:
    """Return a delimited block of places or reviews matching ``query``."""
    if not settings.places_intel_enabled:
        return failure(_TOOL, "the tool is disabled")
    terms = truncate(query or "", PLACES_INTEL_ITEM_MAX_CHARS)
    if not terms:
        return failure(_TOOL, "no search query was provided")
    if aspect not in PLACES_INTEL_ASPECTS:
        aspect = PLACES_INTEL_DEFAULT_ASPECT

    key = credentials.get(LLMProvider.GOOGLE_MAPS)
    if not key:
        return CONNECTED_TOOL_MISSING_KEY_NOTICE.format(
            provider=LLMProvider.GOOGLE_MAPS.value
        )

    where = truncate(location or "", PLACES_INTEL_ITEM_MAX_CHARS)
    # The New API takes the geography inside the free-text query rather than as
    # a separate parameter, so the two are joined here instead of the caller
    # having to know that.
    text_query = f"{terms} in {where}" if where else terms

    raw = await _search_text(text_query, aspect, key)
    if raw is None:
        return failure(
            _TOOL, "Google Places returned no usable response (auth, quota, or billing)"
        )
    places = _parse(raw, aspect)
    if not places:
        return failure(_TOOL, f'no places matched "{text_query}"')

    return render_block(
        open_tag=PLACES_INTEL_RESULT_OPEN,
        close_tag=PLACES_INTEL_RESULT_CLOSE,
        header=f"Query: {text_query} | aspect: {aspect} | places: {len(places)}",
        payload={"places": places},
    )


async def _search_text(text_query: str, aspect: str, key: str) -> Any | None:
    limit = min(settings.places_intel_max_results, _MAX_RESULTS)
    return await request_json(
        f"{GOOGLE_PLACES_API_BASE_URL}/places:searchText",
        method="POST",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": _REVIEWS_MASK if aspect == "reviews" else _SEARCH_MASK,
        },
        json_body={"textQuery": text_query, "maxResultCount": limit},
        timeout=settings.places_intel_timeout_seconds,
    )


def _parse(raw: Any, aspect: str) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for item in raw.get("places") or []:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "name": _localized(item.get("displayName")),
            "rating": item.get("rating"),
            "review_count": item.get("userRatingCount"),
        }
        if aspect == "reviews":
            entry["reviews"] = _reviews(item)
        else:
            entry["address"] = item.get("formattedAddress")
            entry["price_level"] = item.get("priceLevel")
            entry["category"] = _localized(item.get("primaryTypeDisplayName"))
            entry["status"] = item.get("businessStatus")
        out.append(entry)
    return out


def _reviews(place: dict[str, Any]) -> list[dict[str, Any]]:
    reviews = []
    for review in place.get("reviews") or []:
        if not isinstance(review, dict):
            continue
        reviews.append(
            {
                "rating": review.get("rating"),
                "text": truncate(
                    _localized(review.get("originalText") or review.get("text")),
                    PLACES_INTEL_ITEM_MAX_CHARS,
                ),
                "published": review.get("publishTime"),
            }
        )
    return drop_suspicious(reviews, lambda r: str(r.get("text", "")))


def _localized(value: Any) -> str:
    """Unwrap the API's {"text": ..., "languageCode": ...} localized strings."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(value or "")
