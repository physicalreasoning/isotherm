#!/usr/bin/env python3
"""Sealed forward test of the AIFS pool fed by the live AIFS run (FINDINGS §52).

    uv run scripts/aifs_live_forward.py --freeze   # once: hashes, shadow/forward/aifs_live.json
    uv run scripts/build_weather_panel.py && uv run scripts/aifs_live_forward.py   # after the window

Same pool weights as §51 (shadow/forward/aifs.json, hash-checked), but EMOS-AIFS is evaluated on
the AIFS forecast that physicalreasoning/forward captured live at about 20:00 UTC on D-1 (its
public `ledger` branch: the latest run then is the 12z run of D-1, public from 17:52 UTC), instead
of the day-2 archive value. The EMOS parameters are fit on the day-2 history exactly as in §50.
Primary: this pool minus pool(market, EMOS-GFS) with §51's weights. Secondary: minus §51's
three-source pool with day-2 input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import aifs_forward as F  # noqa: E402
import aifs_test as A  # noqa: E402

from isotherm import metrics  # noqa: E402
from isotherm.baselines import _logs, pool  # noqa: E402
from isotherm.dataset import _finish  # noqa: E402
from isotherm.weather import CITIES  # noqa: E402

FROZEN = ROOT / "shadow" / "forward" / "aifs_live.json"
LEDGER_REPO = "https://github.com/physicalreasoning/forward.git"
CODE = ["scripts/aifs_test.py", "scripts/aifs_forward.py", "scripts/aifs_live_forward.py"]


def sha(p) -> str:
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def live_aifs(tmp: pathlib.Path) -> dict[str, pd.Series]:
    """{city: AIFS daily max by target day} from forward's ledger branch (captures at the read)."""
    d = tmp / "forward-ledger"
    if not d.exists():
        subprocess.run(
            ["git", "clone", "-q", "--branch", "ledger", "--depth", "1", LEDGER_REPO, str(d)], check=True
        )
    out: dict[str, dict] = {k: {} for k in CITIES}
    for f in sorted((d / "ledger").glob("*.json")):
        rec = json.loads(f.read_text())
        captured = pd.Timestamp(rec["captured_at"]).tz_convert("UTC")
        for r in rec["rows"]:
            if r.get("station") in out and r.get("aifs") is not None:
                day = pd.Timestamp(r["day"])
                # The run behind the value must be public before the read: 12z of D-1 at 17:52 UTC.
                if captured < (day - pd.Timedelta(days=1)).tz_localize("UTC") + pd.Timedelta(
                    hours=23, minutes=52
                ):
                    out[r["station"]].setdefault(day, float(r["aifs"]))
    return {k: pd.Series(v, dtype=float) for k, v in out.items()}


def freeze():
    if FROZEN.exists():
        raise SystemExit(f"{FROZEN} exists: frozen once")
    rec = {
        "frozen_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window": list(F.WINDOW),
        "weights_from": "shadow/forward/aifs.json",
        "weights_sha256": hashlib.sha256(F.FROZEN.read_bytes()).hexdigest(),
        "code_sha256": {p: sha(p) for p in CODE},
    }
    FROZEN.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


def score(tmp: pathlib.Path):
    fz = json.loads(FROZEN.read_text())
    changed = [p for p, h in fz["code_sha256"].items() if sha(p) != h]
    if hashlib.sha256(F.FROZEN.read_bytes()).hexdigest() != fz["weights_sha256"]:
        changed.append("shadow/forward/aifs.json")
    if changed:
        raise SystemExit(f"changed since the freeze: {changed}")
    w = json.loads(F.FROZEN.read_text())["weights"]
    ls = F.ladders(refetch=True)
    d = ls.meta["day"]
    t = np.flatnonzero(((d >= F.WINDOW[0]) & (d <= F.WINDOW[1])).to_numpy())
    sub = ls.take(t)
    live = live_aifs(tmp)
    sub.probs["emos_aifs_live"] = np.full(sub.mask.shape, np.nan)
    for key, city in CITIES.items():
        fc = A.aifs_day2(city.station, city.tz).copy()  # the fit history, as in §50
        lv = live[key]
        fc = fc[~fc.index.isin(lv.index)]
        fc = pd.concat([fc, lv]).sort_index()  # in the window, the live value is the input
        A.attach_emos(sub, key, fc, "emos_aifs_live")
    sub.probs["emos_aifs_live"] = _finish(sub.probs["emos_aifs_live"], sub.mask)
    days_live = {k: set(v.index) for k, v in live.items()}
    has_live = np.array(
        [day in days_live[c] for c, day in zip(sub.meta["city"], sub.meta["day"], strict=True)]
    )
    ok = np.flatnonzero(has_live & np.isfinite(sub.probs["emos_aifs_live"]).all(1))
    if len(ok) == 0:
        raise SystemExit("no settled ladders with a live capture in the window (rebuild the panel first)")
    s = sub.take(ok)
    p2 = pool(np.array(w["pool2"]), _logs(s, F.NAMES["pool2"]), s.mask)
    p3 = pool(np.array(w["pool3"]), _logs(s, F.NAMES["pool3"]), s.mask)
    p3l = pool(np.array(w["pool3"]), _logs(s, ["market", "emos_gfs", "emos_aifs_live"]), s.mask)
    loss = {
        k: metrics.log_score(np.where(s.mask, v, 0.0), s.y) for k, v in (("p2", p2), ("p3", p3), ("p3l", p3l))
    }
    days = s.meta["day"].to_numpy()
    res = {
        "window": list(F.WINDOW),
        "ladders": int(len(ok)),
        "complete": bool(len(ok) and s.meta["day"].max() >= pd.Timestamp(F.WINDOW[1])),
        "primary_live_pool3_minus_pool2": A.diff(days, loss["p2"], loss["p3l"]),
        "secondary_live_pool3_minus_day2_pool3": A.diff(days, loss["p3"], loss["p3l"]),
    }
    if res["complete"]:
        res["verdict"] = "PASS" if res["primary_live_pool3_minus_pool2"]["ci"][0] > 0 else "FAIL"
    (ROOT / "results" / "aifs_live_forward.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--tmp", type=pathlib.Path, default=ROOT / "data" / "tmp")
    a = ap.parse_args()
    freeze() if a.freeze else score(a.tmp)
