# Chasing Pavements — Session Handoff

**Last updated:** April 21, 2026 (end of Google Maps validation session)

This is a fast-loading summary to pick up the project mid-stream. For full context, see `CLAUDE.md`.

---

## Where we are

**Pipeline is done** for 41 mainland SSA countries. Headline result: real income would rise by ~20% on average across Sub-Saharan Africa if all unpaved roads were paved. Range: +0.6% (South Africa) to +54.5% (Somalia). Validated by the fact that countries with known good road infrastructure (Rwanda, Botswana, Côte d'Ivoire, South Africa) independently land at the bottom of the ranking without being told.

**Google Maps API has been validated.** Four tests show Google's travel times pick up surface differences when we force it onto specific OSM road segments. Paved/unpaved speed ratio ~1.20× across 50 queries. Method works; API key is set up; academic credits available.

**Fellowship one-pager is delivered** (`chasing_pavements_fellowship_update.docx`) with two maps: continental choropleth + Tanzania district-level map.

---

## The immediate decision

User asked (end of last session): *can we use Google speeds directly in the model instead of averaging into a single `c`?*

I laid out three options:

- **(A)** Keep current model; just update `c` from 3.0 to something informed by data (1.2-1.4 speed-only, 2-3 total cost). Zero code change.
- **(B)** Replace the `surface_multiplier` approach with a speed function estimated from ~500 Google queries per country. Edge cost = length / speed(surface, road_class). Moderate code change in `run_country.py`. **My recommendation.**
- **(C)** Query full bilateral Google Routes Matrix (~90K elements per country). Cleanest in principle but can't give us the counterfactual (all-paved) — we'd still need a surface-speed model. Redundant with (B).

User hasn't decided. Start next session by asking which they want.

---

## If user picks (B)

Build `src/gmaps_speed_function.py`:

1. Load Tanzania OSM roads (or any country). Filter to major road classes (trunk, primary, secondary, tertiary) with known surface tags, length 10–50 km.
2. Stratified random sample: ~60 segments per (road_class × surface_class) cell = 480 queries per country. Fits in 10K free tier.
3. Query Google with segment endpoints (same method as `gmaps_test_v3.py`/`v4.py` — already works).
4. Keep queries where Google route length matches OSM length within 0.7–1.3×.
5. Compute mean speed per cell. Save to `data/processed/{country}_speed_function.json`:
   ```json
   {"trunk": {"paved": 74.3, "unpaved": 58.2}, "primary": {...}, ...}
   ```
6. Modify `run_country.py` Phase 2 graph builder so edge weight = `length_km / speed[road_class][surface_class]`. Units become hours.
7. Re-run Phase 2-4 for Tanzania, compare new welfare gain to old.

Existing test scripts that already work:
- `src/gmaps_test.py` — single-query + hand-picked pairs (failed baseline)
- `src/gmaps_test_v2.py` — centroid-based (failed because Google reroutes)
- `src/gmaps_test_v3.py` — **OSM segment endpoints (this is the working method)**
- `src/gmaps_test_v4.py` — replication with 30 queries across road classes

The speed function script would be structured like v4 but with stratified sampling and saving a JSON instead of printing comparison.

---

## If user picks (A)

Trivial. Update the default `cost_unpaved` in `configs/ssa_countries.csv` from 3.0 to e.g. 2.5 and re-run.

Then report the sensitivity range: welfare gain at c=1.5 (pure speed), c=2.5 (speed + fuel), c=3.0 (current). You already have most of this from `src/sensitivity_sigma_c.py`.

---

## If user picks (C)

Bigger lift. Build `src/gmaps_bilateral.py`:
1. For each country, load admin-2 centroids (already in `{country}_admin2.gpkg`).
2. Use Routes Matrix API (up to 625 elements per request, 25×25 origins×destinations).
3. Query all pairs. Save to `{country}_gmaps_bilateral.npy`.
4. Use this matrix directly as the baseline trade cost. Model inversion and counterfactual proceed as normal, but counterfactual still needs the surface-speed model from (B) anyway.

---

## Other open threads

### Cross-country regression (not started, ~1 hour of work)
- `outputs/ssa_model_results.csv` has welfare for 41 countries
- Want to regress on: paved share, urbanization, network density, land area
- Need to merge with country covariates (most in `configs/ssa_countries.csv` already; paved share comes from road summary JSONs that weren't fully synced)

### Route decomposition (queued for HPC, never run)
- `src/market_road_distances_liu.py` builds graph from Liu shapefile, outputs paved_km/unpaved_km per Kenya market pair
- Was planned as the "Donaldson regression" input: `|log(p_i)-log(p_j)| = β₁ paved_km + β₂ unpaved_km`
- Potentially made redundant by Google Maps approach, but still useful as a cross-check

### Seasonal analysis (done)
- Kenya wet season +1.5% price dispersion vs dry. Modest but real. Fine for robustness section of paper.

---

## Critical reminders

1. **"Welfare" not "GDP".** The model computes real income / purchasing-power gains through lower prices, not nominal GDP. See `memory/language_precision.md`. This matters for any external communication — a referee will flag it immediately.

2. **OSM has low surface coverage in most countries.** Tanzania is 69% tagged but Kenya/Uganda are ~30%. The unknown-road sensitivity (`src/sensitivity_unknown.py`) shows this matters: +26% to +38% welfare range in Tanzania depending on unknown-road assumption. Even the most optimistic assumption gives >25%, so the qualitative result holds.

3. **Liu et al. data is on local disk but not tracked.** `data/raw/liu_et_al_kenya/` and `data/raw/liu_et_al_tanzania/`. Large shapefiles, gitignored.

4. **HPC state.** Code is pushed; data files (PBFs, GADMs, WorldPop, BFI GDP) are on `/scratch/ob708/chasing_pavements/`. Conda env at `chasing_env`. Jobs submit via `sbatch hpc/run_all.sh` (array job) or `sbatch hpc/run_analysis.sh <script> <args>` (individual analysis).

5. **RTFP price data is 1.1GB and gitignored.** Located at `data/raw/rtfp_prices.csv`. User copied from Dropbox; if missing, re-copy from: `/Users/olalekanbello/Dropbox/Nigeria Exchange Rate Shared/_Essential_Files/Nigeria_Revised_Paper_JIE/Data/World Bank/WLD_RTFP_mkt_2026-03-24.csv`.

---

## Quick commands

```bash
# Run any country pipeline locally
python3 src/run_country.py --iso3 KEN --phase 0

# Aggregate all country results
python3 src/collect_results.py

# Google Maps test (costs 30 API elements)
/Library/Developer/CommandLineTools/usr/bin/python3 src/gmaps_test_v4.py

# NOTE: use the /Library/Developer/... Python on local machine — Anaconda
# Python doesn't have geopandas. System Python does.

# HPC workflow
ssh torch
cd /scratch/ob708/chasing_pavements
git pull
sbatch hpc/run_analysis.sh <script_name> [args]
# then on local:
./sync_from_hpc.sh
```

---

## Project status at a glance

| Piece | Status |
|---|---|
| Phase 1–4 for 41 countries | ✅ Done |
| σ × c sensitivity (Tanzania) | ✅ Done |
| Trade cost scale sensitivity | ✅ Done |
| Unknown-road sensitivity (full rebuild) | ✅ Done |
| OSM vs Liu validation (93.7% agreement) | ✅ Done |
| Kenya price-distance regression | ✅ Done |
| Seasonal price analysis | ✅ Done |
| Google Maps API validation | ✅ Done (this session) |
| Google Maps speed function | ⏸ Awaiting user decision |
| Cross-country regression (n=41) | ⏸ Not started |
| Optimal paving policy | ⏸ Not started |
| Paper draft | ⏸ Not started |

Target: working paper by end of summer 2026.
