"""Public checkpoint restore and subscribed partner reads across API boundaries."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from unittest.mock import patch

from portbridge import community_sources, discovery_scan, radar_scan
from portbridge.__main__ import DEFAULT_SEED
from portbridge.backup import backup_database, checkpoint_count
from portbridge.catalog import Catalog
from portbridge.integrations import main as pull, select
from portbridge.mcp import PortBridgeMCP
from portbridge.radar_store import event
from test_portbridge import CatalogFixture


class M6PartnerTest(CatalogFixture):
    def test_scheduled_schema_restores_while_private_state_is_excluded(self):
        radar_scan.refresh(self.catalog)
        with self.catalog.connect() as db:
            db.executescript(community_sources.SCHEMA + discovery_scan.SCHEMA)
            db.execute("INSERT INTO discovery_observation VALUES(?,?,?,?)",
                       ("https://github.com/example/demo/pull/12", "a" * 40, "vkQueueSubmit", 1))
            event(db, actor="system", action="draft_created", now=1, details={"generation": "fixture"})
        backup = self.workspace / "checkpoint.sqlite"
        backup_database(self.db_path, backup, public_checkpoint=True)
        self.assertEqual(checkpoint_count(backup), checkpoint_count(self.db_path))
        recovered = Catalog(backup, DEFAULT_SEED)
        radar_scan.refresh(recovered)
        with recovered.connect() as db:
            self.assertEqual(db.execute("SELECT query FROM discovery_observation").fetchone()[0], "vkQueueSubmit")
            self.assertEqual(db.execute("SELECT count(*) FROM radar_events WHERE action='draft_created'").fetchone()[0], 1)

        blocked = self.workspace / "blocked.sqlite"
        with self.catalog.connect() as db:
            db.execute("PRAGMA secure_delete=OFF")
            db.execute("INSERT INTO radar_preferences VALUES('actor',?)", ("unused-private-marker" * 1024,))
        with self.assertRaisesRegex(ValueError, "local participant"):
            backup_database(self.db_path, blocked, public_checkpoint=True)
        self.assertFalse(blocked.exists())
        with self.catalog.connect() as db:
            db.execute("PRAGMA secure_delete=OFF")
            db.execute("DELETE FROM radar_preferences")
            event(db, actor="system", action="claim_expired", now=2, details={"claim_actor": "private"})
        with self.assertRaisesRegex(ValueError, "local Lab event"):
            backup_database(self.db_path, blocked, public_checkpoint=True)
        self.assertFalse(blocked.exists())
        with self.catalog.connect() as db:
            db.execute("DELETE FROM radar_events WHERE action='claim_expired'")
        backup_database(self.db_path, blocked, public_checkpoint=True)
        self.assertNotIn(b"unused-private-marker", blocked.read_bytes())

    def test_partial_page_and_outage_preserve_cursor_until_a_complete_recovery(self):
        feed = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                "counts": {"task": 105}, "items": [
                    {"id": f"task:{i}", "kind": "task", "projects": ["example"], "consoles": ["ps5"]}
                    for i in range(105)]}
        saved = self.workspace / "partner.json"
        cursor = self.workspace / "subscription.json"

        def run(payload):
            if payload is None:
                saved.unlink(missing_ok=True)
            else:
                saved.write_text(json.dumps(payload), encoding="utf8")
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(pull(["--snapshot", str(saved), "--cursor", str(cursor), "--console", "ps5"]), 0)
            return json.loads(out.getvalue())

        self.assertEqual(len(run(feed)["added_or_changed"]), 105)
        original = cursor.read_bytes()
        for partial in (select(feed, console="ps5", limit=100), select(feed, console="ps5", after=100),
                        select(feed, project="other"), {**feed, "items": feed["items"][:-1]}):
            self.assertEqual(run(partial)["state"], "incomplete")
            self.assertEqual(cursor.read_bytes(), original)
        self.assertEqual(run(None)["state"], "unavailable")
        self.assertEqual(cursor.read_bytes(), original)
        self.assertEqual(run(feed)["added_or_changed"], [])
        smaller = {**feed, "items": feed["items"][:-1], "counts": {"task": 104}}
        self.assertEqual(run(select(smaller, console="ps5"))["no_longer_listed"], ["task:104"])
        self.assertEqual(run(smaller)["no_longer_listed"], [])
        with patch("portbridge.mcp.snapshot", return_value=feed):
            response = PortBridgeMCP(None).run_tool({"name": "portbridge_partner", "arguments":
                {"console": "ps5", "after": 100, "limit": 5}})
        self.assertEqual(response["structuredContent"]["items"], feed["items"][100:])
        self.assertIsNone(response["structuredContent"]["next_after"])
