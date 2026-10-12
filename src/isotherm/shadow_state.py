"""Keep Kalshi's market data out of the public shadow ledger while scoring still has it.

The shadow workflow (scripts/shadow.py, .github/workflows/shadow.yml) keeps its state on the
public `shadow-ledger` branch. Scoring needs Kalshi's quotes (bid, ask, the price of each paper
trade, volumes), and Kalshi's developer agreement does not let us share them with third parties.
So each run:

  unpack  decrypt state.enc (the full CSVs) over the public ones, if it exists
  ...     score, settle, report as before, on the full files
  pack    encrypt the full CSVs into state.enc, then drop the market columns from the public CSVs

The key is the Actions secret SHADOW_STATE_KEY (a Fernet key; Fernet is AES-128-CBC with an
HMAC-SHA256 tag). Without it state.enc is unreadable. What stays public: our probabilities, the
side and size of each paper trade, outcomes, and the aggregate report.
"""

from __future__ import annotations

import io
import os
import pathlib
import tarfile

import pandas as pd

STATE = "state.enc"
FILES = ("predictions.csv", "trades.csv", "outcomes.csv", "runs.csv")
# Columns that are Kalshi market data, or let it be recovered (ev_per_contract = p_model - price).
MARKET_COLUMNS = {
    "predictions.csv": ["bid", "ask", "p_market", "volume_at_read"],
    "trades.csv": ["price", "ev_per_contract", "volume_at_read"],
    "outcomes.csv": ["final_volume"],
}


def _fernet(key: str | None = None):
    from cryptography.fernet import Fernet

    key = key or os.environ.get("SHADOW_STATE_KEY")
    if not key:
        raise SystemExit("SHADOW_STATE_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def sanitize(root: pathlib.Path) -> None:
    """Drop the market columns from the public CSVs, in place."""
    for name, cols in MARKET_COLUMNS.items():
        f = root / name
        if f.exists():
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            df.drop(columns=[c for c in cols if c in df.columns]).to_csv(f, index=False)


def pack(root: pathlib.Path, key: str | None = None) -> None:
    """Encrypt the full CSVs into state.enc, then sanitize the public copies."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in FILES:
            if (root / name).exists():
                tar.add(root / name, arcname=name)
    (root / STATE).write_bytes(_fernet(key).encrypt(buf.getvalue()))
    sanitize(root)


def unpack(root: pathlib.Path, key: str | None = None) -> bool:
    """Restore the full CSVs from state.enc. False if there is no state yet (first run)."""
    f = root / STATE
    if not f.exists():
        return False
    data = _fernet(key).decrypt(f.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if m.name not in FILES or not m.isfile():
                raise ValueError(f"unexpected member in {STATE}: {m.name}")
            (root / m.name).write_bytes(tar.extractfile(m).read())
    return True
