"""Exercise three source-backed checks with two separately launched MCP clients."""
import argparse
from hashlib import sha256
import json
import os
import platform
from pathlib import Path
import shutil
from subprocess import PIPE, run
import sys
from threading import Thread
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portbridge.__main__ import DEFAULT_SEED, make_server
from portbridge.catalog import Catalog
from portbridge.community import filter_impact, people
from portbridge.exchange import Exchange
from portbridge.integrations import public_feed, digest
from portbridge.lab import build_lab
from portbridge.preflight import preflight
from portbridge.radar_scan import refresh
from portbridge.radar_store import timestamp

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=Path, default=ROOT / "audit" / "fixtures" / "pilot")
parser.add_argument("workspace", type=Path)
parser.add_argument("--online", action="store_true")
args = parser.parse_args()
root, work = args.input.resolve(), args.workspace.resolve()
if work.is_relative_to(ROOT) and not work.is_relative_to(ROOT / ".portbridge"):
    parser.error("Choose a new workspace under .portbridge or outside the checkout for local pilot data.")
work.mkdir(parents=True)
selected = {entry["n"]: entry for entry in json.loads((root/"new-prs.json").read_bytes())}
artifact = (root/"source-receipts.json").read_bytes()
receipt = json.loads(artifact)
pins = receipt["inputs"]
now = int(time.time())
checked = timestamp(now)
seed = json.loads(DEFAULT_SEED.read_bytes())
seed["projects"].append({"slug":"vulkan-docs-pilot", "name":"Khronos Vulkan specification",
                         "repo":"KhronosGroup/Vulkan-Docs", "url":"https://github.com/KhronosGroup/Vulkan-Docs",
                         "stack":"Vulkan specification", "license":"See pinned source license"})
seed_file = work/"pilot-seed.json"
seed_file.write_text(json.dumps(seed), encoding="utf8")
cat = Catalog(work/"public-inputs.sqlite3", seed_file)
projects = {row["repo"].lower():row["slug"] for row in cat.projects()}
doc = f"https://github.com/KhronosGroup/Vulkan-Docs/commit/{pins['vulkan_docs']}"
comparison = "https://github.com/LooperSalty/AnyXboxX/pull/354"
cases = [
    ("kyty",selected[2038]["url"],doc,"PASS","Verify optional Vulkan robust-buffer paths",
     "The harness explicitly checks alignment, robustness features and optional derivatives before use.",
     "Pinned harness and Khronos extension describe feature-gated pipelines. Driver runtime remains open."),
    ("continued",selected[2365]["url"],selected[20730]["url"],"FAIL","Compare lost-device and parked-queue conditions",
     "Test whether both pins recover the same submission state without a global wait.",
     "Continued compares the requested fence maximum. AnyPS5 replaces the pacing wait for a parked compute queue. These conditions are different."),
    ("xcl",selected[2775]["url"],comparison,"FAIL","Compare what allows quarantined resources to be freed",
     "Test whether both pins wait for every queue mark before draining their resource.",
     "XCL adds a helper for quarantine marks in tests. AnyXboxX provides runtime LRU eviction using completed-fence information. This is not an identical readiness contract."),
]
def obs(repo, url, title, revision, number, *, stamp=checked, kind="pr"):
    return {"project":projects[repo.lower()], "kind":kind, "source_id":str(number), "url":url, "title":title,
            "status":"open" if kind=="pr" else "recorded", "updated_at":stamp, "fetched_at":checked,
            "metadata":{"head_sha":revision,"sha":revision,
                        "technical":{"terms":[],"signals":[],"references":[]}}}
indexed = [obs(row["repo"],row["url"],row["title"],row["head"],number,
               stamp=row["date"]) for number,row in selected.items()]
indexed.extend([obs("KhronosGroup/Vulkan-Docs",doc,"Vulkan pipeline robustness feature contract",pins["vulkan_docs"],
                    pins["vulkan_docs"],kind="commit"),
                obs("LooperSalty/AnyXboxX",comparison,"Fence-safe texture LRU eviction",pins["anyxboxx"],354)])
cat.record_sync({"items":indexed},update_health=False)
radar = refresh(cat,online_discovery=args.online,now=now)
exchange = Exchange(work/"permissions.sqlite3")
author=exchange.create_principal("m5-fixture-volunteer",["read","contribute"])["token"]
reader=exchange.create_principal("m5-fixture-reviewer",["read","review"])["token"]
server=make_server(cat,0,exchange=exchange)
thread=Thread(target=server.serve_forever,daemon=True)
thread.start()
client_a=work/"client-a"
client_b=work/"client-b"
for folder in (client_a,client_b):
    folder.mkdir()
    shutil.copytree(ROOT/"portbridge",folder/"portbridge",ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    assert not list(folder.rglob("*.sqlite3"))

def tool(workspace, key, name, payload, *, writes=False, version="2025-11-25"):
    rpc=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":version,
           "capabilities":{},"clientInfo":{"name":workspace.name,"version":"1"}}},
         {"jsonrpc":"2.0","method":"notifications/initialized"},
         {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":payload}}]
    env={k:v for k,v in os.environ.items() if k not in {"PYTHONPATH","PORTBRIDGE_EXCHANGE_TOKEN","PORTBRIDGE_GITHUB_TOKEN","GITHUB_TOKEN"}}
    env.update(PORTBRIDGE_EXCHANGE_TOKEN=key,PYTHONUTF8="1")
    cmd=[sys.executable,"-EsB","-m","portbridge.mcp","--exchange-port",str(server.server_port)]
    if writes:
        cmd.append("--enable-lab-writes")
    res=run(cmd,cwd=workspace,env=env,input=("\n".join(map(json.dumps,rpc))+"\n").encode(),
            stdout=PIPE,stderr=PIPE,timeout=20,check=True)
    answer=json.loads(res.stdout.splitlines()[-1])
    return answer.get("result",{})

def change(key, action, payload):
    wire={"action":action, **payload}
    request=Request(f"http://127.0.0.1:{server.server_port}/api/v1/exchange/lab-action",
                    data=json.dumps(wire).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    with urlopen(request,timeout=15) as response:
        return json.load(response)

def consent(action, task, ident, **extra):
    return {"action":action,"consent":True,"task":task,"request_id":ident,**extra}
def found(origin):
    return filter_impact(people(cat,now=now)[1],target=origin)["stories"]
def foreground(origin):
    return tool(client_a,author,"portbridge_preflight",{"url":origin})["structuredContent"]

output=[]
try:
    for tag,origin,peer,result,title,expected,observed in cases:
        prior = foreground(origin)
        assert prior["origin_url"]
        pair_pins = [item["revision"] for item in receipt["checks"][tag]]
        assert not found(origin)
        proposal = change(author,"propose",{"request_id":f"pilot-{tag}-propose","target_url":origin,"comparison_url":peer,
                          "revisions":pair_pins,"title":title,"expected":expected,"kind":"source-only"})
        ident = proposal["task"]
        change(reader,"queue",{"task":ident,"request_id":f"pilot-{tag}-queue","note":"Reviewed exact public pins and the scope of a source comparison"})
        card=build_lab(cat,task=ident)["tasks"][0]
        request=consent("claim",ident,f"pilot-{tag}-claim")
        assert not tool(client_a,author,"portbridge_change_lab",request)
        denied=tool(client_a,author,"portbridge_change_lab",{**request,"consent":False},writes=True)
        assert denied["isError"]
        claim=tool(client_a,author,"portbridge_change_lab",request,writes=True)["structuredContent"]
        assert claim["state"]=="claimed"
        payload={"revisions":pair_pins,"environment":f"Isolated {platform.system()} Python clients; public pinned sources","equipment":"CPU only",
                 "commands":"python audit/verify_pilot_sources.py","outcome":result,"expected":expected,"observed":observed,
                 "artifact_sha256":sha256(artifact).hexdigest(),"source_url":receipt["checks"][tag][0]["source"],
                 "limitations":"Source-level comparison. No emulator, game files, or graphics device were run.",
                 "ai_assistance":"Codex scripted the bounded source checks","share_public":True}
        submission=consent("submit",ident,f"pilot-{tag}-submit",report=payload)
        sent=tool(client_a,author,"portbridge_change_lab",submission,writes=True)["structuredContent"]
        assert sent["report_status"]=="valid_format" and not found(origin)
        assert tool(client_a,author,"portbridge_change_lab",submission,writes=True)["structuredContent"]==sent
        check=tool(client_b,reader,"portbridge_my_lab",{"task":ident},version="2025-06-18")["structuredContent"]
        assert check["reports"][0]["id"]==sent["report_id"]
        decision=change(reader,"review",{"task":ident,"request_id":f"pilot-{tag}-review","decision":"reviewed",
                    "report_id":sent["report_id"],"checked_artifact":True,"note":"Checked pinned source hashes, anchors, scope and limitations",
                    "hypothesis_rejected":result=="FAIL"})
        impacts=found(origin)
        assert any(story["id"]==sent["report_id"] for story in impacts)
        output.append({"case":tag,"origin":origin,"peer":peer,"search":{"indexed":prior.get("indexed"),
                       "catalog_status":prior.get("catalog_status"),"source_count":len(prior.get("observations",[])),
                       "research":(prior.get("discovery") or {}).get("automatic_matches",[])},
                       "task":ident,"revisions":pair_pins,"prompt":card.get("prompt"),"report":payload,
                       "format":sent["report_status"],"review":decision,"impact":impacts,
                       "reviewer_read_independent_endpoint":True})
    before=public_feed(cat,now=now)
    _,cursor=digest(before,{},now=now)
    last=output[-1]
    target_result=next(item for item in before["items"] if item["kind"]=="result" and item["source"]==last["report"]["source_url"])
    retract=consent("withdraw_report",last["task"],"pilot-xcl-withdraw",report_id=last["review"]["report_id"])
    tool(client_a,author,"portbridge_change_lab",retract,writes=True)
    assert not found(last["origin"])
    changes,_=digest(public_feed(cat,now=now+1),cursor,now=now+1)
    assert target_result["id"] in changes["no_longer_listed"]
    assert all(not list(folder.rglob("*.sqlite3")) for folder in (client_a,client_b))
    report={"mode":"local protocol clients; real pinned sources; volunteer and reviewer are test principals",
            "cases":output,"router":radar,"withdrew":last["case"],"subscription_removal":True,
            "independent_client_directories":True,"external_adoption":False}
    (work/"pilot.json").write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n",encoding="utf8")
    print(json.dumps({"host_os": platform.system(), "external_adoption": False,
                      "results": [[x["case"], x["report"]["outcome"]] for x in output]}))
finally:
    server.shutdown()
    server.server_close()
    thread.join()
