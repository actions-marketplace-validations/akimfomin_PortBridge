"""People/Impact attribution and privacy regressions."""
import copy
import json
from unittest.mock import patch

from portbridge.community import filter_impact, filter_people, people, read_data
from portbridge.community_policy import decide
from portbridge.community_sources import SCHEMA, thread_entry
from portbridge.export import export
from portbridge.mcp import PortBridgeMCP
from test_portbridge import CatalogFixture

XBOX = "https://github.com/LooperSalty/AnyXboxX/pull/9911"
PS5 = "https://github.com/boykopovar/AnyPS5/pull/9912"
AT = "2026-10-01T10:00:00Z"
AFTER = "2026-10-02T10:00:00Z"
DECISION = "https://github.com/akimfomin/PortBridge/issues/990"


def actor(login, number):
    return {"login": login, "user_id": number}


def observation(url, slug, login, number, when=AT, **metadata):
    return {"url": url, "project": slug, "kind": "pr", "source_id": url.rsplit("/",1)[1],
            "title": "Fix shader subgroup selection and memory barrier", "status": "open",
            "updated_at": when, "fetched_at": AFTER, "metadata": {
                "author": login, "github_user_id": number, **metadata}}


class CommunityTest(CatalogFixture):
    def setUp(self):
        super().setUp()
        self.rows = [observation(XBOX, "anyxboxx", "TestAlias", 9911),
                     observation(PS5, "anyps5", "TestRename", 9911, AFTER),
                     observation(PS5.replace("9912", "9913"), "anyps5", "NotAPerson", 9912, AFTER, author_type="Bot")]
        self.catalog.record_sync({"items": self.rows}, update_health=False)
        self.config = {"people": [], "stories": [], "visibility": {}, "research_links": [
            {"id": "people:wave-check", "from": "loopersalty/anyxboxx", "to": "boykopovar/anyps5",
             "source": XBOX, "comparison": PS5, "at": AFTER, "kind": "shared_mechanism", "state": "research",
             "specialty": "shaders", "consoles": ["xbox-series", "ps5"], "basis": "Same instruction, distinct masks"}]}
        original = read_data
        self.patch = patch("portbridge.community.read_data",
                           side_effect=lambda name: self.config if name == "impact_evidence.json" else original(name))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_numeric_identity_rename_graph_and_no_implicit_availability(self):
        result, impact = people(self.catalog)
        visible = result["profiles"]
        self.assertEqual([row["login"] for row in visible], ["TestRename"])
        row = visible[0]
        self.assertEqual(row["id"], "github-user:9911")
        self.assertEqual(row["consoles"], ["ps5", "xbox-series"])
        self.assertFalse(row["availability"])
        consent = decide(read_data("people_policy.json"), {"action": "opt-in", "actor": actor("TestRename", 9911),
            "at": AT, "until": AFTER, "scope": "lab-test", "proof": DECISION})
        from portbridge.radar_store import epoch
        self.assertEqual(people(self.catalog, now=epoch(AT), policy=consent)[0]["profiles"][0]["availability"]["scope"], "lab-test")
        self.assertIsNone(people(self.catalog, now=epoch(AFTER), policy=consent)[0]["profiles"][0]["availability"])
        self.assertEqual({p["repo"] for p in row["projects"]}, {"loopersalty/anyxboxx","boykopovar/anyps5"})
        self.assertEqual({r["role"] for r in row["roles"]}, {"developer", "bridge"})
        at_target = filter_people(result, target=PS5)
        self.assertEqual(at_target["connections"][0]["state"], "research")
        self.assertEqual(at_target["profiles"][0]["target_evidence"]["source"], PS5)
        self.assertNotIn("target_index", at_target)
        self.assertEqual(impact["metrics"]["accepted_changes"]["value"], 0)
        self.assertEqual(filter_impact(impact, target=PS5)["stories"], [])

    def test_correct_retract_idempotency_and_hide_reissued_sources(self):
        policy = read_data("people_policy.json")
        case = {"id":"impact:correction", "title":"TestAlias report", "summary":"A checked source", "scope":"Synthetic",
                "type":"test", "state":"reviewed", "consoles":["xbox-series"], "at":AT,
                "sources":[{"url":XBOX,"label":"Source"}], "credits":[
                    {"kind":"fix","source":XBOX,"login":"TestAlias","user_id":9911,"basis":"Prior attribution"}],
                "measures":[["independent_reproductions",XBOX]]}
        self.config["stories"] = [case, {**case, "id":"impact:duplicate"}]
        corrected = {"action":"correct","source":XBOX,"actor":actor("CheckedActor",9922),"proof":DECISION,"at":AFTER}
        updated = decide(policy, corrected)
        self.assertEqual(updated,decide(copy.deepcopy(updated),corrected))
        before, after = people(self.catalog, policy=policy)
        current = next(row for row in before["profiles"] if row["login"] == "CheckedActor")
        self.assertEqual(current["evidence"][0]["correction"], DECISION)
        self.assertEqual(after["metrics"]["independent_reproductions"]["value"],1)
        self.assertEqual(after["metrics"]["credited_acts"]["value"],1)
        hidden = decide(copy.deepcopy(updated),{"action":"opt-out","actor":actor("TestAlias",9911),"proof":DECISION,"at":AFTER})
        filtered, outcome = people(self.catalog, policy=hidden)
        self.assertEqual([row["login"] for row in filtered["profiles"]],["CheckedActor"])
        self.assertNotIn("TestAlias",json.dumps(outcome))
        self.assertNotIn("TestRename",json.dumps(filtered))
        site = self.workspace / "hidden-export"
        with patch("portbridge.community.read_data", side_effect=lambda name:
                   self.config if name == "impact_evidence.json" else updated):
            export(self.catalog,site)
        prior = json.loads((site/"data/site.json").read_bytes())["snapshots"]["people"]
        with patch("portbridge.community.read_data", side_effect=lambda name:
                   self.config if name == "impact_evidence.json" else hidden):
            export(self.catalog,site)
        self.assertFalse((site/"data"/prior).exists())
        self.assertNotIn("TestRename",(site/"data/people-directory.json").read_text(encoding="utf8"))
        blocked = decide(hidden,{"action":"withdraw","source":XBOX,"proof":DECISION,"at":AFTER})
        self.assertEqual(people(self.catalog,policy=blocked)[1]["metrics"]["independent_reproductions"]["value"],0)

    def test_public_thread_receipts_and_cached_disappearance(self):
        reviewer = {"login":"PublicReview", "id":9990, "type":"User"}
        data = {"user":reviewer,"html_url":PS5+"#pullrequestreview-12","id":12,"state":"APPROVED","submitted_at":AFTER}
        record = thread_entry(data,"boykopovar/anyps5",PS5)
        self.assertEqual(record["role"],"reviewer")
        self.assertIsNone(thread_entry({**data,"state":"DISMISSED"},"boykopovar/anyps5",PS5))
        self.assertIsNone(thread_entry({**data,"user":{**reviewer,"type":"Bot"}},"boykopovar/anyps5",PS5))
        with self.catalog.connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO community_scopes VALUES('review',?,?,'not_public',?,NULL)",
                      ("boykopovar/anyps5",1,1))
            db.execute("INSERT INTO community_facts VALUES(?,'review',?,?)",
                       (record["id"],record["repo"],json.dumps(record)))
        result,_=people(self.catalog,now=1791100000)
        profile=next(p for p in result["profiles"] if p["login"]=="PublicReview")
        self.assertEqual(profile["roles"][0]["age"],"stale")
        self.assertEqual(profile["interactions"][0]["to"],"github-user:9911")
        site=export(self.catalog,self.workspace/"community-export")
        doc=json.loads((site/"data/people.json").read_bytes())
        mcp=PortBridgeMCP(self.catalog).run_tool({"name":"portbridge_people","arguments":{"profile":"github-user:9990"}})
        self.assertEqual(filter_people(doc,profile="github-user:9990")["profiles"][0]["roles"],
                         mcp["structuredContent"]["profiles"][0]["roles"])
        self.config["people"] = [record]
        from portbridge.community_sources import evidence_key
        with self.catalog.connect() as db:
            db.execute("DELETE FROM community_facts")
            db.execute("UPDATE community_scopes SET name=?,status='complete'",("review:"+evidence_key(PS5),))
        self.assertFalse(filter_people(people(self.catalog)[0],q="PublicReview")["profiles"])
