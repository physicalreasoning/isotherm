# Polymarket daily-high markets as extra data (2026-10-07)

Question: can Polymarket's "Highest temperature in <city> on <date>?" markets add ladders to
isotherm's training set (FINDINGS §21 says the transformer wants more data)?

Survey through the public Gamma API (events by each city's `<city>-daily-weather` series) and the
CLOB price history. Derived rows are kept locally in `data/polymarket/` (not committed).

## What exists

| City | Polymarket station | Kalshi station | From | Settled days | Winning bucket contains the CLI high |
|---|---|---|---|---|---|
| NYC | KLGA | KNYC | 2025-01-22 | 616 | 50% |
| CHI | KORD | KMDW | 2025-12-04 | 256 | 60% |
| DAL | KDAL | KDFW | 2025-12-04 | 303 | 63% |
| DEN | KBKF | KDEN | 2025-12-04 | 194 | 61% |
| MIA | KMIA | KMIA | 2025-12-04 | 256 | 63% |
| ATL | KATL | KATL | 2025-12-06 | 300 | 70% |
| SEA | KSEA | KSEA | 2025-12-06 | 299 | 71% |
| LAX | KLAX | KLAX | 2026-03-24 | 195 | 59% |
| AUS | KAUS | KAUS | 2026-03-24 | 192 | 66% |
| SFO | KSFO | KSFO | 2026-03-24 | 193 | 59% |
| HOU | KHOU | none | 2026-03-24 | 193 | n/a |

2,999 settled US city-days through 2026-10-06. No markets for PHIL, DC, LV, NOLA, OKC, SATX;
Boston and Minneapolis series are empty; Phoenix has two days.

- **Label.** The highest *hourly* reading at the airport, whole °F: Weather Underground's daily
  history until 2026-08-22, NWS timeseries hourly data since. Kalshi settles on the NWS Daily
  Climate Report (CLI), which catches the true peak between hourly readings and uses local
  standard time for the day.
- **Ladder.** 2°F buckets with open tails; 7 buckets until spring 2026, 11 since.
- **Prices.** Retrievable for closed markets with explicit `startTs`/`endTs` (1-minute or hourly
  fidelity) from about an hour after listing, 1 to 2 days before the target day, so a 16:00
  day-before read exists for every event.
- **Size.** Median volume $41k to $91k per city-day.

## Verdict: not usable as Kalshi ladders

Even at the same station, the CLI high lands in Polymarket's winning bucket only 59 to 71% of the
time. When it misses, the CLI is almost always higher: by 1°F on about 30% of days, 2°F or more on
about 4%. Four cities settle at a different airport altogether. The labels are a related
variable, roughly 1°F lower, not the same one.

Using them would need a second target ("max hourly reading at that airport", rebuildable from
METAR observations) and a model that learns both. That is a multi-task project with a different
crowd and a shorter history (most cities start December 2025 or March 2026), so it does not answer
the transformer's need for more in-distribution ladders. Not pursued.
