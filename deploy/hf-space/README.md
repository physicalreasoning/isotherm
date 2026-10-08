---
title: isotherm
emoji: 🌡️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
license: apache-2.0
short_description: Calibrated typed answers for Kalshi daily-high markets
---

# isotherm

Calibrated probabilities for Kalshi's daily high-temperature markets in seven US cities, from the
frozen model in [physicalreasoning/isotherm](https://github.com/physicalreasoning/isotherm)
(FINDINGS §9). Every answer for a city-day is read off one distribution, so answers never
contradict each other. Results: [physicalreasoning.ai/isotherm](https://physicalreasoning.ai/isotherm/).

- `GET /health`, `GET /ladder/{city}`, `POST /decide` (typed questions), docs at `/docs`
- MCP (streamable HTTP) at `/mcp`: tools `cities`, `ladder`, `probability`, `decide`

Cities: NY, CHI, MIA, AUS, LAX, DEN, PHIL. Probabilities, not advice.

This Space is built from the repository by `deploy/hf_space.sh`; edit there, not here.
