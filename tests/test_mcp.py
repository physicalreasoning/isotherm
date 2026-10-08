"""MCP tools: same answers as the REST API, clean errors, and every answer logged (no network)."""

import asyncio
import json

import numpy as np
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from isotherm import mcp_server, shadow
from isotherm.weather import bucket_interval

LADDER = [("less", None, 68), ("between", 68, 69), ("between", 70, 71), ("greater", 71, None)]
IV = [bucket_interval(*b) for b in LADDER]
P = np.array([0.1, 0.5, 0.3, 0.1])


@pytest.fixture
def log(monkeypatch, tmp_path):
    fake = {
        "event": "KXHIGHNY-26OCT06",
        "rows": [{"ticker": "T{}".format(j)} for j in range(4)],
        "iv": IV,
        "bid": np.array([0.08, 0.48, 0.28, 0.08]),
        "ask": np.array([0.10, 0.50, 0.30, 0.10]),
        "p_market": P,
        "p_emos": P,
        "p_model": P,
        "mu": 69.4,
        "sigma": 2.0,
        "gfs_fcst": 69.0,
        "gfs_runtime": "2026-10-05 12:00:00+00:00",
    }
    monkeypatch.setattr(shadow, "predict_city", lambda *a, **k: fake)
    path = tmp_path / "answers.jsonl"
    monkeypatch.setenv("ISOTHERM_ANSWER_LOG", str(path))
    return path


def call(name, args):
    r = asyncio.run(mcp_server.mcp.call_tool(name, args))
    return json.loads(r.content[0].text)


def test_tools_are_listed():
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert names == {"cities", "ladder", "probability", "decide"}


def test_probability_matches_the_buckets_and_is_logged(log):
    r = call("probability", {"city": "ny", "at_least": 70, "day": "2026-10-06"})
    assert np.isclose(r["probability"], 0.4)  # 70-71 bucket + >71 tail
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["via"] == "mcp" and rec["city"] == "NY" and np.isclose(sum(rec["dist"]["p"]), 1, atol=1e-4)


def test_decide_is_coherent(log):
    r = call(
        "decide",
        {
            "city": "NY",
            "day": "2026-10-06",
            "questions": [
                {
                    "kind": "choice",
                    "options": [{"hi": 67}, {"lo": 68, "hi": 69}, {"lo": 70, "hi": 71}, {"lo": 72}],
                },
                {"kind": "score", "stat": "quantiles", "q": [0.1, 0.5, 0.9]},
            ],
        },
    )
    assert np.allclose(r["answers"][0]["probabilities"], P)
    q = r["answers"][1]["value"]
    assert q[0] <= q[1] <= q[2]


def test_errors_are_tool_errors(log):
    with pytest.raises(ToolError, match="unknown city"):
        call("probability", {"city": "Boston", "at_least": 70})
    with pytest.raises(ToolError, match="at_least"):
        call("probability", {"city": "NY"})
