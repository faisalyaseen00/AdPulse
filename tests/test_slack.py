"""Slack report: Block Kit limits + delivery against a local stand-in for Slack's webhook."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from adpulse.config import Settings
from adpulse.reports import delivery, weekly

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def report(db):
    return weekly.build()


def test_blocks_within_slack_limits(report):
    blocks = weekly.to_slack_blocks(report, "https://adpulse.example.com")
    assert 0 < len(blocks) <= 50
    for b in blocks:
        if b["type"] == "header":
            assert b["text"]["type"] == "plain_text" and len(b["text"]["text"]) <= 150
        if b["type"] == "section":
            assert "text" in b or "fields" in b
            if "text" in b:
                assert 0 < len(b["text"]["text"]) <= 3000
            for f in b.get("fields", []):
                assert len(f["text"]) <= 2000
            assert len(b.get("fields", [])) <= 10
        if b["type"] == "actions":
            for el in b["elements"]:
                assert len(el["text"]["text"]) <= 75 and el["url"].startswith("http")
    assert json.dumps(blocks)  # serialisable


class _Hook(BaseHTTPRequestHandler):
    status = 200
    received: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append(json.loads(body))
        self.send_response(_Hook.status)
        self.end_headers()
        self.wfile.write(b"ok" if _Hook.status == 200 else b"invalid_blocks")

    def log_message(self, *a):
        pass


@pytest.fixture
def hook():
    srv = HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Hook.received.clear()
    yield f"http://127.0.0.1:{srv.server_port}/services/T000/B000/XXX"
    srv.shutdown()


def test_webhook_send_success(report, hook):
    _Hook.status = 200
    res = delivery.send_slack(report, Settings(slack_webhook_url=hook, slack_bot_token=""))
    assert res == "sent"
    msg = _Hook.received[0]
    assert msg["text"].startswith("AdPulse weekly report")
    assert msg["blocks"][0]["type"] == "header"


def test_webhook_error_reported(report, hook):
    _Hook.status = 400
    res = delivery.send_slack(report, Settings(slack_webhook_url=hook, slack_bot_token=""))
    assert res.startswith("error") and "400" in res
