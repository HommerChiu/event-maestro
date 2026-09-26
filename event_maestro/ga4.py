"""Build rows that follow the GA4 BigQuery export schema (``events_YYYYMMDD``).

Both the live website collector and the synthetic generator go through
:func:`build_event_row`, so every row that lands on disk has the same shape
no matter where it came from.

Reference: https://support.google.com/analytics/answer/7029846
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, tzinfo
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

DEFAULT_STREAM_ID = "1234567890"
PLATFORM = "WEB"


def property_timezone() -> tzinfo:
    """GA4 derives ``event_date`` from the property's reporting time zone."""
    name = os.environ.get("EVENT_MAESTRO_TIMEZONE", "Asia/Taipei")
    try:
        return ZoneInfo(name)
    except Exception:  # pragma: no cover - missing tzdata
        return timezone.utc


def event_date_for(timestamp_micros: int, tz: tzinfo | None = None) -> str:
    tz = tz or property_timezone()
    dt = datetime.fromtimestamp(timestamp_micros / 1_000_000, tz)
    return dt.strftime("%Y%m%d")


def encode_value(value: Any) -> dict[str, Any]:
    """Encode a Python value into GA4's ``{string,int,float,double}_value`` struct.

    GA4 never uses ``float_value`` for web streams; numbers with a fractional
    part land in ``double_value`` and whole numbers in ``int_value``.
    """
    out: dict[str, Any] = {
        "string_value": None,
        "int_value": None,
        "float_value": None,
        "double_value": None,
    }
    if value is None:
        return out
    if isinstance(value, bool):
        out["int_value"] = int(value)
    elif isinstance(value, int):
        out["int_value"] = value
    elif isinstance(value, float):
        out["double_value"] = value
    else:
        out["string_value"] = str(value)
    return out


def encode_params(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "value": encode_value(value)}
        for key, value in params.items()
        if value is not None and key != "items"
    ]


def encode_user_properties(
    props: Mapping[str, Any], set_timestamp_micros: int
) -> list[dict[str, Any]]:
    rows = []
    for key, value in props.items():
        if value is None:
            continue
        encoded = encode_value(value)
        encoded["set_timestamp_micros"] = set_timestamp_micros
        rows.append({"key": key, "value": encoded})
    return rows


ITEM_FIELDS = (
    "item_id",
    "item_name",
    "item_brand",
    "item_variant",
    "item_category",
    "item_category2",
    "item_category3",
    "item_category4",
    "item_category5",
    "price_in_usd",
    "price",
    "quantity",
    "item_revenue_in_usd",
    "item_revenue",
    "item_refund_in_usd",
    "item_refund",
    "coupon",
    "affiliation",
    "location_id",
    "item_list_id",
    "item_list_name",
    "item_list_index",
    "promotion_id",
    "promotion_name",
    "creative_name",
    "creative_slot",
)


def normalize_item(item: Mapping[str, Any], event_name: str) -> dict[str, Any]:
    row = {field: item.get(field) for field in ITEM_FIELDS}
    price = row["price"]
    if price is not None:
        row["price"] = float(price)
        row["price_in_usd"] = float(price)
    quantity = row["quantity"]
    if quantity is not None:
        row["quantity"] = int(quantity)
    if event_name == "purchase" and price is not None and quantity is not None:
        revenue = round(float(price) * int(quantity), 2)
        row["item_revenue"] = revenue
        row["item_revenue_in_usd"] = revenue
    return row


def empty_ecommerce() -> dict[str, Any]:
    return {
        "total_item_quantity": None,
        "purchase_revenue_in_usd": None,
        "purchase_revenue": None,
        "refund_value_in_usd": None,
        "refund_value": None,
        "shipping_value_in_usd": None,
        "shipping_value": None,
        "tax_value_in_usd": None,
        "tax_value": None,
        "unique_items": None,
        "transaction_id": None,
    }


def build_ecommerce(
    event_name: str, params: Mapping[str, Any], items: list[dict[str, Any]]
) -> dict[str, Any]:
    ecommerce = empty_ecommerce()
    if items:
        ecommerce["total_item_quantity"] = sum(i.get("quantity") or 0 for i in items)
        ecommerce["unique_items"] = len({i.get("item_id") for i in items})
    if event_name == "purchase":
        value = params.get("value")
        if value is not None:
            ecommerce["purchase_revenue"] = float(value)
            ecommerce["purchase_revenue_in_usd"] = float(value)
        for key in ("shipping", "tax"):
            amount = params.get(key)
            if amount is not None:
                ecommerce[f"{key}_value"] = float(amount)
                ecommerce[f"{key}_value_in_usd"] = float(amount)
        ecommerce["transaction_id"] = params.get("transaction_id")
    return ecommerce


def build_event_row(
    *,
    event_name: str,
    event_timestamp: int,
    user_pseudo_id: str,
    params: Mapping[str, Any] | None = None,
    items: Iterable[Mapping[str, Any]] | None = None,
    user_id: str | None = None,
    user_properties: Mapping[str, Any] | None = None,
    user_properties_set_at: int | None = None,
    user_first_touch_timestamp: int | None = None,
    user_ltv_revenue: float | None = None,
    device: Mapping[str, Any] | None = None,
    geo: Mapping[str, Any] | None = None,
    traffic_source: Mapping[str, Any] | None = None,
    collected_traffic_source: Mapping[str, Any] | None = None,
    event_previous_timestamp: int | None = None,
    event_bundle_sequence_id: int | None = None,
    event_server_timestamp_offset: int | None = None,
    batch_event_index: int | None = None,
    stream_id: str = DEFAULT_STREAM_ID,
    tz: tzinfo | None = None,
) -> dict[str, Any]:
    """Return one GA4 export row as a plain dict (ready for ``json.dumps``)."""
    params = dict(params or {})
    normalized_items = [normalize_item(i, event_name) for i in (items or [])]
    currency = params.get("currency")
    value = params.get("value")
    event_value_in_usd = (
        float(value) if value is not None and currency in (None, "USD") else None
    )

    return {
        "event_date": event_date_for(event_timestamp, tz),
        "event_timestamp": event_timestamp,
        "event_name": event_name,
        "event_params": encode_params(params),
        "event_previous_timestamp": event_previous_timestamp,
        "event_value_in_usd": event_value_in_usd,
        "event_bundle_sequence_id": event_bundle_sequence_id,
        "event_server_timestamp_offset": event_server_timestamp_offset,
        "user_id": user_id,
        "user_pseudo_id": user_pseudo_id,
        "privacy_info": {
            "analytics_storage": "Yes",
            "ads_storage": "Yes",
            "uses_transient_token": "No",
        },
        "user_properties": encode_user_properties(
            user_properties or {}, user_properties_set_at or event_timestamp
        ),
        "user_first_touch_timestamp": user_first_touch_timestamp,
        "user_ltv": {
            "revenue": user_ltv_revenue if user_ltv_revenue is not None else 0.0,
            "currency": "USD",
        },
        "device": _device(device),
        "geo": _geo(geo),
        "app_info": None,
        "traffic_source": _traffic_source(traffic_source),
        "stream_id": stream_id,
        "platform": PLATFORM,
        "event_dimensions": None,
        "ecommerce": build_ecommerce(event_name, params, normalized_items),
        "items": normalized_items,
        "collected_traffic_source": _collected_traffic_source(collected_traffic_source),
        "is_active_user": True,
        "batch_event_index": batch_event_index,
    }


def _device(device: Mapping[str, Any] | None) -> dict[str, Any]:
    device = device or {}
    web_info = device.get("web_info") or {}
    return {
        "category": device.get("category", "desktop"),
        "mobile_brand_name": device.get("mobile_brand_name"),
        "mobile_model_name": device.get("mobile_model_name"),
        "mobile_marketing_name": device.get("mobile_marketing_name"),
        "mobile_os_hardware_model": None,
        "operating_system": device.get("operating_system"),
        "operating_system_version": device.get("operating_system_version"),
        "vendor_id": None,
        "advertising_id": None,
        "language": device.get("language"),
        "is_limited_ad_tracking": device.get("is_limited_ad_tracking", "No"),
        "time_zone_offset_seconds": device.get("time_zone_offset_seconds"),
        "browser": None,
        "browser_version": None,
        "web_info": {
            "browser": web_info.get("browser"),
            "browser_version": web_info.get("browser_version"),
            "hostname": web_info.get("hostname"),
        },
    }


def _geo(geo: Mapping[str, Any] | None) -> dict[str, Any]:
    geo = geo or {}
    return {
        key: geo.get(key)
        for key in ("city", "country", "continent", "region", "sub_continent", "metro")
    }


def _traffic_source(ts: Mapping[str, Any] | None) -> dict[str, Any]:
    ts = ts or {}
    return {
        "name": ts.get("name") or ts.get("campaign") or "(direct)",
        "medium": ts.get("medium") or "(none)",
        "source": ts.get("source") or "(direct)",
    }


def _collected_traffic_source(ts: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not ts:
        return None
    return {
        "manual_campaign_id": ts.get("campaign_id"),
        "manual_campaign_name": ts.get("campaign"),
        "manual_source": ts.get("source"),
        "manual_medium": ts.get("medium"),
        "manual_term": ts.get("term"),
        "manual_content": ts.get("content"),
        "gclid": ts.get("gclid"),
        "dclid": None,
        "srsltid": None,
    }
