"""Count verified scheduled publications in the first seven days after a given rollout."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://api.github.com/repos/akimfomin/PortBridge/actions/"
RECEIPT = "portbridge-scheduled-publication-v1"


def stamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Use a timestamp with timezone")
    return parsed.astimezone(timezone.utc)


def pages(route, key, query, since):
    for page in range(1, 11):
        url = API + route + "?" + urlencode({**query, "per_page": 100, "page": page})
        with urlopen(Request(url, headers={"User-Agent": "PortBridge-public-autonomy-audit"}), timeout=20) as res:
            rows = json.load(res)[key]
        yield from rows
        if len(rows) < 100 or min(stamp(row["created_at"]) for row in rows) < since:
            return
    raise ValueError("API page budget reached; observed coverage is incomplete")


def measure(start, now, runs, artifacts):
    end = start + timedelta(days=7)
    if now < start:
        raise ValueError("Rollout timestamp is in the future")
    receipts = {row["workflow_run"]["id"]: row["id"] for row in artifacts
                if row["name"] == RECEIPT and not row["expired"] and row.get("workflow_run")}
    observed = sorted((row for row in runs if start <= stamp(row["created_at"]) < min(end, now)
                       and row["event"] == "schedule" and row["head_branch"] == "main"),
                      key=lambda row: row["created_at"])
    buckets = [0] * 7
    checked = []
    for run in observed:
        receipt = receipts.get(run["id"])
        if receipt and run["conclusion"] == "success":
            buckets[(stamp(run["created_at"]) - start).days] += 1
            checked.append({"at": run["created_at"], "url": run["html_url"],
                            "sha": run["head_sha"], "artifact_id": receipt})
    dates = [start, *(stamp(row["at"]) for row in checked), min(end, now)]
    return {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "elapsed_days": round((min(end, now) - start).total_seconds() / 86400, 3),
            "scheduled_runs": len(observed), "verified_publications": checked,
            "scheduled_without_success_receipt": [r["html_url"] for r in observed
                if r["id"] not in receipts or r["conclusion"] != "success"],
            "verified_per_24h": buckets,
            "longest_observed_gap_hours": round(max((b-a).total_seconds() for a,b in zip(dates,dates[1:])) / 3600, 2),
            "seven_intervals_observed": now >= end and all(buckets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, type=stamp, help="UTC rollout timestamp from the release report")
    args = parser.parse_args()
    runs = pages("workflows/pages.yml/runs", "workflow_runs",
                 {"branch": "main", "event": "schedule", "created": ">=" + args.since.isoformat()}, args.since)
    artifacts = pages("artifacts", "artifacts", {"name": RECEIPT}, args.since)
    print(json.dumps(measure(args.since, datetime.now(timezone.utc), runs, artifacts), indent=2))


if __name__ == "__main__":
    main()
