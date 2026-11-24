"""Opt-in HTTP routes for the local, human-reviewed exchange queue."""

import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .catalog import PROBLEM_ID
from .exchange import AuthError, Conflict, PermissionDenied
from .preflight import preflight


PREFIX = "/api/v1/exchange"
MAX_BODY_BYTES = 64 * 1024
MAX_CURSOR = (1 << 63) - 1
ROUTES = {
    "poll": ("read", "GET, HEAD"),
    "work": ("read", "GET, HEAD"),
    "evidence": ("read", "GET, HEAD"),
    "preflight": ("read", "GET, HEAD"),
    "pending": ("review", "GET, HEAD"),
    "register": ("contribute", "POST"),
    "submit": ("contribute", "POST"),
    "review": ("review", "POST"),
}
QUERY_KEYS = {
    "poll": {"after", "limit"}, "work": {"problem_id"},
    "evidence": {"problem_id", "limit"}, "pending": {"limit"},
    "preflight": {"q", "url", "limit"},
}


class ExchangeRequestError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def positive_query(value, start, end):
    if not value.isascii() or not value.isdecimal() or len(value) > len(str(end)):
        raise ValueError("invalid integer")
    number = int(value)
    if not start <= number <= end:
        raise ValueError("integer out of range")
    return number


def unique_json_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON key")
    return result


def reject_non_json(_value):
    raise ValueError("invalid JSON value")


class ExchangeHandlerMixin:
    def handle_exchange(self, raw_path, method, *, head=False):
        """Handle our namespace when mounted on a loopback HTTP handler."""
        try:
            target = urlsplit(raw_path)
        except ValueError:
            return False
        if target.path != PREFIX and not target.path.startswith(f"{PREFIX}/"):
            return False

        head = head or method == "HEAD"
        exchange = getattr(self.server, "exchange", None)
        route = target.path.removeprefix(f"{PREFIX}/")
        if exchange is None or route not in ROUTES:
            self.exchange_response(404, {"error": "exchange route unavailable"}, head=head)
            return True
        if target.scheme or target.netloc or target.fragment or not self.exchange_request_origin():
            self.exchange_response(403, {"error": "same-origin localhost requests only"}, head=head)
            return True
        scope, allow = ROUTES[route]
        if method not in allow.split(", "):
            self.exchange_response(405, {"error": "method not allowed"}, head=head, allow=allow)
            return True

        try:
            token = self.exchange_token()
            if scope not in exchange.authenticate(token)["scopes"]:
                raise ExchangeRequestError(403, "insufficient exchange permission")
            result = (self.exchange_write(exchange, token, route, target.query) if method == "POST"
                      else self.exchange_read(exchange, token, route, target.query))
        except ExchangeRequestError as exc:
            status, result = exc.status, {"error": str(exc)}
        except PermissionDenied:
            status, result = 403, {"error": "insufficient exchange permission"}
        except AuthError:
            status, result = 401, {"error": "invalid or missing exchange token"}
        except Conflict:
            status, result = 409, {"error": "exchange request conflicts with current state"}
        except LookupError:
            status, result = 404, {"error": "exchange record not found"}
        except (ValueError, RecursionError):
            status, result = 400, {"error": "invalid exchange input"}
        except sqlite3.Error:
            status, result = 503, {"error": "local exchange temporarily unavailable"}
        else:
            status = 200
        self.exchange_response(status, result, head=head)
        return True

    def exchange_request_origin(self):
        # Compare against the actual loopback endpoint, never forwarding headers.
        if self.server.server_address[0] != "127.0.0.1" or self.client_address[0] != "127.0.0.1":
            return False
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        site = self.headers.get_all("Sec-Fetch-Site", [])
        if len(hosts) != 1 or len(origins) > 1 or len(site) > 1:
            return False
        host = hosts[0].lower()
        port = self.server.server_port
        if host not in {"127.0.0.1", "localhost", f"127.0.0.1:{port}", f"localhost:{port}"}:
            return False
        if site and site[0] not in {"same-origin", "none"}:
            return False
        suffix = f":{port}" if port != 80 else ""
        return not origins or origins[0].lower() == f"http://{host.split(':', 1)[0]}{suffix}"

    def exchange_token(self):
        auth = self.headers.get_all("Authorization", [])
        if len(auth) == 1 and len(auth[0]) <= 256:
            parts = auth[0].split()
            if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].isascii():
                return parts[1]
        raise ExchangeRequestError(401, "invalid or missing exchange token")

    def exchange_read(self, exchange, token, route, query):
        values = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
        if values.keys() - QUERY_KEYS[route] or any(len(items) != 1 for items in values.values()):
            raise ValueError("unexpected or duplicate query fields")
        args = {key: items[0] for key, items in values.items()}
        ident = args.get("problem_id")
        if ident is not None and (len(ident) > 70 or not PROBLEM_ID.fullmatch(ident)):
            raise ValueError("invalid problem ID")
        if route == "work":
            return {"work": exchange.active_work(token, problem_id=ident)}
        if route == "preflight":
            catalog = getattr(self.server, "catalog", None)
            if catalog is None:
                raise ExchangeRequestError(404, "local catalog unavailable")
            limit = positive_query(args.get("limit", "5"), 1, 20)
            result = preflight(catalog, q=args.get("q", ""), url=args.get("url", ""), limit=limit)
            reports = [report for problem in result["problems"]
                       for report in exchange.evidence(token, problem["id"], limit=limit)]
            return {**result, "reviewed_reports": reports}
        limit = positive_query(args.get("limit", "50"), 1, 100)
        if route == "evidence":
            if ident is None:
                raise ValueError("problem ID required")
            return {"results": exchange.evidence(token, ident, limit=limit)}
        if route == "pending":
            return {"results": exchange.pending_results(token, limit=limit)}
        after = positive_query(args.get("after", "0"), 0, MAX_CURSOR)
        return exchange.poll_events(token, after=after, limit=limit)

    def exchange_read_json(self):
        if self.headers.get_all("Transfer-Encoding"):
            raise ExchangeRequestError(400, "transfer encoding unsupported")
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].partition(";")[0].strip().lower() != "application/json":
            raise ExchangeRequestError(415, "application/json required")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
            raise ExchangeRequestError(400, "one valid content length required")
        raw_length = lengths[0].lstrip("0")
        if len(raw_length) > len(str(MAX_BODY_BYTES)) or int(raw_length or "0") > MAX_BODY_BYTES:
            raise ExchangeRequestError(413, "exchange body too large")
        length = int(raw_length or "0")
        self.connection.settimeout(3)
        try:
            raw = self.rfile.read(length)
        except TimeoutError as exc:
            raise ExchangeRequestError(408, "exchange request timed out") from exc
        except ConnectionResetError as exc:
            raise ExchangeRequestError(400, "incomplete exchange request") from exc
        if len(raw) != length:
            raise ValueError("incomplete body")
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_object, parse_constant=reject_non_json)
        if not isinstance(body, dict):
            raise ValueError("expected JSON object")
        return body

    def exchange_write(self, exchange, token, route, query):
        if query:
            raise ValueError("write routes do not accept query parameters")
        body = self.exchange_read_json()
        if route == "register":
            if body.keys() - {"problem_id", "ttl_seconds"} or "problem_id" not in body:
                raise ValueError("invalid registration fields")
            return {"work": exchange.register_work(token, body["problem_id"], ttl_seconds=body.get("ttl_seconds", 3600))}
        if route == "submit":
            return {"result": exchange.submit_result(token, body)}
        if body.keys() - {"result_id", "decision", "reason"} or not {"result_id", "decision"} <= body.keys():
            raise ValueError("invalid review fields")
        return {"result": exchange.review_result(token, body["result_id"], decision=body["decision"],
                                                reason=body.get("reason", ""))}

    def exchange_response(self, status, payload, *, head=False, allow=None):
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        # Close even on rejection, so an unread request body is never a new request.
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if status == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="PortBridge Exchange"')
        if allow:
            self.send_header("Allow", allow)
        try:
            self.end_headers()
            if not head:
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
