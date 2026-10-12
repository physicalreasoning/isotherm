# Contributing to isotherm

isotherm is research done in public. The record of what has been tried, what passed and what
failed is [FINDINGS.md](FINDINGS.md); read the sections near the work you want to do before you
start. Starter projects are listed on the open problems page,
[physicalreasoning.ai/open-problems](https://physicalreasoning.ai/open-problems/), and as issues
labelled `good first issue`, `help wanted`, `research` and `infra`.

## Propose work in an issue first

Open an issue, or comment on an existing one, before writing code. Say:

- the question, in one sentence;
- the data it needs and where that data comes from;
- for research: the comparison and the pass rule you would pre-register (see below);
- for infra: what changes and how it is tested.

A maintainer will reply on scope. This keeps two people from doing the same work and catches
problems with a design (leaks, used-up rows, a weak baseline) before anything is fetched.

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/physicalreasoning/isotherm && cd isotherm
uv sync                 # installs the dev and ml groups (torch, scikit-learn) by default
uv sync --no-group ml   # lighter: the API, MCP server and tests that need no training stack
```

Data comes from unauthenticated public endpoints (Kalshi market data, Iowa Environmental Mesonet)
and is cached under `data/` and `data_cache/`, both ignored by git. A Kalshi API key is optional
and only raises the rate limit (`KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`); the order-book
recorder in `scripts/book/` is the one tool that needs it.

## Tests and lint

CI runs exactly these, and a pull request must pass them:

```bash
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv run pytest -q
```

Tests run offline. A change to anything in `src/isotherm/` that touches point-in-time data
(read times, embargoes, which forecast run was public) needs a regression test; FINDINGS §8 records
a timestamp bug that would have leaked the outcome into every row.

## Research rules

These are how every result in FINDINGS.md was produced. Work that does not follow them can still
be useful, but it is recorded as exploration, not as a finding.

1. **Pre-register before fetching data.** Write the question, the data, the model and the pass
   rule as a FINDINGS section headed "pre-registration", and push it before any price, quote or
   outcome of the test data is fetched or looked at. §49 is a model: written and pushed when only
   event counts had been seen. Anything found by looking is labelled "Exploration" and is never
   adopted on its own; it goes to a sealed test (§28, §29).
2. **Sealed tests are scored once.** The lockboxes (§9, §13) and the forward windows (§25, §29,
   §31, §35, §37, §40, §44, §48) are scored once, under the rule written before them, and are not
   re-scored with a new configuration. Do not edit frozen files in `shadow/` or code whose hash a
   sealed test checks (for example `scripts/bench/evaluate.py`, frozen for §48 and §49). The
   walk-forward rows of the last 12 months before the lockbox have been looked at many times
   (§25); a new adoption claim needs a window nobody has seen.
3. **Publish negative results.** Every pre-registered test is written up whatever it returns.
   Corrections go beside the original text, never in place of it (§41 corrects §39 this way).
4. **Compare with the market priced at its bids.** The mid price counts unbid asks as probability
   and flatters every model on thin books (§41, §47). The baseline is the bid-priced market (empty
   bids floored at 0.5 cents, renormalised). Where the question is whether a model knows more than
   the quote, also report it against the market at its most favourable price inside the quote
   (§47's in-quote comparison).
5. **Date-block confidence intervals.** Report differences paired on identical rows, with 95%
   intervals from a bootstrap that resamples whole dates; rows on one date share weather and
   model runs, so resampling rows understates the interval. The month explains most of the
   variance in results (§45), so prefer a year of data to a short window, and say how many
   months a result spans.
6. **Controls.** A learned model gets a market-label control (the same network trained on labels
   drawn from the market's own distribution, §8), which must score within the stated tolerance of
   the market. A trading result reports fees, one cent of slippage and matched-turnover noise
   (§6, §10).
7. **No data or secrets in git.** Never commit API keys, private keys, `.env` files, raw Kalshi
   snapshots or anything under `data/` or `data_cache/`. Result files (`results/*.json`, `.md`)
   are committed; check they contain no absolute paths from your machine.

## Commits and pull requests

- One change per pull request, linked to its issue.
- Commits are brief: a short subject in the imperative, no trailing period, a body only when the
  why is not obvious. Existing examples: `Sealed forward test for oil (FINDINGS §48)`,
  `API: return disagreement with the market on every answer`.
- No AI or tool trailers in commits or pull requests (no `Co-authored-by` lines for tools, no
  "generated with" lines).
- No em dashes in code, docs or commit messages; use commas, colons or parentheses.
- A research pull request updates FINDINGS.md, the raw result file in `results/`, and the README
  results table if the result belongs there.

Contributions are licensed under Apache-2.0, the license of this repository.
