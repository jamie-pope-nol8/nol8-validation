#!/usr/bin/env python3
"""Themis adapter: speak the benchmark's contract, back it with real Themis.

The pre-index / inference / agent-mesh benchmark harness (from
preindex-benchmark-kit) calls a governance endpoint with:

    POST {"text": "<content>"}  ->  {"action": "keep|mask|drop|route", "text": "<content>"}

Themis speaks a redaction-only contract:

    POST {"message": "<content>"} -> {"jid":..., "result": {"message": "<content>"}}

This adapter sits between them: it accepts the benchmark request, calls Themis,
and derives the benchmark's `action` from what Themis did to the text. Point the
harness's NOL8_ENDPOINT at this adapter.

Action derivation:
  - text unchanged                -> "keep"   (nothing matched the policy)
  - text changed                  -> "mask"   (something was redacted)
  - a DROP sentinel appears       -> "drop"   (text returned empty)
  - a ROUTE sentinel appears      -> "route"
Drop/route are opt-in: they only fire when the policy maps a governed value to a
configured sentinel token (THEMIS_DROP_TOKEN / THEMIS_ROUTE_TOKEN), which is how
the benchmark's governance semantics are expressed as Themis policy. Without
sentinels the adapter covers keep/mask, which is the redaction core.

Configuration (environment; source config/demo.env + .env, or export directly):
  THEMIS_PROCESS_ENDPOINT   required - the /v1/process URL (valid cert, no -k)
  THEMIS_TOKEN              required - bearer token
  THEMIS_DROP_TOKEN         optional - sentinel replacement meaning "drop"
  THEMIS_ROUTE_TOKEN        optional - sentinel replacement meaning "route"
  ADAPTER_PORT              optional - listen port (default 8799)
"""

from __future__ import annotations

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

# The four actions the benchmark understands.
ACTION_KEEP = "keep"
ACTION_MASK = "mask"
ACTION_DROP = "drop"
ACTION_ROUTE = "route"


def derive_action(
    original: str,
    processed: str,
    *,
    drop_token: str | None = None,
    route_token: str | None = None,
) -> str:
    """Map (original, Themis-processed) text to a benchmark action.

    Sentinels win over plain keep/mask so a policy can express drop/route by
    redacting a governed value to a known token.
    """

    if drop_token and drop_token in processed:
        return ACTION_DROP
    if route_token and route_token in processed:
        return ACTION_ROUTE
    if processed == original:
        return ACTION_KEEP
    return ACTION_MASK


def to_benchmark_response(
    original: str,
    processed: str,
    *,
    drop_token: str | None = None,
    route_token: str | None = None,
) -> dict[str, str]:
    """Build the benchmark's {"action","text"} response from Themis output."""

    action = derive_action(
        original, processed, drop_token=drop_token, route_token=route_token
    )
    # A dropped chunk carries no text onward.
    text = "" if action == ACTION_DROP else processed
    return {"action": action, "text": text}


def call_themis(text: str, *, endpoint: str, token: str, timeout: float = 10.0) -> str:
    """Send one record through Themis and return the processed message.

    Uses the data-plane endpoint, which presents a valid certificate - no TLS
    override needed (unlike the self-signed policy control plane).
    """

    body = json.dumps({"message": text}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("message"), str):
        raise ValueError(f"Unexpected Themis response shape: {payload!r}")
    return result["message"]


class _AdapterConfig:
    def __init__(self) -> None:
        # Generic PROCESS_ENDPOINT/PROCESS_TOKEN let one adapter serve either
        # engine (Themis :443 or Aergia :444); THEMIS_* remain the default.
        self.endpoint = (
            os.environ.get("PROCESS_ENDPOINT")
            or os.environ.get("THEMIS_PROCESS_ENDPOINT", "")
        )
        self.token = os.environ.get("PROCESS_TOKEN") or os.environ.get("THEMIS_TOKEN", "")
        self.drop_token = os.environ.get("THEMIS_DROP_TOKEN") or None
        self.route_token = os.environ.get("THEMIS_ROUTE_TOKEN") or None
        self.port = int(os.environ.get("ADAPTER_PORT", "8799"))

    def require(self) -> None:
        missing = [
            name
            for name, value in (
                ("THEMIS_PROCESS_ENDPOINT", self.endpoint),
                ("THEMIS_TOKEN", self.token),
            )
            if not value
        ]
        if missing:
            raise SystemExit(f"Missing required environment: {', '.join(missing)}")


def _make_handler(config: _AdapterConfig):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - required name
            length = int(self.headers.get("Content-Length", "0"))
            try:
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                text = request["text"]
                processed = call_themis(
                    text, endpoint=config.endpoint, token=config.token
                )
                result = to_benchmark_response(
                    text,
                    processed,
                    drop_token=config.drop_token,
                    route_token=config.route_token,
                )
                self._send(200, result)
            except Exception as error:  # noqa: BLE001 - surface as JSON error
                self._send(502, {"action": "error", "text": "", "error": str(error)})

        def _send(self, status: int, body: dict) -> None:
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args) -> None:  # silence default logging
            return

    return Handler


def main() -> None:
    config = _AdapterConfig()
    config.require()
    server = HTTPServer(("127.0.0.1", config.port), _make_handler(config))
    print(
        f"Themis adapter on http://127.0.0.1:{config.port}  ->  {config.endpoint}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
