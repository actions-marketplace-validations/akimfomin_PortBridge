"""Shared collection freshness and coverage for API, snapshots and clients."""
from collections import Counter
from datetime import datetime, timezone


MAX_AGE_SECONDS = 2 * 60 * 60
FUTURE_TOLERANCE_SECONDS = 5 * 60


def source_time(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, OverflowError):
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
    return None


def freshest(*values):
    usable = [(parsed, value) for value in values if (parsed := source_time(value)) is not None]
    return max(usable, default=(None, None))[1]


def age(value, now):
    observed = source_time(value)
    if observed is None:
        return None
    seconds = (now - observed).total_seconds()
    return max(0, int(seconds)) if seconds >= -FUTURE_TOLERANCE_SECONDS else None


def freshness(last_success, now):
    seconds = age(last_success, now)
    return {"age_seconds": seconds, "age_state": (
        "unknown" if seconds is None else "stale" if seconds >= MAX_AGE_SECONDS else "fresh")}


def health_freshness(report, *, now=None, generated_at=None):
    """Keep attempt, success and snapshot generation independent."""
    if not isinstance(report, dict) or not isinstance(report.get("sources", []), list):
        raise ValueError("Invalid PortBridge health report")
    now = now or datetime.now(timezone.utc)
    sources = []
    for original in report.get("sources", []):
        if not isinstance(original, dict) or not isinstance(original.get("kinds", {}), dict):
            raise ValueError("Invalid PortBridge source health record")
        source = dict(original)
        source.update(freshness(source.get("last_success"), now))
        source["kinds"] = {name: {**kind, **freshness(kind.get("last_success"), now)}
                           for name, kind in source.get("kinds", {}).items()}
        sources.append(source)
    # A successful legacy build exposes per-source timestamps even if its envelope didn't.
    success = freshest(report.get("last_success"), *(source.get("last_success") for source in sources))
    result = {**report, "sources": sources, "as_of": now.isoformat(timespec="seconds"),
              "last_success": success, "freshness_limit_seconds": MAX_AGE_SECONDS,
              "freshness": freshness(success, now),
              "source_totals": {"age": dict(Counter(source["age_state"] for source in sources)),
                                "availability": dict(Counter(source.get("availability", "unknown") for source in sources)),
                                "collection": dict(Counter(source.get("freshness", "unknown") for source in sources))}}
    if generated_at is not None:
        result["publication"] = {"generated_at": generated_at, **freshness(generated_at, now)}
    return result
