"""Console classification. Host platform and console family are separate."""

from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlsplit

CONSOLES = ("xbox-series", "ps5")
WATCH = Path(__file__).with_name("data") / "console_sources.json"


@lru_cache(maxsize=1)
def watch_sources():
    return json.loads(WATCH.read_bytes())


def repository_of(value):
    if not isinstance(value, str):
        return ""
    if value.startswith("https://"):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return ""
        if parsed.hostname != "github.com":
            return ""
        value = "/".join(parsed.path.strip("/").split("/")[:2])
    return value.lower().rstrip("/")


def console_families(value, *, default=()):
    record = watch_sources().get(repository_of(value))
    return list(record["consoles"]) if record else list(default)
