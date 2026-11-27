"""Select public source files from reviewed directories in an immutable Git tree."""

from hashlib import sha256
import json
import os
from pathlib import PurePosixPath
import re
from urllib.request import Request, build_opener

MAX_TREE_BYTES = 4_000_000
MAX_FILE_BYTES = 1_150_000
MAX_SELECTED = 10
CACHE = "code-tree-selection-v1:"
BLOB_SHA = re.compile(r"[0-9a-f]{40}")
SOURCE_PATH = re.compile(r"(?:[A-Za-z0-9_-][A-Za-z0-9_+.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_+.-]*")
EXTENSIONS = {".c", ".cpp", ".h", ".hpp", ".rs", ".py", ".adoc", ".rst"}
FAMILIES = tuple(re.compile(pattern) for pattern in (
    r"wsi|present|surface|swapchain", r"sync|semaphore|fence|barrier",
    r"shader|pipeline|wave", r"memory|resource|heap", r"descriptor|binding",
    r"render|image|texture", r"command|queue|copy",
))
EXCLUDE = re.compile(r"(?:^|[/_.-])(?:generated|headers|external|third.party|vendor|secret|keys?|auth|drm)(?:$|[/_.-])", re.I)


def cache_key(group):
    rules = json.dumps([group["directories"], group["limit"], group["files"]], sort_keys=True).encode()
    suffix = sha256(rules).hexdigest()[:12]
    return f"{CACHE}{group['repo']}@{group['revision']}:{suffix}"


def valid_file(group, path):
    return (isinstance(path, str) and SOURCE_PATH.fullmatch(path) and not EXCLUDE.search(path)
            and any(path.startswith(directory + "/") for directory in group["directories"])
            and PurePosixPath(path).suffix in EXTENSIONS)


def fetch_tree(group):
    from .github import NoRedirect
    address = f"https://api.github.com/repos/{group['repo']}/git/trees/{group['revision']}?recursive=1"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "PortBridge-readonly-code-index"}
    token = os.environ.get("PORTBRIDGE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    with build_opener(NoRedirect()).open(Request(address, headers=headers), timeout=8) as response:
        body = response.read(MAX_TREE_BYTES + 1)
    if len(body) > MAX_TREE_BYTES:
        raise ValueError("Source tree exceeds the response budget")
    return json.loads(body)


def select(group, tree):
    if not isinstance(tree, dict) or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
        raise ValueError("Incomplete Git tree")
    candidates = []
    excluded = set(group.get("already_indexed", ()))
    for entry in tree["tree"]:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        size = entry.get("size")
        digest = entry.get("sha")
        if (entry.get("type") != "blob" or entry.get("mode") != "100644"
                or not valid_file(group, path) or path in excluded or type(size) is not int
                or not 0 < size <= MAX_FILE_BYTES or not isinstance(digest, str) or not BLOB_SHA.fullmatch(digest)):
            continue
        stem = PurePosixPath(path).stem.casefold()
        families = [index for index, pattern in enumerate(FAMILIES) if pattern.search(stem)]
        if families:
            candidates.append((len(stem), path.count("/"), size, path, digest, families))
    ranked = sorted(candidates)
    selected = {}
    for family in range(len(FAMILIES)):
        best = next((row for row in ranked if family in row[-1]), None)
        if best:
            selected[best[3]] = best[4]
    for _, _, _, path, digest, _ in ranked:
        if len(selected) >= group["limit"]:
            break
        selected.setdefault(path, digest)
    return [{"path": path, "blob": digest} for path, digest in list(selected.items())[:group["limit"]]]
