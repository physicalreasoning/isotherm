#!/usr/bin/env python3
"""Check a Kalshi API key works and measure the sustained read rate it gets.

    KALSHI_API_KEY_ID=... KALSHI_PRIVATE_KEY_PATH=~/.kalshi/key.pem \\
        uv run scripts/kalshi_auth_check.py

Only GETs. `/portfolio/balance` needs a valid signature and returns your
balance, which is printed as ok/failed, never the amount.
"""

import pathlib
import sys
import time
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pmdecide import kalshi  # noqa: E402

if not (kalshi.KEY_ID and kalshi.KEY_PATH):
    sys.exit("set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH first")
try:
    kalshi.get("portfolio/balance")
    print("signature: ok")
except urllib.error.HTTPError as e:
    sys.exit("signature: failed (HTTP {})".format(e.code))

kalshi.MIN_INTERVAL = 0.0
n, t0, limited = 0, time.time(), 0
while time.time() - t0 < 20:
    try:
        kalshi._fetch(kalshi.BASE + "/historical/cutoff")
        n += 1
    except urllib.error.HTTPError as e:
        limited += e.code == 429
print(
    "sustained: {:.1f} req/s over 20s, {} rate-limited (anonymous was ~3.5 req/s)".format(
        n / (time.time() - t0), limited
    )
)
print("suggested: export KALSHI_MIN_INTERVAL={:.3f}".format(max(0.02, 1.25 * (time.time() - t0) / max(n, 1))))
