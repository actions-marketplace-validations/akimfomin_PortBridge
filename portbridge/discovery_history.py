"""Select a bounded history lookup for a receiving project's own code."""
from collections import Counter
from datetime import datetime
import re

from .discovery_terms import API_SYMBOL, DISCOVERY_SYMBOL
from .matching import ISA_OPCODE


# Only a complete inline code span can nominate a symbol, never an entire
# shell command, filename, string literal, stack trace or paragraph.
IDENT = re.compile(r"[A-Za-z][A-Za-z0-9]{0,19}(?:_[A-Za-z][A-Za-z0-9]{0,19}){1,4}", re.ASCII)
CODE_SPAN = re.compile(r"(?<!\x60)\x60([A-Za-z][A-Za-z0-9_]{5,59})\x60(?!\x60)")
WORD = re.compile(r"[A-Za-z0-9_]+")
FENCE = re.compile(r"^[ \t]*(\x60{3,}|~{3,})(.*)$")
PRIVATE_LINE = re.compile(r"(?i)\b(?:e-?mail|contact|handle|password|credential|access token)\b|[\w.+-]+@[\w.-]+|(?<!\w)@[\w-]+")
TECHNICAL = re.compile(r"\b(?:code|function|class|method|call|tests?|build|runtime|compiler|launcher|config|"
                       r"cache|flags?|buffer|field|parser|implementation|command|module|pipeline|mapping)\b", re.I)
SENSITIVE = re.compile(r"(?:^|_)(?:key|secret|token|password|passwd|bearer|credential|authorization|email)(?:_|$)", re.I)
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def valid_identifier(value):
    return (isinstance(value, str) and 6 <= len(value) <= 60 and IDENT.fullmatch(value)
            and (value.islower() or value.isupper()) and not SENSITIVE.search(value)
            and not value.lower().startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_", "sk_"))
            and not DISCOVERY_SYMBOL.fullmatch(value) and not ISA_OPCODE.fullmatch(value))


def history_identifier(text):
    # Count mentions in the author's technical prose; quoted logs, markup
    # comments, fenced code and contact lines cannot corroborate an identifier.
    lines = []
    fence = ""
    for line in re.sub(r"<!--.*?(?:-->|\Z)", " ", text, flags=re.S).splitlines():
        marker = FENCE.match(line)
        if marker and not fence:
            fence = marker[1]
            continue
        if fence:
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = ""
            continue
        if not line.lstrip().startswith(">") and not PRIVATE_LINE.search(line):
            lines.append(line)
    prose = "\n".join(lines)
    if not TECHNICAL.search(prose):
        return ""
    # Keep the existing cross-project route for precise shared calls and opcodes.
    if (API_SYMBOL.search(prose) or ISA_OPCODE.search(prose)
            or any(not match[0].isupper() for match in DISCOVERY_SYMBOL.finditer(prose))):
        return ""
    nominations = dict.fromkeys(m[1] for m in CODE_SPAN.finditer(prose) if valid_identifier(m[1]))
    if not nominations:
        return ""
    counts = Counter(WORD.findall(prose))
    return max((term for term in nominations if counts[term] >= 2), key=counts.get, default="")


def prior_lookup(row):
    meta = row.get("metadata", {})
    term = (meta.get("technical") or {}).get("history_identifier")
    created = meta.get("created_at")
    if not valid_identifier(term) or not isinstance(created, str) or not STAMP.fullmatch(created):
        return None
    try:
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return term, created
