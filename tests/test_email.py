"""Email report: delivered over SMTP to a local stand-in server, HTML escaped and well-formed."""
import email
import socketserver
import threading
from email import policy

import pytest

from adpulse.config import Settings
from adpulse.reports import delivery, weekly

pytestmark = pytest.mark.integration


class _SMTP(socketserver.StreamRequestHandler):
    """Just enough SMTP (EHLO/AUTH/MAIL/RCPT/DATA/QUIT) to capture one message."""
    messages: list = []

    def reply(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())

    def handle(self):
        rcpt, data_mode, buf = [], False, []
        self.reply("220 test ESMTP")
        for raw in self.rfile:
            line = raw.decode().rstrip("\r\n")
            if data_mode:
                if line == ".":
                    data_mode = False
                    _SMTP.messages.append({"rcpt": rcpt, "data": "\r\n".join(buf)})
                    self.reply("250 queued")
                else:
                    buf.append(line[1:] if line.startswith("..") else line)
                continue
            cmd = line.split(" ")[0].upper()
            if cmd in ("EHLO", "HELO"):
                self.wfile.write(b"250-test\r\n250 AUTH PLAIN LOGIN\r\n")
            elif cmd == "AUTH":
                self.reply("235 ok")
            elif cmd == "RCPT":
                rcpt.append(line.split(":", 1)[1].strip(" <>"))
                self.reply("250 ok")
            elif cmd == "DATA":
                data_mode = True
                self.reply("354 go")
            elif cmd == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


@pytest.fixture()
def smtp_server():
    _SMTP.messages = []
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTP)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def report(db):
    r = weekly.build()
    r.commentary = r.commentary + ["Check <script>alert(1)</script> & co"]
    return r


def _settings(port, **kw):
    return Settings(smtp_host="127.0.0.1", smtp_port=port, smtp_security="none", smtp_user="u", smtp_password="p",
                    report_email_from="adpulse@example.com", report_email_to="a@example.com; b@example.com",
                    app_base_url="https://adpulse.example.com", **kw)


def test_email_delivered_to_all_recipients(smtp_server, report):
    assert delivery.send_email(report, _settings(smtp_server)) == "sent"
    (m,) = _SMTP.messages
    assert m["rcpt"] == ["a@example.com", "b@example.com"]
    msg = email.message_from_string(m["data"], policy=policy.default)
    assert "AdPulse weekly report" in msg["Subject"]
    assert msg.get_body("plain") is not None
    body = msg.get_body("html").get_content()
    assert "&lt;script&gt;" in body and "<script>" not in body  # commentary is escaped
    assert "https://adpulse.example.com/recommendations" in body
    for k in report.kpis:
        assert k.text() in body


def test_email_errors_are_reported_not_raised(report):
    s = _settings(1)  # nothing listens on port 1
    assert delivery.send_email(report, s).startswith("error:")
    assert delivery.send_email(report, _settings(1).model_copy(update={"report_email_to": ""})) \
        == "error: REPORT_EMAIL_TO is empty"
