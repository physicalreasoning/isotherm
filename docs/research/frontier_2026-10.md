# Frontier scan for isotherm (2026-10-05)

Literature and data review: what recent work (mostly 2023-2026) could realistically improve a
calibrated, market-anchored model of Kalshi daily temperature ladders. It is web research only;
no code was changed. I verified every citation below against arXiv's API, Crossref, or the
publisher or agency page on 2026-10-05. Where a claim comes from a vendor page or a non-peer-
reviewed source, the entry says so.

Before writing I read `docs/MODEL_CARD.md`, `docs/G3.md` and FINDINGS §17-20 so the advice does
not repeat work already done. Already done: multi-station synthetic pretraining (G3, failed its
gate); the transformer at two sizes (failed, but scale helped at 16:00); pooled read times, lows
and the new cities as extra rows (pre-registered in §20); the maker fill model; ladder Kelly;
point-in-time MOS availability.

## TL;DR

1. **The most important new facts are operational, not academic.** NBM v5.0 went live on
   2026-04-21. It now **ingests ECMWF AIFS and NOAA AIGFS** for temperature, takes higher-
   resolution ECMWF and GEFS inputs, and reports its daily max as the mean of a quantile-mapped
   distribution. Settlement moved to The Weather Company on 2026-08-14. NAM, HREF and NAM MOS
   are retired, and RRFS becomes operational on 2026-10-06. NBM swaps its NAM/HiresW inputs for
   RRFS/REFS on 2026-11-03. The market prices NBM, so every NBM upgrade shrinks the share of
   information that only GFS MOS carries. This may be part of the lockbox's month-on-month PnL
   decay. Check it before anything else.
2. **Crosier (2026) already did what an outsider would do with public forecasts.** On the same
   seven cities, the Kalshi market beats the NBM by about 10% RMSE. It also beats an out-of-sample,
   daily-refit optimal combination of six public products (NBM, NDFD, LAMP, GFS MOS, HRRR, ECMWF)
   by 3-4%. Adding more free forecasts is therefore a game of thousandths of a nat, not
   hundredths.
3. **Global AI weather models (GraphCast, GenCast, Aurora, FourCastNet 3, AIFS, AIGFS) are mostly
   hype for this project.** The two most useful of them are now inside NBM, which the market
   already prices. Their open archives are short or have changed version mid-sample, and running
   them yourself costs a lot for gridded 6-hourly output that is worse at stations than MOS
   before post-processing. One possible exception is the **WeatherNext 3 station head**: a
   station-level 2 m temperature distribution, claimed to be 30-40% better in CRPS at short
   lead times. It can only be tested honestly on data from July 2026 onward (leakage note below),
   so it is a candidate to start archiving now, not one to backtest.
4. **Cheap wins come from inputs you already download.** The NBM text bulletins (NBS) carry
   `XND`, the NBM's own standard deviation of the max/min, and `TSD`. Both sit in your IEM cache
   unused, because the EMOS spread is purely seasonal. A heteroscedastic EMOS (Gneiting et al.,
   2005) is a one-day experiment. LAMP (IEM archive since 2020-07) is the obvious extra expert
   for the 08/12/14 reads.
5. **Small-data ML (TabPFN, in-context learning, conformal) is unlikely to beat what you have.**
   FINDINGS §17-19 says the edge is limited by information more than capacity. TabPFN-2.5 and 3
   are under non-commercial licences, and conformal methods target coverage, not log score.

**Minimum detectable effect.** In your own gate tables, the 95% date-block CI half-width on a
paired 12-month difference at one read is about 0.003 nats (§17, §19). An improvement must
therefore be around +0.004 to +0.006 nats per ladder, at one read, to pass a gate. Most
candidates below are expected to land at or under that level. I say so in each entry.

---

## 0. Read first: the two papers closest to isotherm

### Crosier (2026), *Prediction Markets Beat the Weather Forecast on Tomorrow's High Temperature*
[arXiv:2609.23969](https://arxiv.org/abs/2609.23969) (submitted 2026-09-21)

- **Idea:** extract a market-implied point forecast from Kalshi ladders (bucket mids, uniform mass
  within buckets, geometric tails) for seven cities (NY, CHI, MIA, AUS, PHL, DEN, LA, through
  2026-08-12). Race it hour by hour against NDFD, NBM, LAMP, GFS MOS, HRRR and ECMWF.
- **Findings:**
  - The market beats NBM by 9.8% RMSE at its first trading hour (2.44 vs 2.70°F) and by 11.4% at
    NBM's final morning bulletin.
  - It beats an out-of-sample, daily-refit optimal weighting of all six products by 3-4%.
  - Between postings, NBM moves about four times further toward the market than the market moves
    toward NBM.
  - The edge is largest in high-error seasons (10-16% November-June in colder cities) and small in
    Miami.
  - Three of the six products forecast a *daytime* max rather than the calendar-day max and
    needed correction.
- **Why it applies:**
  - It is independent confirmation of your G0 premise from the other side: the market is sharper
    than any public forecast or blend.
  - It also confirms that the residual information in public forecasts is small. Your +0.01 to
    +0.02 nats is consistent with it.
  - It gives a ready list of products, with archive sources: NOMADS/AWS for NBM and NDFD, IEM for
    GFS MOS and LAMP, plus HRRR and ECMWF archives.
  - The seasonal heterogeneity suggests the edge, and so Kelly size, should be conditioned on
    season and forecast-error regime.
- **Expected gain:** none by itself; it is context. It is a single-author preprint, not peer
  reviewed. It uses RMSE of a point forecast, not log score, and its tail construction (τ=0.55)
  is ad hoc.
- **Risk:** a public paper showing that Kalshi weather markets out-forecast NWS may attract more
  quantitative traders to these series. That is one more reason to expect further edge decay.

### Bürgi, Deng & Whelan (2026), *Makers and Takers: The Economics of the Kalshi Prediction Market*
[PDF (UCD / karlwhelan.com)](https://www.karlwhelan.com/Papers/Kalshi.pdf); also
[CESifo WP 12122](https://www.ifo.de/en/cesifo/publications/2026/working-paper/makers-and-takers-economics-kalshi-prediction-market),
[VoxEU summary](https://cepr.org/voxeu/columns/economics-kalshi-prediction-market)

- **Idea:** transaction-level data on 300k+ Kalshi contracts from 2021 to April 2025. Prices are
  informative and improve toward close, but there is a clear favourite-longshot bias. Contracts
  under 10c lose over 60% of stake; contracts over 50c earn small positive returns. Makers do
  better than takers. The bias is rejected as zero in every category including "Climate &
  Weather", and it is weaker in 2025. Kalshi began charging makers fees after April 2025.
- **Why it applies:**
  - It justifies the tempered market term (your fitted market exponent of 1.07 to 1.18 says the
    market is, if anything, slightly *under*confident at 16:00 the day before).
  - It argues that maker execution matters. You already model maker fills conservatively
    (EVALS.md), so the open question is only whether the fee schedule on the weather series has
    changed since your `fee_multiplier` assumption.
- **Expected gain:** 0 for the model. Possibly material for net PnL if fee or maker assumptions
  are stale.
- **Cost:** 0.5 day to re-check the current Kalshi fee schedule for the KXHIGH* series.

---

## (a) ML weather forecasting and free signals

Format of each entry: citation, idea, why it applies, expected gain, cost, data and point-in-time
status, risk.

### a1. ECMWF IFS ENS via ECMWF Open Data
[ECMWF open data](https://www.ecmwf.int/en/forecasts/datasets/open-data);
[AWS mirror `ecmwf-forecasts`](https://registry.opendata.aws/ecmwf-forecasts/);
archive dates from [Herbie docs](https://herbie.readthedocs.io/en/stable/gallery/ecmwf_models/ecmwf.html);
Zarr version at [dynamical.org / source.coop](https://source.coop/dynamical)

- **Idea:** 51-member ENS at 0.25° under CC-BY-4.0, including `mx2t6`/`mn2t6` (6-hour max/min 2 m
  temperature). Build per-station ENS quantiles of the calendar-day max, then fit an EMOS-ENS
  expert, or use the ENS spread as a scale feature.
- **Why it applies:** a genuinely different model family from GFS, with its own probabilistic
  spread. Crosier included ECMWF.
- **Expected gain:** small. NBM already ingests ECMWF ENS (at 0.2° from v5), and traders watch the
  "Euro" closely. I would guess +0.000 to +0.004 nats, mostly through the spread rather than the
  mean.
- **Cost:** 3-5 days (GRIB2 extraction at 7 points, `mx2t6` windows aligned to the settlement day
  in local standard time, publication-time stamps).
- **Data:**
  - Free. The ECMWF server keeps only about 12 runs (2-3 days).
  - The AWS mirror runs from 2023-01-18. It was 0.4° until 2024-02-01 and 0.25° after, so there is
    a resolution break inside your sample.
  - dynamical.org's Zarr starts 2024-04-01, 00 UTC only.
  - **Point-in-time:** stamp by dissemination time, not init time. The 00 UTC ENS finishes
    dissemination hours after 00 UTC, and the open-data release schedule has changed over the
    period.
- **Risk:** the resolution break; only about 2.7 years of history; a small marginal effect.

### a2. ECMWF AIFS Single and AIFS ENS
Lang et al. (2024), *AIFS: ECMWF's data-driven forecasting system*,
[arXiv:2406.01465](https://arxiv.org/abs/2406.01465). Lang et al. (2024), *AIFS-CRPS*,
[arXiv:2412.15832](https://arxiv.org/abs/2412.15832).
[ECMWF AIFS dataset page](https://www.ecmwf.int/en/forecasts/dataset/aifs-machine-learning-data).

- **Idea:** ML global model; the deterministic version has been operational since 2025-02-25 and
  the CRPS-trained ensemble since 2025-07-01. Both upgraded to v2 on 2026-05-12. CC-BY-4.0, 6-hourly,
  0.25°.
- **Why it applies:** in principle a skilful extra signal.
- **Expected gain:** approximately 0 as a separate expert. NBM v5.0 already ingests AIFS
  ("ECAIFS") for temperature (SCN 26-24, below), and the market prices NBM. The archive is too
  short and has changed version too often to learn a pool weight honestly: AIFS ENS exists from
  July 2025, with a version change in May 2026.
- **Cost:** 2-3 days once a1 exists, because it is the same pipeline.
- **Data:** free. Open-data archive on AWS from about 2024-02 (Single) and 2025-07 (ENS).
- **Risk:** version breaks; 6-hourly steps miss the afternoon peak, so a Tmax proxy from 6-hourly
  `2t` is biased cold. Use `mx2t6` where it exists.

### a3. NOAA AIGFS / AIGEFS / HGEFS and the GraphCastGFS/EAGLE archive
[NOAA announcement via WMO](https://wmo.int/media/news/noaa-deploys-new-generation-of-ai-driven-global-weather-models);
[NCO AIGEFS products](https://www.nco.ncep.noaa.gov/pmb/products/aigefs/);
[AWS `noaa-nws-graphcastgfs-pds`](https://registry.opendata.aws/noaa-nws-graphcastgfs-pds)

- **Idea:** operational AI global models from 2025-12-17 (AIGFS deterministic, AIGEFS with 31
  members, HGEFS hybrid grand ensemble). Experimental GraphCastGFS forecasts exist from 2024-02-05
  and EAGLE from 2024-04-24.
- **Why it applies:** a free US-run AI ensemble.
- **Expected gain:** approximately 0 as an expert. AIGFS is already an NBM v5 input, the
  operational archive is under 10 months old, and the experimental archive changed model mid-way.
- **Cost:** 2-4 days.
- **Data:** free (NOMADS, AWS). Point-in-time is fine for real-time pulls; the experimental
  bucket's version history makes a backtest messy.
- **Risk:** low value for the effort. Forward-archive at most.

### a4. Self-run global AI models: GraphCast, GenCast, Aurora, FourCastNet 3
- Lam et al. (2023), *Learning skillful medium-range global weather forecasting*, Science,
  [doi:10.1126/science.adi2336](https://doi.org/10.1126/science.adi2336) ([arXiv:2212.12794](https://arxiv.org/abs/2212.12794))
- Price et al. (2024), *Probabilistic weather forecasting with machine learning* (GenCast), Nature,
  [doi:10.1038/s41586-024-08252-9](https://doi.org/10.1038/s41586-024-08252-9) ([arXiv:2312.15796](https://arxiv.org/abs/2312.15796))
- Bodnar et al. (2025), *A foundation model for the Earth system* (Aurora), Nature,
  [doi:10.1038/s41586-025-09005-y](https://doi.org/10.1038/s41586-025-09005-y) ([arXiv:2405.13063](https://arxiv.org/abs/2405.13063))
- Bonev et al. (2025), *FourCastNet 3*, [arXiv:2507.12144](https://arxiv.org/abs/2507.12144)
- NVIDIA Earth-2: StormCast, Pathak et al. (2024), [arXiv:2408.10958](https://arxiv.org/abs/2408.10958)

- **Idea:** run the open checkpoints yourself (for example via Earth2Studio) from operational
  initial conditions, to produce an independent ensemble.
- **Why it applies:** weakly. These are 0.25° gridded models with 6-hourly output, evaluated
  against ERA5. Station 2 m temperature (and so daily max) needs post-processing to beat MOS.
  Trotta et al. (2025, below) show post-processed AIFS is about as good as post-processed NWP,
  and that blending helps a little.
- **Expected gain:** ≤ +0.003 nats, and probably 0 after the market and NBM.
- **Cost:** 2-4 weeks including GPU time for about 1,000 initialisations × members; GenCast is
  expensive.
- **Data and leakage:**
  - You must initialise from analyses that existed at the time (GDAS or HRES), **not ERA5**. ERA5
    is a reanalysis produced days later and is better than the real-time analysis, so ERA5
    initial conditions leak future observations.
  - Check that each checkpoint's training cutoff precedes your test period. The public GraphCast
    and GenCast weights were trained to the late 2010s, which is fine for 2023-2026.
- **Risk:** high effort for gains below the MDE. **Verdict: hype for this project.**

### a5. Google WeatherNext 2 and WeatherNext 3 (station head)
- Alet et al. (2025), *Skillful joint probabilistic weather forecasting from marginals* (FGN,
  the basis of WeatherNext 2), [arXiv:2506.10772](https://arxiv.org/abs/2506.10772)
- Rasp et al. (2026), *WeatherNext 3: Increasing resolution and performance of global weather
  models with raw observations*, [arXiv:2609.03582](https://arxiv.org/abs/2609.03582)
- Access and licence: [WeatherNext data access](https://developers.google.com/weathernext/guides/access-forecast);
  [EE catalog, WN2](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_2_0_0);
  [EE catalog, WN3 0.05°](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p05deg)

- **Idea:**
  - WN3 runs **hourly** and assimilates raw geostationary satellite frames on top of analyses. It
    has a **station head** that predicts the 2 m temperature distribution at arbitrary points.
  - The paper reports up to 30% better short-lead CRPS than WN2 and 40% better than ECMWF ENS,
    measured on held-out METAR and mesonet stations.
  - The EE dataset publishes station-head quantiles (mean, p10-p90).
- **Why it applies:** this is the first free-ish AI product that is station-level, probabilistic,
  hourly, and not an NBM input. It is the one AI signal that could carry information the market
  lacks. Caveat: WN3 also powers Google Search and Maps weather, which many retail Kalshi traders
  look at.
- **Expected gain:** unknown. Plausibly the largest of the AI options, and plausibly 0.
- **Cost:** 1-2 days to set up a forward archiver (access request: 5-7 business days); 2-3 days to
  add as an expert later.
- **Data and LEAKAGE:**
  - The WN3 archive begins 2026-01-01.
  - The paper states the **production model was trained on data through 2026-06-30**. Any WN3
    forecast valid before July 2026 is therefore in-sample for the model that produced it. **Only
    ladders from about 2026-07-01 are an honest test.**
  - WN2 history (2022 onward) is undocumented on whether it is archived real-time output or a
    retrospective hindcast, or which initial conditions it used. Treat it as **unsafe for
    backtesting** until Google documents it.
  - Real-time data (under 1 hour old for WN3, under 48 hours for WN2) falls under the "GDM
    Real-Time Weather Forecasting Experimental Data Terms of Use", not CC-BY. Check commercial use
    before trading on it.
- **Risk:**
  - Licence.
  - The station head predicts instantaneous hourly temperature; the daily max needs the hourly
    path, and quantiles do not compose into a max distribution without a joint model.
  - Only about 3 months of clean data today.

### a6. LAMP (Localized Aviation MOS Program)
[LAMP overview (NWS/MDL)](https://www.weather.gov/media/mdl/pub/LAMP_overview_paper_AMS2005_final.pdf);
[IEM MOS archive](https://mesonet.agron.iastate.edu/mos/) (GFS LAMP "LAV" from 2020-07-12)

- **Idea:** hourly-updated, observation-conditioned station MOS for 1-25 h ahead, at about 2,300
  stations.
- **Why it applies:** directly targets your intraday reads (08/12/14). It folds the latest METAR
  into the remaining-day temperature path, which is what "EMOS-NBM conditioned on today's
  observed max" approximates by hand. Crosier used it.
- **Expected gain:** +0.002 to +0.006 nats at same-day reads; about 0 at 16:00 the day before.
  Guess: the market likely watches the current temperature closely, so LAMP's value is in the
  *remaining* rise rather than the level.
- **Cost:** 2-3 days (the IEM parser already exists for MAV/NBS).
- **Data:** free; IEM archive since 2020-07. Crosier notes IEM holds only four LAMP cycles a day,
  so check which cycles precede each read. Point-in-time: LAMP posts roughly 20-30 minutes after
  the hour; stamp by product issuance.
- **Risk:** low. The main risk is redundancy with your obs-conditioned NBM expert.

### a7. NBM v5.0 and NBM's own uncertainty fields (`XND`, `TSD`)
[SCN 26-24, NBM v5.0, effective 2026-04-21](https://www.weather.gov/media/notification/pdf_2026/scn26-24NBM_V5(1).0_aaa.pdf);
[NBM v4.2 text bulletin card (element definitions)](https://vlab.noaa.gov/web/mdl/nbm-textcard-v4.2);
[NBM AWS archive](https://vlab.noaa.gov/web/mdl/nbm-download)

- **Idea:**
  - NBS bulletins carry `XND` (standard deviation of max/min temperature, °F) and `TSD`
    (standard deviation of hourly temperature).
  - Your IEM cache has both columns, but `emos.py` uses a seasonal-only σ.
  - In v5.0, daily max/min are "the mean of the QM distribution", with the standard deviation
    drawn from the same QM solution, so `XND` should now be a better-calibrated spread signal.
- **Why it applies:** this is textbook heteroscedastic EMOS (Gneiting et al., 2005,
  [doi:10.1175/MWR2904.1](https://doi.org/10.1175/MWR2904.1)): put a predicted spread into the
  log-σ link.
- **Expected gain:** +0.001 to +0.005 nats. The market surely already knows "uncertain days are
  uncertain", but your NBM expert currently does not, which wastes pool weight.
- **Cost:** 1 day.
- **Data:** free and already cached. **Point-in-time and regime:** `XND` semantics changed on
  2026-04-21. Fit separate σ coefficients pre/post v5, or use v5-only data with shrinkage.
- **Risk:** low.

### a8. HRRR and RRFS
[RRFS/REFS implementation, SCN 26-48 notes](https://www.weather.gov/media/notification/pdf_2026/scn26-048_RRFS_and_REFS_Implementation.aab.pdf);
[SCN 26-47, NAM/SREF/HREF/HiresW/NAM MOS termination 2026-10-06](https://www.weather.gov/media/notification/pdf_2026/scn26-47_Retirement_of_NAM_SREF_HREF_HiresW_NAM_MOS.aaa.pdf);
[SCN 26-89, downstream changes incl. NBM inputs, 2026-11-03](https://www.weather.gov/media/notification/pdf_2026/scn26-89_RRFS_Downstream.pdf)

- **Idea:** 3 km hourly convection-allowing guidance. HRRR has not yet been retired; RRFS goes
  operational on 2026-10-06.
- **Why it applies:** same-day reads. Weather traders watch HRRR heavily (Crosier included it).
- **Expected gain:** about 0 to +0.003 nats; raw HRRR 2 m temperature has known diurnal biases,
  and the market already uses it.
- **Cost:** 3-4 days (Herbie or dynamical.org Zarr makes extraction easy).
- **Data:** free, with a long AWS archive. RRFS has no history beyond the parallel feed from
  2026-08-11.
- **Risk:** RRFS replaces HRRR eventually, so any learned HRRR weight has a limited life.

### a9. Convenience archives (and a leakage trap)
- [dynamical.org](https://source.coop/dynamical): cloud-optimised Zarr for GFS, GEFS, HRRR, IFS ENS
  and AIFS. A real time-saver for a1, a2 and a8.
- [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api):
  **LEAKS.** It is built by stitching "each run's first few hours" into one series, so it is
  close to an analysis, not a forecast available at your read time. Do not use it for features.
- [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) gives fixed
  24 h, 48 h... offsets per *valid hour*. A daily max built from it mixes runs, ignores
  publication latency, and uses a grid cell, not the station. Usable for exploration; not for a
  sealed test. Most models are archived only from January 2024 (GFS from 2021).

### a10. Station-level post-processing with neural networks (for building better weather experts)
- Rasp & Lerch (2018), *Neural networks for postprocessing ensemble weather forecasts*, MWR,
  [doi:10.1175/MWR-D-18-0187.1](https://doi.org/10.1175/MWR-D-18-0187.1) ([arXiv:1805.09091](https://arxiv.org/abs/1805.09091)).
  Distributional regression network (DRN) with **station embeddings**: one model for all stations
  beats per-station EMOS.
- Schulz & Lerch (2022), *Machine learning methods for postprocessing ensemble forecasts of wind
  gusts: a systematic comparison*, MWR, [doi:10.1175/MWR-D-21-0150.1](https://doi.org/10.1175/MWR-D-21-0150.1)
  ([arXiv:2106.09512](https://arxiv.org/abs/2106.09512)). Compares DRN, Bernstein quantile network
  (BQN) and histogram estimation network (HEN, a softmax over bins). HEN is the closest analogue
  to isotherm's per-bucket softmax; the parametric and quantile heads were generally at least as
  good with less data.
- Bremnes (2020), *Ensemble postprocessing using quantile function regression based on neural
  networks and Bernstein polynomials*, MWR, [doi:10.1175/MWR-D-19-0227.1](https://doi.org/10.1175/MWR-D-19-0227.1).
- Landry, Charantonis & Monteleoni (2024), *Leveraging deterministic weather forecasts for in-situ
  probabilistic temperature predictions via deep learning*, MWR,
  [doi:10.1175/MWR-D-23-0273.1](https://doi.org/10.1175/MWR-D-23-0273.1) ([arXiv:2406.02141](https://arxiv.org/abs/2406.02141)).
  METAR stations in the US and Canada; **one model across lead times beats separate models**.
  This is the same idea as your §20 pooled-read-time arm.
- Höhlein et al. (2024), permutation-invariant NNs for ensemble post-processing, AIES,
  [doi:10.1175/AIES-D-23-0070.1](https://doi.org/10.1175/AIES-D-23-0070.1) ([arXiv:2309.04452](https://arxiv.org/abs/2309.04452)).
- Van Poecke et al. (2024), *Self-attentive Transformer for fast and accurate postprocessing of
  temperature and wind speed forecasts*, AIES, [doi:10.1175/AIES-D-24-0127.1](https://doi.org/10.1175/AIES-D-24-0127.1)
  ([arXiv:2412.13957](https://arxiv.org/abs/2412.13957)).
- Feik, Lerch & Stühmer (2024), GNNs for post-processing, [arXiv:2407.11050](https://arxiv.org/abs/2407.11050).
  Not useful with 7 to 19 widely separated stations.
- Trotta et al. (2025), *Statistical post-processing yields accurate probabilistic forecasts from
  AI weather models*, AIES, [doi:10.1175/AIES-D-25-0037.1](https://doi.org/10.1175/AIES-D-25-0037.1)
  ([arXiv:2504.12672](https://arxiv.org/abs/2504.12672)). AIFS post-processed with IMPROVER is about
  as good as post-processed NWP, and blending helps.
- Baran & Mihalina (2026), sharpness penalty for NN post-processing,
  [arXiv:2606.08587](https://arxiv.org/abs/2606.08587). Narrower intervals with no loss of CRPS.
  Not relevant under log score, which already rewards sharpness.

**How this applies:** replace the per-city, single-predictor Gaussian EMOS experts with **one
pooled DRN or BQN weather expert**. Use station embeddings; predictors are GFS MOS `n_x`, NBM
`txn`, `xnd`, LAMP, their disagreement, day of year, read time, and the obs-so-far. Train it on
the 55-station corpus you built for G3 plus the Kalshi cities, with **real outcomes only and no
simulated market**.

This differs from G3. G3 pretrained the *combiner* on simulated markets, and a simulator cannot
teach market behaviour. This proposal improves the *weather expert*, where more stations and years
are genuinely the same task.

- **Expected gain:** +0.002 to +0.006 nats, partly overlapping a6 and a7.
- **Cost:** 4-6 days.
- **Leakage:** same-day weather at neighbouring stations is correlated, so keep G3's rule. Train
  only on days at or before each fold's last training day, across all stations.

### a11. Regime changes inside or right after your sample (not papers, but load-bearing)
| Date | Change | Why it matters |
|---|---|---|
| 2025-02-25 / 2025-07-01 | AIFS Single / AIFS ENS operational | ML forecasts reach traders and, later, NBM |
| 2025-12-17 | AIGFS, AIGEFS, HGEFS operational | same |
| **2026-04-21** | **NBM v5.0**: ingests AIFS and AIGFS; higher-resolution ECMWF and GEFS; max/min = mean of QM distribution | the priced public forecast got better and changed its error statistics, inside your last fold and before the lockbox |
| 2026-05-12 | AIFS v2 (Single and ENS) | version break |
| **2026-08-14** | Kalshi settlement moves from NWS CLI to The Weather Company | target definition (your MODEL_CARD) |
| 2026-10-06 | RRFS operational; NAM, NAM MOS, HREF, SREF, HiresW retired | intraday guidance mix |
| **2026-11-03** | NBM swaps NAM/HiresW inputs for RRFS/REFS | another NBM error-statistics shift |

---

## (b) Probabilistic combination and recalibration with small data

### b1. Benter (1995/2008), *Computer based horse race handicapping and wagering systems: a report*
In *Efficiency of Racetrack Betting Markets*, [doi:10.1142/9789812819192_0019](https://doi.org/10.1142/9789812819192_0019).

- **Idea:** a multinomial logit combining a fundamental model with the public's implied
  probabilities. Algebraically this is your log opinion pool over mutually exclusive outcomes.
- **Why it applies:** it confirms the architecture. Benter also stresses that the combination
  weights, not the fundamental model, must be refit as the public gets smarter. That is your
  decay story.
- **Expected gain:** 0 (it is validation). **Cost:** reading only.

### b2. Linear and beta-transformed pools, stacking, BMA
- Ranjan & Gneiting (2010), *Combining probability forecasts*, JRSS-B,
  [doi:10.1111/j.1467-9868.2009.00726.x](https://doi.org/10.1111/j.1467-9868.2009.00726.x)
- Yao, Vehtari, Simpson & Gelman (2018), *Using stacking to average Bayesian predictive
  distributions*, Bayesian Analysis, [doi:10.1214/17-BA1091](https://doi.org/10.1214/17-BA1091)
- Raftery et al. (2005), *Using Bayesian model averaging to calibrate forecast ensembles*, MWR,
  [doi:10.1175/MWR2906.1](https://doi.org/10.1175/MWR2906.1)
- Wang, Hyndman, Li & Kang (2023), *Forecast combinations: an over 50-year review*, IJF,
  [arXiv:2205.04216](https://arxiv.org/abs/2205.04216)

- **Idea:**
  - The linear pool needs a calibrating transform (the beta-transformed linear pool).
  - Stacking on log score beats BMA when no candidate model is true, which is your case.
  - The "forecast combination puzzle" says simple, heavily regularised weights usually win
    out of sample.
- **Why it applies:** your learned log pool is already log-score stacking with tempering, which is
  the right choice. A beta-transformed linear pool is a cheap ablation, but log pools are sharper
  and suit a market that is already well calibrated.
- **Expected gain:** about 0 for switching pool type. A small gain is possible from **hierarchical
  shrinkage of pool weights across cities and reads** toward the pooled value. That is effectively
  §20's pooling, applied to the pool layer.
- **Cost:** 1-2 days. **Risk:** low.

### b3. Online aggregation with time-varying weights
Berrisch & Ziel (2023), *CRPS learning*, J. Econometrics,
[doi:10.1016/j.jeconom.2021.11.008](https://doi.org/10.1016/j.jeconom.2021.11.008)
([arXiv:2102.00968](https://arxiv.org/abs/2102.00968))

- **Idea:** online expert aggregation (Bernstein online aggregation) with forgetting and weights
  smoothed across quantiles, with regret guarantees.
- **Why it applies:** your edge is non-stationary (decaying, with regime breaks). A principled
  online learner for the *pool weights* is a cleaner answer than a fixed 365-day half-life plus
  monthly refits. It also gives a natural monitoring signal: the GFS weight trending to zero means
  the information has been priced in. Use the log-score analogue, since the paper is about CRPS.
- **Expected gain:** +0.000 to +0.003 nats; the benefit is mostly robustness after breaks such as
  NBM v5. **Cost:** 2-3 days.
- **Risk:** online weights can chase noise. Keep the half-life comparison as the control.

### b4. Isotonic distributional regression and EasyUQ
- Henzi, Ziegel & Gneiting (2021), *Isotonic distributional regression*, JRSS-B,
  [doi:10.1111/rssb.12450](https://doi.org/10.1111/rssb.12450) ([arXiv:1909.03725](https://arxiv.org/abs/1909.03725))
- Walz et al. (2024), *EasyUQ*, [arXiv:2212.08376](https://arxiv.org/abs/2212.08376)

- **Idea:** a non-parametric, tuning-free predictive distribution under a monotonicity
  constraint. Example: a higher MOS max implies a stochastically larger observed max.
- **Why it applies:** a robust, assumption-light weather expert. It is a useful check that your
  Gaussian EMOS is not mis-shaped in the tails (skew in Denver or Miami lows).
- **Expected gain:** about 0 to +0.002. Interval probabilities from IDR are step functions and
  need smoothing for log score on 2°F buckets.
- **Cost:** 1 day (the `isodisreg` package). **Risk:** zero-probability buckets if not smoothed.

### b5. Tabular foundation models and in-context learning
- Hollmann et al. (2025), *Accurate predictions on small data with a tabular foundation model*
  (TabPFN v2), Nature, [doi:10.1038/s41586-024-08328-6](https://doi.org/10.1038/s41586-024-08328-6)
- Grinsztajn et al. (2025), *TabPFN-2.5*, [arXiv:2511.08667](https://arxiv.org/abs/2511.08667);
  (2026) *TabPFN-3 technical report*, [arXiv:2605.13986](https://arxiv.org/abs/2605.13986)
- Qu et al. (2025), *TabICL*, [arXiv:2502.05564](https://arxiv.org/abs/2502.05564)

- **Idea:** a transformer pretrained on synthetic tabular tasks does Bayesian-style in-context
  prediction. Regression outputs a binned "bar distribution", so it can be scored by log score.
- **Why it applies:** in principle, this is a small-data regime. In practice the task is
  "combine a very sharp market with weak extra signals under non-stationarity". TabPFN's prior
  assumes i.i.d. rows and knows nothing about market anchoring or ladder normalisation.
  FINDINGS §17-19 already says capacity is not the binding constraint.
- **Expected gain:** about 0. At best a quick sanity baseline for the weather expert (a10), not
  for the combiner.
- **Cost:** 1-2 days.
- **Licence:** TabPFN v2 allows commercial use with attribution. **TabPFN-2.5, 2.6 and 3 weights
  are non-commercial** and cannot be used for a trading model.
- **Verdict:** hype for this use.

### b6. Conformal prediction
Angelopoulos & Bates, *A Gentle Introduction to Conformal Prediction*,
[arXiv:2107.07511](https://arxiv.org/abs/2107.07511)

- **Idea:** distribution-free coverage guarantees.
- **Why it (mostly) does not apply:** you need full, log-score-optimal bucket probabilities, not
  set coverage, and your model is already calibrated (debiased ECE 0.004-0.007). Under
  exchangeability violations (decay, regime breaks), adaptive conformal tracks coverage, not
  sharpness.
- **Expected gain:** 0. **Verdict:** skip.

### b7. A market-anchored, low-dimensional correction head (my suggestion, grounded in a10)
Schulz & Lerch's comparison suggests per-bin (HEN-like) heads waste data relative to parametric
or quantile heads. Instead of a per-bucket MLP correction, predict 2-3 numbers per ladder (shift,
log-scale and maybe a skew of the market-implied CDF) from context features, then re-integrate
over the buckets. It is a strong inductive bias: most of what forecasts can tell the market is
"move the distribution by x and widen or narrow it".

- **Expected gain:** +0.000 to +0.004.
- **Cost:** 2 days.
- **Risk:** it loses per-bucket effects such as tail favourite-longshot bias. Keep a small
  per-bucket term for the tails.

---

## (c) Prediction-market ML and quant work

### c1. Le (2026), *Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets*
[arXiv:2602.19520](https://arxiv.org/abs/2602.19520)

- **Idea:** 292M trades on Kalshi and Polymarket. Calibration decomposes into horizon, domain,
  domain-by-horizon and trade-size effects. **Weather markets are overconfident at short horizons
  (calibration slopes 0.69-0.97 within 48 h, lowest at 0-1 h) and underconfident beyond a week.**
- **Why it applies:**
  - It suggests the market exponent should vary by read time; check that each read's fitted
    tempering matches.
  - Caveat: this is a per-contract binary analysis that includes illiquid last-hour trades,
    whereas your 16:00 fit says the ladder is slightly *under*confident (exponent 1.07-1.18).
    The two can coexist, because per-contract slopes are not ladder-normalised.
- **Expected gain:** about 0 if you already fit tempering per read (you do). **Cost:** 0.5 day to
  tabulate the fitted market exponent by read and by hours-to-close.

### c2. Snowberg & Wolfers (2010), *Explaining the Favorite-Long Shot Bias: Is it Risk-Love or Misperceptions?*
JPE, [doi:10.1086/655844](https://doi.org/10.1086/655844)

- **Idea:** the favourite-longshot bias is driven by probability misperception, not risk-love.
- **Why it applies:** background for why tail buckets are overpriced (section 0, Bürgi et al.). Your
  per-bucket MLP with price features should already capture it.
- **Gain:** 0. **Cost:** reading only.

### c3. Kelly sizing under estimation error
- Baker & McHale (2013), *Optimal betting under parameter uncertainty: improving the Kelly
  criterion*, Decision Analysis, [doi:10.1287/deca.2013.0271](https://doi.org/10.1287/deca.2013.0271)
- Metel (2017), *Kelly betting on horse races with uncertainty in probability estimates*,
  [arXiv:1701.02814](https://arxiv.org/abs/1701.02814). Mutually exclusive outcomes, with
  probabilities from a multinomial logit, which is your exact setting.

- **Idea:** shrink Kelly stakes by an amount that depends on the variance of the probability
  estimate, rather than by a fixed fraction.
- **Why it applies:** your 5-seed ensemble spread and walk-forward residuals give a per-ladder
  uncertainty estimate. With a decaying edge, ladder-specific shrinkage (bet less when seeds
  disagree or the regime is new) should cut drawdowns more than it cuts growth.
- **Expected gain:** risk-adjusted PnL rather than nats; modest. **Cost:** 1-2 days on your
  existing ladder-Kelly solver.
- **Risk:** seed spread underestimates true model error. Calibrate shrinkage on walk-forward
  results, not on seeds.

### c4. Market making in binary markets
Avellaneda & Stoikov (2008), *High-frequency trading in a limit order book*, Quantitative Finance,
[doi:10.1080/14697680701381228](https://doi.org/10.1080/14697680701381228)

- **Idea:** quote around a reservation price with inventory-dependent skew.
- **Why it applies:** only if you move from conservative maker fills toward actively quoting. With
  books this thin, adverse selection around guidance releases dominates. Your "fill only on a
  print strictly through our price" model is already the right conservative test.
- **Gain:** possibly real PnL, not nats. **Cost:** 1-2 weeks including live plumbing.
- **Risk:** high (adverse selection, fees on makers since 2025).

### c5. LLM forecasting agents
- Halawi et al. (2024), *Approaching human-level forecasting with language models*,
  [arXiv:2402.18563](https://arxiv.org/abs/2402.18563)
- Karger et al. (2024/25), *ForecastBench*, [arXiv:2409.19839](https://arxiv.org/abs/2409.19839)
- Yang et al. (2025), *LLM-as-a-Prophet: Prophet Arena* (ICLR 2026), [arXiv:2510.17638](https://arxiv.org/abs/2510.17638)

- **Idea:** LLMs retrieve news and forecast event outcomes; they are competitive on some live
  benchmarks and slower than markets near resolution.
- **Why it does not apply:** a daily high is a physical quantity whose information is in NWP and
  observations, not text. An LLM adds nothing that a numeric feature cannot carry, and it adds
  latency, cost and leakage risk (pretraining data contains realised weather).
- **Gain:** 0. **Verdict:** hype for this project. (Multi-agent LLM swarms for Polymarket, such
  as PolySwarm, arXiv 2604.03888, are in the same category.)

### c6. Other market papers, briefly
- Qin & Yang (2026), *Polymarket-v1* database ([RePEc listing of arXiv 2606.04217](https://econpapers.repec.org/paper/arxpapers/2606.04217.htm)):
  tick-rule aggressor classification is about 50% accurate in prediction markets. You already use
  Kalshi's explicit taker side; keep it that way.
- Muthum (2025), [Kalshi weather calibration blog post](https://www.cs.utexas.edu/~kavish/blog/kalshi-weather-calibration.html):
  per-city calibration of the same seven cities. Not peer reviewed; consistent with Crosier.
- Weather-derivative pricing, e.g. Hening Tallarico & Olivares (2024),
  [arXiv:2411.12013](https://arxiv.org/abs/2411.12013): seasonal and climatological horizons with
  no NWP conditioning. **Not relevant** to day-ahead ladders.

---

## (d) Data-efficient training

### d1. Multi-task pooling across stations, targets and read times
Rasp & Lerch (2018) and Landry et al. (2024) in a10 are the evidence. Pooling with embeddings
beats separate models in post-processing.

Your §20 already pre-registers pooled reads, lows and new cities for the **combiner**. The
literature supports this direction. My only addition is to apply it to the **weather expert** as
well (a10), where the extra 55 stations are fully valid data. In the combiner they were not,
because there is no market for them.

### d2. Reforecast archives
- GEFSv12 reanalysis and reforecasts: Hamill et al. (2022), MWR,
  [doi:10.1175/MWR-D-21-0023.1](https://doi.org/10.1175/MWR-D-21-0023.1); reforecasts 2000-2019,
  5 members daily at 00 UTC, on [AWS `noaa-gefs-retrospective`](https://noaa-gefs-retrospective.s3.amazonaws.com/index.html).
- GFS MOS station archive at IEM since 2003-12-16 ([IEM MOS](https://mesonet.agron.iastate.edu/mos/)).

- **Idea:** pretrain the weather expert on 20 years of reforecasts, then fine-tune on the
  operational period.
- **Why it applies, honestly:**
  - Your GFS EMOS is already fit on 2015 onward, so the GFS-MOS side is not data-starved.
  - GEFS reforecasts would add an ensemble-spread signal with a long, version-consistent history.
    GEFSv12 has been operational since September 2020, matching the reforecast configuration.
  - But NBM already blends GEFS, so the marginal information over the market is small.
- **Expected gain:** +0.000 to +0.003. **Cost:** 5-8 days (gridded extraction; the reforecast
  `tmax` fields cover 6 h windows).
- **Point-in-time:** reforecasts are retrospective, but by a frozen model with no knowledge of
  outcomes. That is fine for *pretraining*; use only operational GEFS for test features.

### d3. Synthetic pretraining of the combiner
Already tested as G3: it helps at 10% of the data and hurts at 100%. The literature offers nothing
that would change that verdict. A market simulator cannot produce the private information that
makes the real market sharp (your fitted τ ranges from 5 to 29°F across folds). **Do not revisit.**

---

## Leakage checklist for anything above

1. **ERA5 or any reanalysis as a feature or initial condition** leaks: it is produced days later
   with observations from after the read time.
2. **Open-Meteo Historical Forecast API** is stitched short-lead forecasts, close to an analysis.
   It leaks.
3. **Retrospective AI hindcasts:**
   - WeatherNext 3 before 2026-07-01 is in-sample for the production model.
   - WeatherNext 2 history is undocumented; treat it as unsafe.
   - For any self-run model, check that the checkpoint's training cutoff precedes the test period
     and that initial conditions are real-time analyses.
4. **Init time versus availability:** stamp every product by when it was published (ECMWF
   dissemination schedule, MOS about 5 h after the run as you already do, LAMP and NBM about 1 h).
   Open-data delays changed in 2025.
5. **Version breaks act as leakage of a different kind.** Fitting one EMOS across NBM v4 and v5, or
   across IFS at 0.4° and 0.25°, makes the backtest look like a stationary world that live trading
   will not see.
6. **Settlement definition:** Kalshi's day is in local standard time and the source changed on
   2026-08-14. Products that forecast a daytime max (MOS `n_x`; NBM `txn` covers 12-06Z) need the
   correction Crosier describes. Your `mos_daytime_max` handles MOS; check NBM and any new product
   the same way.
7. **Neighbour-station leakage** in pooled weather experts: train only on days at or before each
   fold's last training day at *every* station (G3's rule).
8. **Price data:** keep using candles whose period ended by the read time. Note that MODEL_CARD
   already lists the gap between backtest candle closes and the live book.

---

## Hype check (what I would not spend time on)

| Item | Why not |
|---|---|
| Self-running GraphCast, GenCast, Aurora, FourCastNet 3 | weeks of work and GPU time; gridded and 6-hourly; already partly inside NBM v5; gain below the MDE |
| AIFS or AIGFS as separate experts | NBM v5 ingests both; archives too short and changed version mid-sample |
| TabPFN-2.5/3, TabICL as the combiner | non-commercial licence (2.5/3); i.i.d. prior; your own work says the bottleneck is information |
| Conformal prediction | optimises coverage, not log score; you are already calibrated |
| LLM forecasting agents | no information beyond numeric forecasts; leakage risk |
| GNN post-processing | needs dense station networks; you have 7-19 far-apart stations |
| More synthetic-market pretraining | G3 already answered it |

---

## Ranked shortlist: top 5 by expected ROI for isotherm

The ranking weighs expected nats or PnL, the probability that the gain is real, and cost, given a
gate MDE of about 0.004-0.006 nats per read.

### 1. Audit and adapt to the 2026 regime breaks (NBM v5.0, TWC settlement, RRFS/NBM input swap)
**Why first:**
- It is cheap and protects the edge you have.
- It may explain the lockbox decay: NBM absorbing AIFS and AIGFS should shrink exactly the GFS-only
  information your pool exploits.
- A real NBM-v5 effect means pre-April EMOS-NBM coefficients are mis-specified in live use, and
  another shift lands on 2026-11-03.

**First experiment (1-2 days):**
- On the seven stations, compute MAE and bias of NBM `txn` and GFS MOS `n_x` against settled
  highs, by month, from 2025-10 to 2026-09.
- Mark 2026-04-21 and 2026-08-14.
- Refit the frozen pool (market^w1 · EMOS-GFS^w2) on rolling 90-day windows and plot w2 over
  time.
- Pre-register a simple decision rule: if the post-v5 NBM error drops by more than X% relative to
  GFS MOS, or w2's rolling CI covers 0, refit EMOS-NBM on v5-only data with shrinkage toward
  pre-v5 coefficients, and log that the GFS edge is being priced out.
- Set up the same monitor for 2026-11-03 now.

### 2. Heteroscedastic EMOS from NBM's own spread (`XND`, `TSD`), already in your cache
**Why:**
- It costs one day and uses data you already have.
- It is textbook EMOS (Gneiting et al., 2005), and v5's QM-based standard deviation should make
  `XND` more informative from April 2026.
- At intraday reads, `TSD` on the remaining hours informs "how much warmer can it still get".

**First experiment (1 day):**
- Change `emos.py`'s log-σ link from `[1, cos t, sin t]` to
  `[1, cos t, sin t, log XND, |GFS − NBM|]`, with separate σ coefficients before and after
  2026-04-21.
- Re-run the G0 benchmark for EMOS-NBM alone (log score vs the old EMOS-NBM) and then the full
  isotherm, paired, on the last 12 months, with the usual date-block CI.
- Gate: expert-level gain CI above 0. Adopt into isotherm only if the isotherm-level difference
  is at least 0 at 3 of 4 reads.

### 3. LAMP as an intraday expert (and the cleanest test of "does more public guidance still help")
**Why:**
- Hourly, observation-conditioned station MOS that targets your 08/12/14 reads.
- Free, with an IEM archive back to July 2020 covering your whole walk-forward period.
- It is the one public product with obvious same-day specificity that you do not yet use.

**First experiment (2-3 days):**
- Ingest the IEM LAV archive and record which cycles exist at each read time (Crosier says only
  four per day).
- Build "LAMP max of remaining hours ∨ observed max so far" as a calendar-day (LST) max estimate.
- Fit EMOS-LAMP causally and add it as one more expert to the pool at the three same-day reads.
- Gate as in G0: paired gain CI above 0 at one or more same-day read on the last 12 months.
- If it fails, treat that as evidence that the public-guidance channel is exhausted. Stop adding
  NWP products, which saves the effort of a1 and a8.

### 4. A pooled DRN/BQN weather expert across the 55-station corpus and the Kalshi cities
**Why:**
- It turns the G3 corpus into useful data, but for the right component: the weather expert,
  where other stations are genuinely the same task.
- It replaces two thin Gaussian EMOS experts with one model that sees GFS, NBM, `XND`, LAMP and
  observations jointly.
- Rasp & Lerch, Landry et al. and Schulz & Lerch all show that pooled NN post-processing with
  embeddings beats per-station EMOS.

**First experiment (4-6 days):**
- Train a DRN (Gaussian or skew-normal) and a BQN with station and read-time embeddings on
  real CLI highs at all 62 stations, walk-forward with G3's causality rule.
- Score it first as a standalone weather forecast against EMOS-NBM on the Kalshi cities (a CRPS
  and log score gain is necessary).
- Then swap it into the pool in place of EMOS-GFS and EMOS-NBM, and run the §16-style paired gate.
- Expect a clear win at the expert level and a small one (+0.002 to +0.005) at the isotherm level.
  Pre-register that asymmetry so a failed isotherm gate is read correctly.

### 5. Start forward point-in-time archiving now for signals that cannot be backtested honestly
**Why:**
- WeatherNext 3's station head is the only AI product that is station-level, probabilistic,
  hourly and not an NBM input. Other candidates are AIFS ENS v2, IFS ENS spread, AIGEFS and RRFS.
- None of them has a clean history long enough for a gate. WN3 is in-sample before July 2026,
  AIFS changed version in May 2026, and RRFS starts 2026-10-06.
- The only honest test is forward. Every month of delay costs a month of test data.

**First experiment (1-2 days of setup, then waiting):**
- Request WeatherNext access and check the real-time licence terms for commercial use.
- Add a job that, at each read time, saves the latest available WN3 station-head quantiles, IFS
  ENS `mx2t6` member values, AIFS ENS and AIGEFS for the settlement points, each with its
  publication timestamp.
- Pre-register now a test on ladders from 2026-10-06 to 2027-04-05 (about 6 months, 3 reads):
  each new expert added to the then-current pool, paired gain, date-block CI.
- Expect most to fail. A pass on WN3 would be the first evidence of an AI-weather edge the market
  has not priced.
- For IFS ENS alone, an honest backtest is possible from the AWS archive (2024-02 onward at 0.25°).
  Run it as a side test in the same pipeline.

**Honourable mentions:**
- Uncertainty-scaled ladder Kelly (c3, 1-2 days; improves risk, not nats).
- An online pool-weight learner as a decay monitor (b3, 2-3 days).
- A market-anchored shift/scale correction head (b7, 2 days).
- Re-checking the current Kalshi fee schedule for the weather series (0.5 day).

---

## Sources verified on 2026-10-05

- arXiv metadata checked via the arXiv API for every arXiv ID cited.
- DOIs checked via Crossref (and doi.org for 10.1175/MWR2904.1).
- NWS Service Change Notices 26-24, 26-47 and 26-89 read in full text.
- WeatherNext dataset ranges and licence terms read from Google's Earth Engine catalog pages.
- Kalshi working paper read from the PDF (UCD/karlwhelan.com).

Not verified beyond the vendor or secondary source:
- Herbie's documentation of the AWS ECMWF archive start date.
- IEM's stated MOS and LAMP archive start dates.
- The WMO/NOAA press release figures for AIGEFS.
