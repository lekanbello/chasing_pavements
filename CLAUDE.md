# Chasing Pavements — Project Context

## What This Is
Quantitative spatial general equilibrium analysis measuring the GDP cost of unpaved roads in Sub-Saharan Africa. Core counterfactual: how much higher would real GDP be if all unpaved roads were paved?

## Research Design Decisions Made
- **Framing**: Hook into Akbar, Couture, Duranton & Storeygard (2023) "unobserved road quality" residual. They show road quality explains large share of speed differences across countries but can't decompose it. We show surface type (paved vs unpaved) is a first-order component.
- **Cost ratio estimation**: Use Google Maps Routes API (Essentials tier, ~$2K for 500K OD pairs) to estimate unpaved speed penalty from simulated trips, following Akbar et al. methodology. For now using placeholder c_unpaved/c_paved = 3.0.
- **Road surface data**: Multiple ML-classified datasets exist (Liu et al. 2026 in ESSD, Mapillary-based classifiers, Kenya satellite study). Decision on which to use deferred — OSM surface tags are surprisingly good for Tanzania (69% coverage, ~100% on trunk/primary/secondary roads). Will triangulate across sources.
- **Reduced-form complement needed**: Pure structural results won't be enough. Need event study or correlational evidence (e.g., paved share vs nightlights growth at district level).
- **Optimal policy extension**: Beyond "pave everything" benchmark, compute marginal welfare contribution of each road segment → priority ranking for constrained planner.
- **Target countries**: Tanzania (started), Ethiopia, Kenya, Nigeria, Uganda, Ghana, Mozambique, Senegal.

## Pipeline Status
- **Phase 1 (Data ingestion)**: DONE for Tanzania. `src/ingest.py` downloads OSM PBF from Geofabrik, extracts road network, classifies surface types, saves to GeoPackage. `src/viz.py` produces road network maps and surface coverage charts.
- **Phase 2 (Trade costs)**: DONE for Tanzania. `src/network.py` parses PBF for graph topology using OSM node IDs, simplifies to intersection graph (~2M nodes, 2.6M edges, 95.8% connected), computes bilateral Dijkstra shortest paths between 186 admin-2 centroids. Produces baseline and counterfactual trade cost matrices. `src/viz_trade.py` produces choropleth maps, scatter plots, distribution charts, district rankings.
- **Phase 3 (Model calibration)**: DONE for Tanzania. `src/calibrate.py` aggregates WorldPop 2019 population and BFI subnational GDP (population-weighted overlay) to 186 admin-2 districts. Inverts GE model (Redding & Rossi-Hansberg 2017) to recover productivities and amenities. Trade cost normalization calibrated to give realistic domestic trade shares (median π_nn ≈ 0.4). Saves baseline trade shares for counterfactual.
- **Phase 4 (Counterfactual analysis)**: DONE for Tanzania. `src/counterfactual.py` implements exact hat algebra (Eqs 18-21 of Redding & Rossi-Hansberg 2017). Two-stage solver: Stage 1 fixes population, Stage 2 adds mobility. Headline: ~34% welfare gain (with mobility) or ~50% (fixed pop).
- **Phase 5 (Robustness/extensions)**: PARTIALLY DONE. Trade cost scale sensitivity analysis complete (welfare robust at 47-52% across scales). Kenya price data used to anchor distance elasticity. Remaining: σ sensitivity, cross-country, optimal paving, wet/dry season.

## Key Results (Tanzania, placeholder c=3.0)
- **Road network**: 677,579 km, 2.2% paved, 66.5% unpaved, 31.3% unknown surface
- **Connectivity**: 70.4% of admin-2 pairs connected through road network
- **Trade costs**: Mean reduction from paving everything: 30.3%. Range: 0% to 66.7%.
- **GE welfare gain**: ~34% with labor mobility, ~50% fixed population (Stage 1)
- **Sensitivity**: Welfare robust to trade cost normalization (47-52% across scale = 340-2654 km)
- **Spatial pattern**: Remote western/southern Tanzania gains most; Dar es Salaam/Zanzibar lose (increased competition)
- **Winners**: 150/158 districts gain; top gains are remote districts with mostly unpaved roads
- **Losers**: 8 districts (urban centers that currently benefit from better connectivity — face more competition post-paving)

## Kenya Price Data Calibration
- Source: World Bank RTFP dataset, 233 Kenyan markets, 2007-2026
- Commodity: Maize (o_maize_fao), 6.2M bilateral price-gap observations
- Distance elasticity: δ = 0.000377 per km (highly significant, t ≈ 1,140)
- Implied: 14.7% price gap at median distance (390 km straight-line)
- Implied scale for τ=1+dist/scale: ~2,654 km (straight-line) → ~1,000-1,500 km (road distance)
- Key finding: welfare results are robust to this calibration — changes headline by < 5 pp

## Key Files
- `src/ingest.py` — OSM PBF → road GeoDataFrame with surface classification
- `src/viz.py` — road network maps and surface coverage charts
- `src/network.py` — graph construction, shortest paths, trade cost matrices
- `src/viz_trade.py` — trade cost result visualizations
- `src/calibrate.py` — WorldPop + BFI GDP aggregation, GE model inversion
- `src/counterfactual.py` — hat algebra counterfactual solver, welfare computation
- `data/raw/tanzania-latest.osm.pbf` — raw OSM data (703 MB, gitignored)
- `data/raw/gadm41_TZA.gpkg` — GADM admin boundaries
- `data/raw/tza_ppp_2019.tif` — WorldPop population 2019 (485 MB, gitignored)
- `data/raw/bfi_gdp_025deg/` — BFI subnational GDP data
- `data/processed/tanzania_roads.gpkg` — processed road network
- `data/processed/tanzania_trade_costs_baseline.npy` — 186×186 baseline cost matrix
- `data/processed/tanzania_trade_costs_counterfactual.npy` — 186×186 counterfactual matrix
- `data/processed/tanzania_calibrated.gpkg` — calibrated admin-2 with pop, GDP, productivity, amenity
- `data/processed/tanzania_baseline_trade_shares.npy` — 186×186 baseline trade share matrix
- `data/processed/tanzania_model_params.json` — model parameters and calibration metadata
- `outputs/figures/` — all generated visualizations
- `outputs/kenya_price_elasticity.txt` — Kenya distance elasticity results
- `outputs/welfare_sensitivity.txt` — welfare sensitivity to trade cost scale

## Technical Notes
- Python 3.9.6, key packages: geopandas, osmium, scipy, matplotlib, contextily, rasterstats, wbgapi
- Graph simplification: contracts intermediate OSM nodes, keeps only intersections/endpoints
- GADM data from geodata.ucdavis.edu
- UTM zone 37S (EPSG:32737) for Tanzania distance calculations
- Trade cost normalization: τ = 1 + distance/scale, where scale calibrated to give target π_nn
- Counterfactual uses d_hat = tc_cf/tc_base (ratios only, no level normalization needed)
- GE model: Redding & Rossi-Hansberg (2017) with σ=5, α=0.65. Two-stage solver for stability.
- World Bank API fallback: Tanzania 2019 GDP = $61.03B cached in case API is down

## Key Papers
- Akbar, Couture, Duranton & Storeygard (2023) "The fast, the slow, and the congested" — 1200 cities, Google Maps methodology, unobserved road quality
- Akbar et al. (2023) AER "Mobility and Congestion in Urban India" — 57M simulated trips, validates Google Maps in developing countries
- Redding & Rossi-Hansberg (2017) "Quantitative Spatial Economics" — Annual Review of Economics. Model framework, hat algebra (Eqs 18-21), welfare formula
- Liu, Zhou, Zhang & Laari (2026) ESSD — first road surface dataset for 50 African countries, TabNet classifier, 87% accuracy
- Donaldson (2018), Allen & Arkolakis (2014), Fajgelbaum & Schaal (2020) — GE model precedents

## Extensions & Future Papers
- **Wet/dry season extension (Phase 5 robustness)**: Add seasonal cost ratios (c_unpaved_wet >> c_unpaved_dry) as a robustness check in the main paper. Shows the constant cost ratio is conservative and captures the nonlinear disruption during rains.
- **Paper #2: Seasonal Market Fragmentation**: Full analysis of wet-season road disruption — which districts become disconnected, for how long, and what that does to prices, storage, crop choice. Would need truck GPS trace data (Locus, Fleetmon, telecoms) to observe actual speeds and route impassability by season. Pair with agricultural price data showing wet-season price spikes in remote areas. More empirical, less structural than Paper #1.

## Identification / Robustness Notes
- **Unobserved road quality bundle**: Paved roads are systematically wider, better-maintained, better-aligned than unpaved. Our cost ratio captures the full bundle, not just surface. Frame as the policy-relevant object — real paving projects upgrade multiple characteristics simultaneously. Not a limitation.
- **OSM tags beyond surface**: Checked width (0.5%), lanes (0.4%), maxspeed (0.3%), smoothness (1.4%) — coverage too thin for systematic controls. Can use for spot checks where available.
- **Within-road-class estimation**: Can estimate speed penalty comparing paved vs. unpaved secondary roads (same class, different surface) to isolate surface from road class effects.
- **Differentiation from Akbar et al.**: They study urban mobility (within-city speed). We study inter-city trade costs and aggregate welfare. Overlap is methodology (Google Maps data), not contribution. Lead with GE counterfactual and policy numbers, not data methodology.
- **Trade cost normalization robustness**: Welfare gain is stable (47-52%) across scale parameter range 340-2654 km. Kenya food price data provides empirical anchor. Report full sensitivity table in paper.

## Google Maps API
- Use Routes API Compute Route Matrix (Essentials tier for free-flow duration)
- ~$2K for 500K OD pairs, 3K elements/min rate limit
- Returns both `duration` (free-flow) and `duration_in_traffic`
- Research credits CANNOT be used for Maps Platform
- Setup: Google Cloud Console → enable Routes API → generate API key

## Next Steps (Priority Order)
1. Sensitivity analysis across σ ∈ {3, 4, 5, 6, 7} and c ∈ {2.0, 2.5, 3.0, 3.5, 4.0}
2. Scale pipeline to second country (Kenya — has price data for validation)
3. Set up Google Maps Routes API for empirical cost ratio estimation
4. Build reduced-form evidence (price dispersion vs. paved share)
5. Optimal paving policy counterfactual (budget-constrained planner)
6. Scale to all 8 countries
7. Paper writing
