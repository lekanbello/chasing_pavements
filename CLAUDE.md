# Chasing Pavements — Project Context

## What This Is
Quantitative spatial general equilibrium analysis measuring the welfare cost of unpaved roads in Sub-Saharan Africa. Core counterfactual: how much higher would real income (welfare) be if all unpaved roads were paved? NOTE: The welfare gain is a real income / purchasing power measure (lower prices from cheaper trade), NOT a nominal GDP increase. Be precise about this distinction.

## Research Design Decisions Made
- **Framing**: Hook into Akbar, Couture, Duranton & Storeygard (2023) "unobserved road quality" residual. They show road quality explains large share of speed differences across countries but can't decompose it. We show surface type (paved vs unpaved) is a first-order component.
- **Cost ratio estimation**: Use Google Maps Routes API (Essentials tier, ~$2K for 500K OD pairs) to estimate unpaved speed penalty from simulated trips, following Akbar et al. methodology. For now using placeholder c_unpaved/c_paved = 3.0.
- **Road surface data**: OSM surface tags as primary source. Validated against Liu et al. (2026) ML-classified dataset — 93.7% road-level agreement. OSM coverage varies: Tanzania 69%, Senegal 48%, Kenya/Uganda ~31%.
- **Reduced-form complement needed**: Price dispersion vs. paved share regression using RTFP/WFP data. Donaldson (2018)-style route decomposition (paved_km vs unpaved_km) to estimate c directly.
- **Optimal policy extension**: Beyond "pave everything" benchmark, compute marginal welfare contribution of each road segment → priority ranking for constrained planner.
- **Scale**: Continental — 41 mainland SSA countries completed, pipeline fully automated on HPC.

## Pipeline Status
- **Phase 1 (Data ingestion)**: DONE for 41 countries. `src/run_country.py` auto-downloads OSM PBF, extracts road network, classifies surface types, saves road summary JSON.
- **Phase 2 (Trade costs)**: DONE for 41 countries. Graph construction using OSM node IDs, bilateral Dijkstra shortest paths between admin-2 centroids. Baseline and counterfactual trade cost matrices.
- **Phase 3 (Model calibration)**: DONE for 41 countries. WorldPop population + BFI subnational GDP aggregation. GE model inversion (Redding & Rossi-Hansberg 2017) to recover productivities and amenities.
- **Phase 4 (Counterfactual analysis)**: v1 done for 41 countries (numbers obsolete after April 2026 audit; see `PIPELINE_AUDIT_2026-04-30.md`). v2 rerun pending.
- **Phase 5 (Robustness/extensions)**: PARTIALLY DONE. σ×c sensitivity table (rewritten under v2; rerun pending). Trade cost scale sensitivity (rewritten under v2). Kenya and Tanzania price elasticity estimated. Remaining: Google Maps cost ratio, reduced-form evidence, optimal paving, wet/dry season.

## Headline Results — pending v2 rerun

**v1 numbers were rejected after the April 2026 audit (8 model bugs). The pre-rerun Tanzania smoke test under v2 gives Stage 2 welfare = +9.4% (down from v1's +34%) with welfare_cv = 0.0000 at convergence. Continental v2 numbers will be available after the HPC rerun.**

The v1 ranking pattern (Somalia/DRC/CAR at top; South Africa/Rwanda/Botswana at bottom) is likely preserved qualitatively but not quantitatively.

## Key Results (Tanzania Deep-Dive, post-audit v2)
- **Road network**: 677,579 km, 2.2% paved, 66.5% unpaved, 31.3% unknown surface (unchanged — Phase 1/2 not affected by audit)
- **Connectivity**: 70.4% of admin-2 pairs connected through road network
- **Trade costs**: Mean iceberg-ratio reduction from paving everything: 22.9% (v2 d_hat formula).
- **Welfare gains (v2 smoke test, three mobility regimes):**
  - Stage 1 (no mobility, pre-incidence): aggregate +9.24%, range across districts [-0.0%, +31.9%], std 5.79
  - Stage 2 (perfect mobility, headline): +9.44%, equalized across districts (CV = 0.0000)
  - Stage 3 (frictional mobility, κ=2): aggregate +9.38%, range [+2.4%, +22.4%], std 3.72
- **Stage 3 redistribution pattern**: top winners are remote mainland districts (Nyang'hwale, Pangani, Mkalama) gaining +18-22% with ~+16-26% in-migration; bottom are Zanzibar/Pemba islands and Lake Victoria's Ukerewe — they're disconnected from mainland paving and lose ~12% of population to better-connected mainland districts.
- **Calibrated trade-cost scale**: 263 km (brentq-chosen so median π_nn = 0.4)
- **σ×c sensitivity**: rewritten under v2; rerun pending
- **Winners**: 150/158 districts gain; top gains are remote districts with mostly unpaved roads
- **Losers**: 8 districts (urban centers facing more competition post-paving)

## Price Data Calibration
- **Kenya (RTFP)**: 233 markets, 6.2M bilateral obs, δ = 0.000377/km (t ≈ 1,140), implied scale ~2,654 km
- **Tanzania (WFP)**: 25 markets, 27K bilateral obs, δ = 0.000090/km (t = 14.4), implied scale ~11,131 km
- Kenya estimate is more reliable (200x more obs, actual market locations vs. regional proxies)
- Welfare results are robust to this calibration — changes headline by < 5 pp across scale range

## Key Files
### Pipeline (per-country)
- `src/run_country.py` — full pipeline runner (Phases 1-4), auto-downloads missing data
- `src/country_config.py` — builds config dicts from master CSV
- `configs/ssa_countries.csv` — master registry: 48 countries with metadata, GDP, UTM zones

### Individual Phase Scripts (Tanzania originals)
- `src/ingest.py` — Phase 1: OSM PBF → road GeoDataFrame
- `src/viz.py` — road network visualizations
- `src/network.py` — Phase 2: graph construction, shortest paths
- `src/viz_trade.py` — trade cost visualizations
- `src/calibrate.py` — Phase 3: population/GDP aggregation, model inversion
- `src/counterfactual.py` — Phase 4: hat algebra counterfactual solver

### Analysis & Robustness
- `src/sensitivity_sigma_c.py` — σ × c parameter sensitivity
- `src/sensitivity_scale.py` — trade cost normalization sensitivity
- `src/price_elasticity.py` — distance elasticity from food price data (Kenya/Tanzania)
- `src/validate_surface.py` — OSM vs Liu et al. (2026) comparison
- `src/collect_results.py` — aggregate per-country results into summary CSVs
- `src/build_country_registry.py` — generate master CSV from WDI API

### HPC
- `hpc/run.sh` — single-country Slurm job
- `hpc/run_all.sh` — array job for all enabled countries (or specific list)
- `sync_to_hpc.sh` — push code to HPC
- `sync_from_hpc.sh` — pull results from HPC

### Teaching
- `notebooks/01_graphs_and_algorithms.ipynb` — graphs, Dijkstra's, trade costs
- `notebooks/02_ge_model_math.ipynb` — GE model, hat algebra, welfare formula

## Technical Notes
- Python 3.9.6 (local) / 3.11 (HPC), key packages: geopandas, osmium, scipy, matplotlib, rasterstats, wbgapi
- **GE model: Redding & Rossi-Hansberg (2017) Krugman-CES throughout.** σ=5 is the CES elasticity; trade elasticity is σ−1=4. α=0.65 (labor share). Two-stage solver (fixed pop → mobility) for stability.
- **Calibration version v2-rrh-krugman-cse-row** (after April 2026 audit; see `PIPELINE_AUDIT_2026-04-30.md`). Trade-share matrix π is row-stochastic with `π[n, i]` = destination n's expenditure share on origin i. Equation: π_ni ∝ L_i × A_i^{σ-1} × (w_i^α × τ_ni)^{1-σ}. The source-employment factor `L_i` is essential — without it, the L̂ term in the hat-algebra trade-share update has nothing to rescale.
- **Trade-cost scale calibration:** τ = 1 + distance/scale. Scale calibrated per country via `scipy.optimize.brentq` to hit median π_nn = 0.4 (R&RH benchmark, anchored to inter-state US trade). Common target across all 41 countries — this is an assumption; robustness to country-specific or empirically-anchored targets (e.g. Donaldson-style δ from price data) is a follow-up.
- **Counterfactual d_hat:** d_hat = (1 + tc_cf/scale) / (1 + tc_base/scale), the iceberg-cost ratio τ'/τ. NOT the raw distance ratio — that was the v1 bug.
- **Welfare aggregation:** R&RH 2017 Eq 21 evaluated location by location, then aggregated by population-weighted mean. At Stage 2 perfect-mobility convergence the cross-locational welfare CV → 0; we save `welfare_cv` to JSON and flag countries with CV > 0.05 as non-convergent.
- **Three mobility regimes computed.** The solver runs three nested counterfactuals and saves all three to outputs:
  - **Stage 1 (κ = 0, no mobility):** pre-mobility incidence — `welfare_s1_hat` per district. Used for "winners and losers" maps that show who benefits if no one moves.
  - **Stage 2 (κ = ∞, perfect mobility) — HEADLINE:** welfare equalizes across locations by assumption; `welfare_pct` is the population-weighted mean. This is the default reported number.
  - **Stage 3 (κ finite, R&RH frictional mobility):** migration update is `λ̂_n ∝ V̂_n^κ` rather than the perfect-mobility limit. Welfare varies across locations; in-migration partly equalizes gains. Default κ = 2.0 (PARAMS). Saved as `welfare_s3_pct` (aggregate) and `welfare_s3_hat` (per-location), with population shifts in `pop_s3_hat`.
- Auto-download: run_country.py fetches missing PBF/GADM/WorldPop via curl
- HPC: NYU Torch cluster, Slurm array jobs, 4 cores / 32 GB per country

## Key Papers
- Akbar, Couture, Duranton & Storeygard (2023) "The fast, the slow, and the congested" — unobserved road quality
- Akbar et al. (2023) AER "Mobility and Congestion in Urban India" — Google Maps validation
- Redding & Rossi-Hansberg (2017) "Quantitative Spatial Economics" — model framework
- Donaldson (2018) "Railroads of the Raj" — network-based trade costs, price validation
- Liu, Zhou, Zhang & Laari (2026) ESSD — road surface dataset for 50 African countries
- Allen & Arkolakis (2014), Fajgelbaum & Schaal (2020) — GE model precedents

## Extensions & Future Papers
- **Wet/dry season extension (Phase 5 robustness)**: Add seasonal cost ratios as robustness check. Shows constant ratio is conservative.
- **Paper #2: Seasonal Market Fragmentation**: Full analysis of wet-season road disruption. Needs truck GPS trace data + agricultural price data.
- **Donaldson-style cost ratio estimation**: Decompose routes into paved/unpaved km, regress price gaps on each → directly estimate c from data. Key empirical contribution.

## Identification / Robustness Notes
- **Unobserved road quality bundle**: Cost ratio captures full bundle (surface + width + alignment). Frame as policy-relevant object.
- **OSM vs Liu et al. validation**: 93.7% road-level agreement. OSM is conservative (lower paved rate).
- **Unknown road sensitivity (full rebuild)**: Script `src/sensitivity_unknown.py` re-runs Phases 2-4 from scratch with cost_unknown = {1.0, 2.0, 3.0}. (v1 numbers below are obsolete; rerun pending under v2.)
- **Cross-country validation**: Model ranking matches known infrastructure quality without being calibrated to it. (v1 ranking pattern; v2 numbers pending rerun.)
- **σ×c sensitivity**: Each cell fully re-calibrated under that σ in v2 (script `src/sensitivity_sigma_c.py` rewritten). v1 table is obsolete.
- **Differentiation from Akbar et al.**: They study urban mobility; we study inter-city trade costs and aggregate welfare.

## v1 → v2 audit and fixes (April 2026)
A pipeline audit (`PIPELINE_AUDIT_2026-04-30.md`) caught 8 issues in the v1 calibration/counterfactual code that together overstated the headline welfare gain by roughly 6×. v2 fixes:
1. Calibration switched from EK-style `A^θ × cost^{-θ}` (no source size) to R&RH Krugman-CES `L × A^{σ-1} × cost^{1-σ}` (Bug 7).
2. π is now row-stochastic by construction (Bug 2).
3. `d_hat` is the iceberg ratio `(1+tc'/s)/(1+tc/s)`, not the raw distance ratio (Bug 1).
4. Headline welfare aggregation uses population-weighted mean; `welfare_cv` saved (Bug 4).
5. Stage 1 welfare formula no longer has an extraneous ŵ factor (Bug 5).
6. District-level welfare uses the full Eq 21 expression — same object as the headline (Bug 6).
7. σ-sensitivity script re-inverts calibration per σ (Bug 3).
8. Trade-cost scale calibrated per country via brentq on median π_nn = 0.4 (Bug 8).

Pre-rerun Tanzania smoke test: Stage 2 welfare = +9.4% (vs v1's +34%); welfare_cv = 0.0000 at convergence. Full 41-country rerun pending.

## Google Maps API
- Use Routes API Compute Route Matrix (Essentials tier for free-flow duration)
- ~$2K for 500K OD pairs, 3K elements/min rate limit
- Returns both `duration` (free-flow) and `duration_in_traffic`
- User HAS academic research credits — money is not a constraint
- API key saved in `.env` (gitignored). 51 of 10K free elements used.

## Google Maps Validation Results (April 2026)
- Ran 4 test scripts (`src/gmaps_test*.py`) to validate OSM surface classifications
- **Key finding**: When Google is forced to use specific OSM road segments (by querying their exact endpoints), paved roads are ~20% faster than unpaved roads
- Pooled across 50 queries in Tanzania (trunk/primary/secondary): paved ~66 km/h, unpaved ~55 km/h, ratio 1.20x
- v3 script (trunk-only, 5+5): 1.39x. v4 (larger, mixed classes): 1.17-1.32x
- **Interpretation**: Speed ratio is a lower bound on cost ratio `c`. Total economic cost also includes vehicle wear, fuel, reliability, spoilage — consistent with `c` of 2-3.
- **Validation**: OSM surface tags and Google's driver speeds agree on which roads are fast vs slow. Two independent data sources converge.
- Earlier tests failed because: (v1) hand-picked "unpaved" routes have been paved in last decade, (v2) centroid-to-centroid lets Google route around unpaved roads. Lesson: force Google onto specific segments by querying OSM segment endpoints.

## Next Steps (Priority Order)
1. Donaldson-style cost ratio estimation (route decomposition + price data for Kenya)
2. Set up Google Maps Routes API for empirical cost ratio estimation
3. Build reduced-form evidence (price dispersion vs. paved share across countries)
4. Optimal paving policy counterfactual (budget-constrained planner)
5. Cross-country regression: welfare gain vs. country characteristics
6. Pull road summary stats from HPC for all 41 countries → OSM coverage table
7. Paper writing
