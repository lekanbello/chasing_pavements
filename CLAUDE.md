# Chasing Pavements — Project Context

## What This Is
Quantitative spatial general equilibrium analysis measuring the GDP cost of unpaved roads in Sub-Saharan Africa. Core counterfactual: how much higher would real GDP be if all unpaved roads were paved?

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
- **Phase 4 (Counterfactual analysis)**: DONE for 41 countries. Exact hat algebra (Eqs 18-21). Two-stage solver. Welfare gains range from +0.6% (South Africa) to +54.5% (Somalia).
- **Phase 5 (Robustness/extensions)**: PARTIALLY DONE. σ×c sensitivity table complete for Tanzania. Trade cost scale sensitivity complete. Kenya and Tanzania price elasticity estimated. Remaining: Google Maps cost ratio, reduced-form evidence, optimal paving, wet/dry season.

## Headline Results (41 SSA Countries, placeholder c=3.0)
- **Continental average welfare gain from full paving: ~20%**
- **Range: +0.6% (South Africa) to +54.5% (Somalia)**
- Top tier (>30%): Somalia, Congo DR, CAR, Malawi, Tanzania, Burundi, Kenya
- High (15-30%): Liberia, Namibia, Uganda, Mozambique, Ghana, Nigeria, Chad, Niger, Sudan, Congo Rep, Zambia, Angola
- Moderate (5-15%): Eq. Guinea, Benin, Mali, Ethiopia, Cameroon, Gabon, Guinea, Togo, Guinea-Bissau, Eswatini, Senegal, Zimbabwe
- Low (<5%): Djibouti, Burkina Faso, Gambia, Botswana, Rwanda, Sierra Leone, Cote d'Ivoire, South Africa
- **Model validation**: Countries known for good roads (South Africa, Botswana, Cote d'Ivoire, Rwanda) independently rank at the bottom — the ranking emerges from data, not assumptions
- **Missing**: 7 island nations (disabled), 2 with no GDP data (Eritrea, South Sudan)

## Key Results (Tanzania Deep-Dive, placeholder c=3.0)
- **Road network**: 677,579 km, 2.2% paved, 66.5% unpaved, 31.3% unknown surface
- **Connectivity**: 70.4% of admin-2 pairs connected through road network
- **Trade costs**: Mean reduction from paving everything: 30.3%. Range: 0% to 66.7%.
- **GE welfare gain**: ~34% with labor mobility, ~50% fixed population (Stage 1)
- **Sensitivity**: Welfare robust to trade cost normalization (47-52% across scale = 340-2654 km)
- **σ×c sensitivity**: Welfare ranges from +4% (σ=7, c=2.0) to +64% (σ=3, c=4.0). Central: +44% (σ=5, c=3.0)
- **Spatial pattern**: Remote western/southern Tanzania gains most; Dar es Salaam/Zanzibar lose (increased competition)
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
- GE model: Redding & Rossi-Hansberg (2017) with σ=5, α=0.65. Two-stage solver for stability.
- Trade cost normalization: τ = 1 + distance/scale, where scale calibrated to give target π_nn
- Counterfactual uses d_hat = tc_cf/tc_base (ratios only, no level normalization needed)
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
- **Unknown road sensitivity (full rebuild)**: Ran Phases 2-4 from scratch with cost_unknown = {1.0, 2.0, 3.0}. Tanzania welfare ranges from +26.3% (all unknown = paved) to +37.6% (all unknown = unpaved). Spread = 11 pp. Even the most optimistic assumption gives >25% welfare gain. Liu et al. suggests truth is near upper bound. Script: `src/sensitivity_unknown.py`.
- **Cross-country validation**: Model ranking matches known infrastructure quality without being calibrated to it. South Africa, Botswana, Rwanda at bottom; Somalia, Congo DR at top.
- **Trade cost normalization robustness**: Welfare stable (47-52%) across scale range 340-2654 km.
- **σ×c sensitivity**: Full grid reported. Central estimate robust; extreme parameters give wide range.
- **Differentiation from Akbar et al.**: They study urban mobility; we study inter-city trade costs and aggregate welfare.

## Google Maps API
- Use Routes API Compute Route Matrix (Essentials tier for free-flow duration)
- ~$2K for 500K OD pairs, 3K elements/min rate limit
- Returns both `duration` (free-flow) and `duration_in_traffic`
- Research credits CANNOT be used for Maps Platform

## Next Steps (Priority Order)
1. Donaldson-style cost ratio estimation (route decomposition + price data for Kenya)
2. Set up Google Maps Routes API for empirical cost ratio estimation
3. Build reduced-form evidence (price dispersion vs. paved share across countries)
4. Optimal paving policy counterfactual (budget-constrained planner)
5. Cross-country regression: welfare gain vs. country characteristics
6. Pull road summary stats from HPC for all 41 countries → OSM coverage table
7. Paper writing
