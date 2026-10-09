"""Service: integer distribution coherence and the HTTP contract (no network)."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from isotherm import serve, shadow
from isotherm.weather import bucket_interval

LADDER = [("less", None, 68), ("between", 68, 69), ("between", 70, 71), ("greater", 71, None)]
IV = [bucket_interval(*b) for b in LADDER]
P = np.array([0.1, 0.5, 0.3, 0.1])


def test_integer_distribution_reproduces_bucket_probabilities():
    d = serve.integer_distribution(P, IV, mu=69.4, sigma=2.0)
    for (lo, hi), pj in zip(IV, P, strict=True):
        mass = d.p[(d.v + 0.5 > lo) & (d.v - 0.5 < hi)].sum()
        assert np.isclose(mass, pj)
    assert np.isclose(d.p.sum(), 1.0)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ISOTHERM_ANSWER_LOG", str(tmp_path / "answers.jsonl"))
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
    return TestClient(serve.app)


def test_decide_answers_typed_questions_coherently(client):
    r = client.post(
        "/decide",
        json={
            "city": "NY",
            "day": "2026-10-06",
            "questions": [
                {
                    "kind": "choice",
                    "options": [{"hi": 67}, {"lo": 68, "hi": 69}, {"lo": 70, "hi": 71}, {"lo": 72}],
                },
                {"kind": "noul", "set": {"lo": 70}},
                {"kind": "score", "stat": "quantiles", "q": [0.1, 0.5, 0.9]},
            ],
        },
    )
    assert r.status_code == 200
    a = r.json()["answers"]
    assert np.allclose(a[0]["probabilities"], P)
    assert np.isclose(a[1]["probabilities"][0], 0.4)  # 70-71 bucket + >71 tail
    assert a[2]["value"][0] <= a[2]["value"][1] <= a[2]["value"][2]
    assert r.json()["disagreement"] == 0.0  # the fake model equals the market


def test_ladder_and_health(client):
    r = client.get("/ladder/NY", params={"day": "2026-10-06"})
    assert r.status_code == 200 and r.json()["buckets"][0]["lo"] is None
    assert client.get("/health").json()["status"] == "ok"


def test_bad_requests_are_rejected(client):
    assert client.get("/ladder/XYZ").status_code == 404
    bad = {"city": "NY", "questions": [{"kind": "choice", "options": [{"lo": 1}]}]}
    assert client.post("/decide", json=bad).status_code == 422
