import pandas as pd
import pytest
from cryptography.fernet import Fernet

from isotherm import shadow_state as ss


@pytest.fixture
def ledger(tmp_path):
    pd.DataFrame(
        {
            "ticker": ["T1"],
            "bid": [0.3],
            "ask": [0.35],
            "p_market": [0.32],
            "p_model": [0.4],
            "volume_at_read": [10],
        }
    ).to_csv(tmp_path / "predictions.csv", index=False)
    pd.DataFrame(
        {
            "ticker": ["T1"],
            "side": ["yes"],
            "price": [0.35],
            "ev_per_contract": [0.05],
            "contracts_intended": [3],
        }
    ).to_csv(tmp_path / "trades.csv", index=False)
    pd.DataFrame({"ticker": ["T1"], "y": [1], "final_volume": [99]}).to_csv(
        tmp_path / "outcomes.csv", index=False
    )
    return tmp_path


def test_pack_hides_market_columns_and_unpack_restores_them(ledger):
    key = Fernet.generate_key().decode()
    full = {f: (ledger / f).read_text() for f in ("predictions.csv", "trades.csv", "outcomes.csv")}
    ss.pack(ledger, key)
    pub = pd.read_csv(ledger / "predictions.csv")
    assert list(pub.columns) == ["ticker", "p_model"]
    assert list(pd.read_csv(ledger / "trades.csv").columns) == ["ticker", "side", "contracts_intended"]
    assert list(pd.read_csv(ledger / "outcomes.csv").columns) == ["ticker", "y"]
    assert b"0.35" not in (ledger / ss.STATE).read_bytes()
    assert ss.unpack(ledger, key)
    assert {f: (ledger / f).read_text() for f in full} == full


def test_wrong_key_cannot_read_the_state(ledger):
    ss.pack(ledger, Fernet.generate_key().decode())
    with pytest.raises(Exception):  # noqa: B017 (cryptography raises InvalidToken)
        ss.unpack(ledger, Fernet.generate_key().decode())


def test_first_run_has_no_state(tmp_path):
    assert ss.unpack(tmp_path, Fernet.generate_key().decode()) is False
