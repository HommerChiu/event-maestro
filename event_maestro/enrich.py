"""Server-side enrichment: turn a User-Agent and a visitor id into GA4 ``device`` / ``geo``.

Real GA4 looks up geo from the visitor's IP. Running locally every visitor
is 127.0.0.1, so geo is picked deterministically from the ``user_pseudo_id``
out of :data:`GEO_POOL` instead. The same pool feeds the synthetic generator.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

GEO_POOL: tuple[tuple[dict[str, str], float], ...] = (
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Taiwan", "region": "Taipei City", "city": "Taipei", "metro": "(not set)"}, 30),
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Taiwan", "region": "New Taipei City", "city": "Banqiao", "metro": "(not set)"}, 10),
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Taiwan", "region": "Taichung City", "city": "Taichung", "metro": "(not set)"}, 8),
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Taiwan", "region": "Kaohsiung City", "city": "Kaohsiung", "metro": "(not set)"}, 6),
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Hong Kong", "region": "Hong Kong", "city": "Hong Kong", "metro": "(not set)"}, 6),
    ({"continent": "Asia", "sub_continent": "Eastern Asia", "country": "Japan", "region": "Tokyo", "city": "Tokyo", "metro": "(not set)"}, 7),
    ({"continent": "Asia", "sub_continent": "Southeast Asia", "country": "Singapore", "region": "Singapore", "city": "Singapore", "metro": "(not set)"}, 5),
    ({"continent": "Americas", "sub_continent": "Northern America", "country": "United States", "region": "California", "city": "San Francisco", "metro": "San Francisco-Oakland-San Jose CA"}, 12),
    ({"continent": "Americas", "sub_continent": "Northern America", "country": "United States", "region": "New York", "city": "New York", "metro": "New York NY"}, 6),
    ({"continent": "Europe", "sub_continent": "Western Europe", "country": "Germany", "region": "Berlin", "city": "Berlin", "metro": "(not set)"}, 5),
    ({"continent": "Europe", "sub_continent": "Northern Europe", "country": "United Kingdom", "region": "England", "city": "London", "metro": "(not set)"}, 5),
)


def geo_for_visitor(user_pseudo_id: str) -> dict[str, str]:
    """Pick a stable geo for a visitor by hashing their id into the weighted pool."""
    digest = hashlib.sha256(user_pseudo_id.encode()).digest()
    total = sum(weight for _, weight in GEO_POOL)
    point = int.from_bytes(digest[:8], "big") / 2**64 * total
    for geo, weight in GEO_POOL:
        point -= weight
        if point < 0:
            return dict(geo)
    return dict(GEO_POOL[-1][0])


_BROWSERS = (
    ("Edge", r"Edg/([\d.]+)"),
    ("Opera", r"OPR/([\d.]+)"),
    ("Samsung Internet", r"SamsungBrowser/([\d.]+)"),
    ("Chrome", r"(?:Chrome|CriOS)/([\d.]+)"),
    ("Firefox", r"(?:Firefox|FxiOS)/([\d.]+)"),
    ("Safari", r"Version/([\d.]+).*Safari"),
)


def parse_user_agent(user_agent: str) -> dict[str, Any]:
    """A small, dependency-free UA parser that covers the common browsers.

    Good enough for a playground; production pipelines use a maintained
    library (ua-parser) because the long tail of user agents is huge.
    """
    ua = user_agent or ""
    browser, browser_version = "(not set)", "(not set)"
    for name, pattern in _BROWSERS:
        match = re.search(pattern, ua)
        if match:
            browser, browser_version = name, match.group(1)
            break

    os_name, os_version = "(not set)", "(not set)"
    brand, model = None, None
    if match := re.search(r"iPhone OS ([\d_]+)", ua):
        os_name, os_version, brand, model = "iOS", match.group(1).replace("_", "."), "Apple", "iPhone"
    elif match := re.search(r"iPad.*OS ([\d_]+)", ua):
        os_name, os_version, brand, model = "iOS", match.group(1).replace("_", "."), "Apple", "iPad"
    elif match := re.search(r"Android ([\d.]+)(?:; ([^;)]+))?", ua):
        os_name, os_version = "Android", match.group(1)
        model = (match.group(2) or "").strip() or None
        brand = "Samsung" if model and model.startswith("SM-") else "Google" if model and "Pixel" in model else None
    elif match := re.search(r"Windows NT ([\d.]+)", ua):
        os_name, os_version = "Windows", {"10.0": "10", "6.3": "8.1", "6.1": "7"}.get(match.group(1), match.group(1))
    elif match := re.search(r"Mac OS X ([\d_.]+)", ua):
        os_name, os_version, brand = "Macintosh", match.group(1).replace("_", "."), "Apple"
    elif "CrOS" in ua:
        os_name = "Chrome OS"
    elif "Linux" in ua:
        os_name = "Linux"

    if "iPad" in ua or "Tablet" in ua or (os_name == "Android" and "Mobile" not in ua):
        category = "tablet"
    elif "Mobi" in ua or "iPhone" in ua:
        category = "mobile"
    else:
        category = "desktop"

    return {
        "category": category,
        "mobile_brand_name": brand,
        "mobile_model_name": model,
        "operating_system": os_name,
        "operating_system_version": f"{os_name} {os_version}" if os_version != "(not set)" else "(not set)",
        "web_info": {"browser": browser, "browser_version": browser_version},
    }
