"""The HTTP API the React web app uses (api/main.py). No database needed for these checks."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api import main

client = TestClient(main.app)


def test_healthz_is_up_without_database():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_clean_makes_frames_json_safe():
    df = pd.DataFrame({"d": [pd.Timestamp("2026-11-22")], "x": [np.float64("nan")], "n": [np.int64(3)]})
    out = main.clean({"rows": df, "day": date(2026, 11, 22), "inf": math.inf})
    assert out == {"rows": [{"d": "2026-11-22T00:00:00", "x": None, "n": 3}], "day": "2026-11-22", "inf": None}


def test_cors_allows_local_dev_and_project_previews_only():
    ok = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    preview = client.get("/healthz", headers={"Origin": "https://adpulse-git-main-team.vercel.app"})
    assert preview.headers.get("access-control-allow-origin") == "https://adpulse-git-main-team.vercel.app"
    other = client.get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in other.headers


def test_unknown_refresh_job_is_404():
    assert client.get("/api/data/jobs/nope").status_code == 404
