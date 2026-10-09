# isotherm API and MCP reference

isotherm answers questions about Kalshi's daily high-temperature markets with calibrated
probabilities. It is live at **https://isotherm.onrender.com**:

| | |
|---|---|
| REST | `GET /health`, `GET /ladder/{city}`, `POST /decide`; interactive docs at [`/docs`](https://isotherm.onrender.com/docs) |
| MCP | streamable HTTP at `https://isotherm.onrender.com/mcp`, tools `cities`, `ladder`, `probability`, `decide` |
| Cities | NY (KNYC), CHI (KMDW), MIA (KMIA), AUS (KAUS), LAX (KLAX), DEN (KDEN), PHIL (KPHL) |
| Model | the frozen strategy of [FINDINGS §9](../FINDINGS.md): a log pool of the market's prices and EMOS-calibrated GFS MOS, hash `b200c51ce4ee` |

Free hosting: after 15 idle minutes the server sleeps, and the next request takes up to a minute.
Probabilities, not advice.

## How answers work

For a city and target day, isotherm reads Kalshi's live ladder and the NWS forecast public at that
moment, and forms **one probability distribution over the whole-degree high** that the NWS Daily
Climate Report will record (the number Kalshi settles on). Every answer is read off that one
distribution, so a range probability, a bucket choice and a quantile never contradict each other.
Out of sample, these answers are better calibrated than the market's own prices (FINDINGS §38).

- **Temperatures** are whole °F. **Ranges are inclusive**: `{"lo": 74, "hi": 77}` is 74, 75, 76
  or 77; omit `lo` or `hi` for an open end.
- **`day`** is the target date, `YYYY-MM-DD`; it defaults to tomorrow in the city's time zone.
  A ladder exists once Kalshi lists it, at 10:00 ET the day before the target day.
- **Errors**: an unknown city, or a day with no ladder, quotes or forecast yet, returns a clear
  message (MCP tool error; HTTP 404 or 409).

## Connect an agent

```bash
claude mcp add --transport http isotherm https://isotherm.onrender.com/mcp    # Claude Code, hosted
claude mcp add isotherm -- uv run --directory /path/to/isotherm isotherm-mcp  # local, stdio
```

Any MCP client works: point it at the `/mcp` URL (streamable HTTP, stateless, JSON responses).

## Tools

Examples below are real responses from 2026-10-08, rounded.

### `cities()`

The cities covered, their settlement stations and Kalshi series, and the model in use.

```json
{"cities": {"NY": {"station": "KNYC", "series": "KXHIGHNY"}, "CHI": {"station": "KMDW", "series": "KXHIGHCHI"}, "...": "..."},
 "model": "pool · market+GFS", "model_hash": "b200c51ce4ee"}
```

### `probability(city, at_least=None, at_most=None, day=None)`

P(the high falls in a range). Give `at_least`, `at_most` or both.

```json
// probability(city="CHI", at_least=75)
{"city": "CHI", "day": "2026-10-08", "probability": 0.055, "model_hash": "b200c51ce4ee"}
```

### `decide(city, questions, day=None)`

Several typed questions about one city-day at once, all from the same distribution. Each question
is one of:

| `kind` | Asks | Fields | Answer `value` |
|---|---|---|---|
| `choice` | which of several disjoint ranges wins | `options`: list of ranges | index of the most likely option; `probabilities` per option |
| `noul` | is the high in a range (yes/no) | `set`: a range | `true` if P ≥ 0.5; `probabilities`: [P] |
| `score` | the high itself | `stat`: `mean`, `quantiles` (with `q`) or `interval` (with `coverage`) | a number or a list of whole °F |

```json
// decide(city="NY", questions=[
//   {"kind": "choice", "options": [{"hi": 73}, {"lo": 74, "hi": 77}, {"lo": 78}]},
//   {"kind": "noul", "set": {"lo": 76}},
//   {"kind": "score", "stat": "quantiles", "q": [0.1, 0.5, 0.9]}])
{"city": "NY", "day": "2026-10-08", "event": "KXHIGHNY-26OCT08", "model_hash": "b200c51ce4ee",
 "answers": [
   {"kind": "choice", "value": 1, "probabilities": [0.178, 0.807, 0.015], "confidence": 0.807, "uncovered_mass": 0.0},
   {"kind": "noul", "value": false, "probabilities": [0.288], "confidence": 0.712},
   {"kind": "score", "value": [73.0, 75.0, 77.0]}]}
```

`disagreement` (on `decide`, `probability` and `ladder`) is the KL divergence of isotherm's
ladder from the market's, in nats. Near 0, isotherm is repeating the market; larger values mark the
answers most likely to carry information beyond the price (FINDINGS §46, measured on the research
model). It is a guide to which answers to weigh, not a trading signal: §46 found it does not sort
trading profit.

`confidence` is the probability of the answer given; `uncovered_mass` is the probability that
falls outside every `choice` option (zero when the options cover every temperature).

### `ladder(city, day=None)`

Kalshi's live ladder with three probabilities per bucket: the market's (mid-price, normalised),
the forecast's (EMOS on GFS MOS) and isotherm's. Bucket bounds are half-degrees: a bucket
settles YES when the whole-degree high lies strictly inside `(lo, hi)`; `null` is an open end.

```json
// ladder(city="MIA")
{"city": "MIA", "day": "2026-10-08", "event": "KXHIGHMIA-26OCT08", "gfs_fcst": 91.0,
 "gfs_runtime": "2026-10-07 18:00:00+00:00",
 "buckets": [
   {"ticker": "KXHIGHMIA-26OCT08-T85", "lo": null, "hi": 84.5, "bid": 0.0, "ask": 0.01,
    "p_market": 0.005, "p_forecast": 0.001, "p_model": 0.001},
   {"ticker": "KXHIGHMIA-26OCT08-B85.5", "lo": 84.5, "hi": 86.5, "bid": 0.01, "ask": 0.02,
    "p_market": 0.015, "p_forecast": 0.006, "p_model": 0.004},
   "..."]}
```

## REST

The same functions over HTTP:

```bash
curl -s https://isotherm.onrender.com/health
curl -s https://isotherm.onrender.com/ladder/MIA
curl -s -X POST https://isotherm.onrender.com/decide -H 'content-type: application/json' \
  -d '{"city": "NY", "questions": [{"kind": "noul", "set": {"lo": 76}}]}'
```

## Run it yourself

```bash
uv sync
uv run uvicorn isotherm.app:app        # REST and MCP on :8000
uv run isotherm-mcp                    # MCP over stdio
docker build -t isotherm . && docker run -p 8000:8000 isotherm
```

Every served answer is appended to `ISOTHERM_ANSWER_LOG` (JSON lines, with the distribution it
came from) so live answers can be scored against outcomes later. On the hosted server that log
does not survive a restart.
