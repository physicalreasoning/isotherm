"""isotherm as an MCP server: agents ask typed questions about Kalshi daily highs.

The tools call the same functions as the REST API (`isotherm.serve`), so an agent gets the same
frozen model, the same coherent answers and the same answer log.

    uv run isotherm-mcp                          # stdio, for Claude Code / Desktop
    uv run uvicorn isotherm.app:app              # streamable HTTP at /mcp, as deployed

Claude Code: claude mcp add isotherm -- uv run --directory /path/to/isotherm isotherm-mcp
"""

from __future__ import annotations

from typing import List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import serve
from .api import Bucket, Choice, Noul, Score
from .weather import CITIES

INSTRUCTIONS = """isotherm gives calibrated probabilities for Kalshi's daily high-temperature markets
in seven US cities, from a model that combines the market's own prices with NWS forecasts and
beat the market out of sample (physicalreasoning.ai/isotherm). Temperatures are whole °F, as
settled by the NWS Daily Climate Report. Each answer carries `disagreement`, the model's divergence
from the market in nats: near 0 it is repeating the market, larger values mark the answers most
likely to add information (for isotherm's research model, the top fifth by disagreement gained 4 to
10 times the bottom fifth over the market out of sample). A ladder exists once Kalshi lists it,
at 10:00 ET the day before the target day. Every answer for a city-day is read off one
probability distribution, so answers never contradict each other. Probabilities, not advice."""

mcp = MCPServer("isotherm", instructions=INSTRUCTIONS, website_url="https://physicalreasoning.ai/isotherm/")


def _city(city: str) -> str:
    key = city.strip().upper()
    if key not in CITIES:
        raise ToolError("unknown city {!r}; one of {}".format(city, ", ".join(sorted(CITIES))))
    return key


def _run(fn, *a):
    try:
        return fn(*a)
    except serve.NotServable as e:
        raise ToolError(str(e)) from None


@mcp.tool()
def cities() -> dict:
    """The cities isotherm covers, their NWS settlement stations, and the model in use."""
    h = serve.health_payload()
    return {
        "cities": {k: {"station": c.station, "series": c.series} for k, c in CITIES.items()},
        "model": h["model"],
        "model_hash": h["model_hash"],
    }


@mcp.tool()
def ladder(city: str, day: Optional[str] = None) -> dict:
    """Kalshi's live ladder for a city's daily high, with the market's, the forecast's and isotherm's
    probability for every bucket.

    city: NY, CHI, MIA, AUS, LAX, DEN or PHIL. day: target date YYYY-MM-DD (default: tomorrow).
    """
    return _run(serve.ladder_payload, _city(city), day)


@mcp.tool()
def probability(
    city: str, at_least: Optional[int] = None, at_most: Optional[int] = None, day: Optional[str] = None
) -> dict:
    """Probability that a city's daily high (whole °F) falls in a range, e.g. at_least=85 for
    "85°F or higher", at_most=60 for "60°F or lower", both for "between".

    city: NY, CHI, MIA, AUS, LAX, DEN or PHIL. day: target date YYYY-MM-DD (default: tomorrow).
    """
    if at_least is None and at_most is None:
        raise ToolError("give at_least, at_most or both")
    q = Noul(set=Bucket(lo=at_least, hi=at_most))
    r = _run(serve.decide_payload, _city(city), [q], day, "mcp")
    return {
        "city": r.city,
        "day": r.day,
        "probability": r.answers[0].probabilities[0],
        "disagreement": r.disagreement,
        "model_hash": r.model_hash,
    }


@mcp.tool()
def decide(city: str, questions: List[Choice | Noul | Score], day: Optional[str] = None) -> dict:
    """Answer several typed questions about one city-day at once, all from the same distribution.

    Each question is one of:
      {"kind": "choice", "options": [{"hi": 79}, {"lo": 80, "hi": 81}, {"lo": 82}]}  which range wins
      {"kind": "noul", "set": {"lo": 85}}                                     P(high in range)
      {"kind": "score", "stat": "mean" | "quantiles" | "interval", "q": [...], "coverage": 0.8}
    Ranges are inclusive whole °F; omit lo or hi for an open end.
    """
    return _run(serve.decide_payload, _city(city), questions, day, "mcp").model_dump()


def main():
    mcp.run("stdio")


if __name__ == "__main__":
    main()
