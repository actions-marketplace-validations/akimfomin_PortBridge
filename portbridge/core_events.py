"""Append changes to the audited curated relationships and evidence."""

from itertools import combinations
import json

from .identity import evidence_fields, relation_fields


SCHEMA = """
CREATE TABLE IF NOT EXISTS core_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS core_events_entity ON core_events(entity_id, sequence);
"""


def reviewed_entities(cards):
    entities = {}
    for card in cards:
        primary = [solution["source_refs"][0] for solution in card["solutions"]]
        kind = card.get("relationship", "same_problem")
        for left, right in combinations(primary, 2):
            relation = relation_fields(left, right, kind=kind, state="reviewed",
                                       reason="Reviewed catalog relationship", confidence="reviewed",
                                       directed=kind in {"source_port", "test_reuse"})
            relation.update(problem_id=card["id"], urls=[left["url"], right["url"]])
            entities[relation["id"]] = ("relation", "reviewed", relation)
        for solution in card["solutions"]:
            for evidence in solution["evidence"]:
                fields = evidence_fields(evidence)
                ident = fields["evidence_id"]
                summary = {**fields, "problem_id": card["id"], "project": solution["project"],
                           "outcome": evidence.get("outcome", "observed"), "observed": evidence["observed"],
                           "state": "reviewed"}
                entities[ident] = ("evidence", "reviewed", summary)
    return entities


def reconcile(db, cards, changed_at):
    incoming = reviewed_entities(cards)
    latest = {row["entity_id"]: row for row in db.execute(
        """SELECT event.* FROM core_events event
           JOIN (SELECT max(sequence) AS sequence FROM core_events GROUP BY entity_id) active USING(sequence)""")}
    for key in latest.keys() - incoming.keys():
        row = latest[key]
        if row["state"] != "withdrawn":
            payload = json.loads(row["payload"])
            incoming[key] = (row["kind"], "withdrawn", {**payload, "state": "withdrawn"})
    for key, (kind, state, payload) in sorted(incoming.items()):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if key not in latest or latest[key]["payload"] != encoded or latest[key]["state"] != state:
            db.execute("""INSERT INTO core_events (entity_id, kind, state, changed_at, payload)
                          VALUES (?, ?, ?, ?, ?)""", (key, kind, state, changed_at, encoded))


def events(db, *, kind=None, entity_id=None, after=0, limit=None):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='core_events' AND type='table'").fetchone():
        return []
    sql = "SELECT * FROM core_events WHERE sequence>?"
    values = [after]
    if kind:
        sql += " AND kind=?"
        values.append(kind)
    if entity_id:
        sql += " AND entity_id=?"
        values.append(entity_id)
    sql += " ORDER BY sequence ASC"
    if limit is not None:
        sql += " LIMIT ?"
        values.append(limit)
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in db.execute(sql, values)]


def current(db, *, kind):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='core_events' AND type='table'").fetchone():
        return []
    return [json.loads(row[0]) for row in db.execute(
        """SELECT event.payload FROM core_events event JOIN (
                SELECT max(sequence) AS sequence FROM core_events WHERE kind=? GROUP BY entity_id
            ) active USING(sequence) ORDER BY event.entity_id""", (kind,))]
