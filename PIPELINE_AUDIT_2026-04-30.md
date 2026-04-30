# Pipeline Audit Findings — 2026-04-30

Audit triggered after a GPT-flagged inconsistency between calibration and counterfactual was confirmed. A Claude agent then performed a full read of the pipeline. This document captures the findings before any fixes are applied so the diff is reviewable.

## Severity definitions
- **CRITICAL**: changes headline numbers materially or invalidates results
- **HIGH**: changes numbers noticeably (>10% relative) or breaks assumptions
- **MEDIUM**: methodological issue, doesn't necessarily change numbers but is wrong
- **LOW**: cosmetic / clarity / minor

---

## Bugs (ordered by severity)

### [CRITICAL] Bug 1 — `d_hat` formula uses raw distance ratio instead of iceberg ratio
**Files:** `src/counterfactual.py:49`; `src/run_country.py:477`; `src/sensitivity_sigma_c.py:72`; `src/sensitivity_scale.py:61`

**Code:** `d_hat[mask] = tc_cf[mask] / tc_base[mask]` (raw weighted-km ratio)

**Should be:** `d_hat = (1 + tc_cf/scale) / (1 + tc_base/scale)` — the ratio of the iceberg costs `τ` that calibration uses (`calibrate.py:236`).

**Evidence (Tanzania, scale = 334.75 km, 158 districts):**
- Buggy: mean d_hat = 0.688 → mean shock 31%
- Correct: mean d_hat = 0.776 → mean shock 22%
- Magnitude overstated by ~1.4×; via `(σ-1) ≈ 4` powers in Eq 19 this propagates to ~6× welfare overstatement.

**Fix:** Pass calibrated `scale` (already in `tanzania_model_params.json["trade_cost_scale"]`) into `compute_d_hat`. Same fix in run_country.py and the two sensitivity scripts.

---

### [CRITICAL] Bug 2 — Saved π is column-stochastic; counterfactual treats it as row-stochastic
**Files:** Calibration: `src/calibrate.py:312-316`, `src/run_country.py:396-398`. Counterfactual: `src/counterfactual.py:296-298, 116, 121, 166, 179, 205`; `src/run_country.py:470, 494, 519`.

**Code:** Calibration produces `pi[i,j]` with **column sums = 1** (`pi[i,j]` = destination j's expenditure share on origin i). Counterfactual then row-renormalizes that matrix and uses it as if rows summed to 1. **The two conventions are transposes**, not the same.

**Evidence on saved Tanzania artifact:**
- Column sums: all exactly 1.0 (186/186)
- Row sums: range 0.05 to 4.44

**Fix (cleanest):** In `calibrate.py:316`, switch convention to row-stochastic (R&RH); update `Y_pred = pi.T @ Y` (line 319). Drop the row-renormalize at `counterfactual.py:297-298`. Re-run calibration end-to-end.

---

### [CRITICAL] Bug 3 — `sensitivity_sigma_c.py` raises productivities to `A**sigma` instead of `A**theta`
**File:** `src/sensitivity_sigma_c.py:91`

**Code:** `num = np.outer(A**sigma, np.ones(nn)) * cost**(-sigma)`

**Should be:** `A**theta * cost**(-theta)` — calibrated productivities were solved under θ=5; varying σ is supposed to vary only the (1−σ) exponent in Eq 19, not retroactively re-power calibrated productivities.

**Impact:** σ=3 and σ=7 ends of the published sensitivity grid are contaminated. The σ=5 central point is unaffected (θ = σ = 5 there). The σ×c table I removed from the deck would have been wrong even before the other bugs.

**Fix:** Use `theta_base` (already loaded at line 21) instead of `sigma` for the calibrated productivity exponent.

---

### [HIGH → MEDIUM after model fix] Bug 4 — Headline welfare uses `np.median` instead of population-weighted mean; convergence quality not saved
**Files:** `src/counterfactual.py:218-219, 244, 358-360`; `src/run_country.py` (no CV computed at all)

**Code:** `welfare_change = np.median(welfare_by_loc)`. Stage-2 cross-locational CV is computed at line 218 but only printed to stdout — never saved to JSON.

**Why it matters:** Under perfect mobility, all entries of `welfare_by_loc` should equalize and median = mean. They don't, because the solver doesn't drive CV exactly to zero. Median:
- Gives a different number than the correct utilitarian aggregate (population-weighted mean of consumption-equivalent welfare)
- Hides whether Stage 2 actually converged

**Verified:** All 41 saved per-country JSONs have `welfare_cv: None`. We cannot check retroactively whether any country's Stage 2 was non-convergent.

**Severity nuance (post-review):** Once Bugs 1, 2, and 7 are fixed and the solver actually equalizes welfare across locations under perfect mobility, the median-vs-weighted-mean question becomes near-irrelevant (they coincide at convergence). The save-CV part of this fix is still important for diagnostics; the median→mean swap is hygiene, not first-order.

**Fix:** `welfare_change = np.average(welfare_by_loc, weights=L_prime)`. Save `welfare_cv` to JSON. Flag countries with CV > 0.05 as non-convergent in `collect_results.py`.

---

### [HIGH] Bug 5 — Stage 1 (fixed-pop) welfare has an extraneous `ŵ` factor
**Files:** `src/counterfactual.py:148`; `src/run_country.py:504`; `src/sensitivity_scale.py:103`

**Code:** `welfare_fixed = w_hat * (pi_nn / pi_nn_prime_fixed)**(α/(σ-1))`

**Should be:** `(π_nn / π'_nn)^{α/(σ-1)}` — no leading ŵ. Under R&RH with L̂=1, substituting d̂_nn=1 into Eq 19 and computing `ŵ/P̂` shows ŵ cancels out. The included multiplier overstates dispersion across locations and biases the L-weighted aggregate.

**Impact:** ~±5 pp on the Stage 1 number; spatial cross-section (top winners/losers) more affected than the scalar headline.

**Fix:** Drop `w_hat *` prefix at all three sites.

---

### [HIGH] Bug 6 — `real_income_hat` for mapping uses a different formula than the headline welfare; framing inconsistent
**File:** `src/counterfactual.py:227` vs. `:214`

**Code:**
- Line 227 (saved to GeoPackage as `real_income_hat`, used for spatial maps): `w_hat × (π_nn/π'_nn)^{1/(σ-1)}`
- Line 214 (saved as `welfare_pct`, the headline): `(π_nn/π'_nn)^{α/(σ-1)} × (λ/λ')^{(σ(1-α)-1)/(σ-1)}`

These are different objects. Line 227 is real-wage net of the goods-price index, **excluding the land/rent (housing) effect**; line 214 is the full Eq-21 welfare including the housing channel via `λ̂`. With σ=5, α=0.65, line 227's exponent on `(π_nn/π'_nn)` is 0.25 vs line 214's 0.16 — line 227 inflates dispersion ~1.5×.

**Severity nuance (post-review):** This is more a labeling/framing inconsistency than an algebra bug. Both objects are well-defined and useful — but the deck and any downstream figures need to be explicit about which one is being shown. If district maps are interpreted as "welfare gains," they're showing the wrong thing. If they're explicitly "real income excluding housing," they're showing the right thing under a different name.

**Fix:** Pick a definition. If the deck/maps are meant to represent welfare consistent with the headline number, switch line 227 to evaluate the full Eq 21 location-by-location with that location's own `λ̂`. Otherwise, rename `real_income_hat` to something like `real_wage_hat` and label all derivative figures accordingly.

---

### [MEDIUM] Trade-cost normalization `scale` recomputed per rebuild → inconsistent across robustness scenarios
**Files:** `src/calibrate.py:228-234`; `src/run_country.py:377-378`; cascades into `src/sensitivity_unknown.py`.

**Code:** `scale = median(off_diag_distances) / 4.0`. Recomputed each scenario from a different baseline distance distribution, so the iceberg level shifts across scenarios in a way that confounds the unknown-road effect with the normalization.

**Impact:** ~1-2 pp per scenario in Tanzania; doesn't change ranking but contaminates the "spread" diagnostic in the unknown-road sensitivity.

**Fix:** Pin `scale` to the baseline value across robustness scenarios.

---

### [MEDIUM] Edge dedup in graph build can resolve ties differently for baseline vs counterfactual
**Files:** `src/run_country.py:217-222`; `src/network.py:213-217`

**Code:** When two parallel OSM edges connect the same node pair (e.g. paved primary + unpaved track), the build keeps the min-cost edge. This is recomputed independently for baseline and counterfactual, so the same node pair can use different physical edges in the two graphs.

**Impact:** Likely <1 pp; rare in OSM. Worst when many parallel edges exist.

**Fix:** Build edge-set ONCE keyed by (u, v, surface_class); derive baseline and counterfactual cost arrays from the same edge list.

---

### [LOW] `sensitivity_scale.py:103` Stage 1 welfare inherits the extra `ŵ` issue from Bug 5
Same fix.

---

### [LOW] Disconnected-pair `d_hat = 1` is consistent but undocumented
**File:** `src/counterfactual.py:43-50`

Not a bug, but the comment doesn't explain why d_hat=1 is correct (because baseline τ has the same finite max-distance fallback in counterfactual).

---

## Issues that aren't bugs but worth flagging

- Calibrated productivities `A` are conditional on Bug 2's column-stochastic interpretation. Fixing Bug 2 means re-running calibration end-to-end — A will change, not just the counterfactual.
- `welfare_cv = None` across all 41 saved JSONs means we cannot retroactively check Stage 2 convergence. Re-run is required either way.
- The variable name `lam_prime = lam_hat * lam` is misleading — it isn't the "prime" of hat algebra, just the new population share level.
- `pop_floor = median(L) * 0.01` may artificially boost very small districts; documented but no test for sensitivity.

---

## Code that was checked and believed correct

- Phase 1 (`ingest.py`): surface classification, length computation
- Phase 2 graph construction (`network.py:parse_simplified_graph`)
- Cost-multiplier application per surface class (`network.py:194-207`)
- Wage market clearing form `pi_prime.T @ (w_hat × λ̂ × wl)` — *given* whichever pi convention is in use
- Population mobility Eq 20: `λ̂ ∝ (π̂_nn)^{-γ}` with γ = α/(σ(1-α)-1)
- BFI population-weighted overlay (`calibrate.py:99-193`)
- `Y_predicted = pi @ Y` aggregation (correct given column-stochastic pi)

---

## Files not audited (out of scope)

- `src/price_elasticity.py`, `src/price_road_regression.py`, `src/market_road_distances*.py` — reduced-form regressions, not GE welfare
- `src/validate_surface.py`, `src/build_country_registry.py`, `src/country_config.py` — data prep
- `src/gmaps_*.py`, `src/render_gmaps_figures.py`, `src/make_deck_schematics.py` — validation/viz, independent of welfare
- `hpc/*.sh` — shells, same code path
- `notebooks/*.ipynb` — teaching

---

## Blast radius

| Output | Affected by |
|---|---|
| 41-country headline welfare | Bugs 1 + 2 + 5 + 6 |
| σ × c sensitivity table | Bugs 1 + 2 + 3 + 5 |
| Trade cost scale sensitivity | Bugs 1 + 2 + 5 |
| Unknown-road sensitivity (Tanzania) | Bugs 1 + 2 + 5 + scale recomputation |
| District-level maps & winners/losers | Bug 6 (different formula); ranking ≈ preserved, magnitudes not |
| Reduced-form price-distance regressions | Unaffected |
| Google Maps validation | Unaffected |
| OSM vs Liu validation | Unaffected |
| Calibrated A and a | Conditional on Bug 2's pi convention; will change |

---

## Additional findings (post-audit, from second GPT review)

### [CRITICAL] Bug 7 — Phase 3 calibration is the wrong model for the Phase 4 hat algebra
**Files:** Calibration: `src/calibrate.py:305-316`, `src/run_country.py:391-397`. Hat algebra: `src/counterfactual.py:114, 164, 203`; `src/run_country.py:484`.

R&RH 2017 Eqs 18–21 are derived from a Krugman-CES spatial model. The required baseline trade-share equation (their Eq 9 in counterfactual form) is

> π_ni ∝ **L_i** × A_i^{σ−1} × (τ_ni × w_i^α)^{1−σ}

Three things must match between calibration and hat algebra:
1. **Source-size term `L_i`** (mass of varieties under monopolistic competition)
2. **Same elasticity** as the counterfactual: `(σ − 1)`, not `θ`
3. Same productivity exponent: `A_i^{σ−1}`

Phase 3 currently constructs

> π_ni ∝ A_i^θ × (τ_ni × w_i^α)^{−θ}

— EK-style, with **no L_i** and elasticity θ instead of σ−1. With `PARAMS = {theta: 5, sigma: 5}`, even the elasticities don't line up (calibration uses 5; hat algebra uses 4).

This means `counterfactual.py:164`'s `factor = (d̂ × ŵ × L̂)^{1−σ}` is being applied to a baseline π that doesn't carry an `L` factor — so the `L̂` term is rescaling something that was never proportional to L.

**Evidence on Tanzania artifact** (rebuilding π under each fix):

| Calibration form | Median diag(π) |
|---|---:|
| (a) Current: `A^θ × cost^{−θ}`, no L | 0.4417 |
| (b) Fix elasticity only: `A^{σ−1} × cost^{1−σ}`, no L | 0.2989 |
| (c) Full Krugman-CES: `L × A^{σ−1} × cost^{1−σ}` | **0.2403** |

The L term shifts π_nn unevenly across districts — tiny districts collapse toward 0, large districts (Dar es Salaam regions) hold steady. The cross-sectional dispersion of π_nn is materially different.

**Why this matters:** Even after fixing Bugs 1, 2, 4, 5, 6 the saved π is the wrong sufficient statistic. The hat algebra cannot recover the right counterfactual from a baseline calibrated under a different model.

**Fix (principle, not recipe):** Pick one model family — pure R&RH Krugman-CES is the natural choice given the existing hat algebra — and make calibration and counterfactual consistent with it. The directional changes in calibration are:
1. Drop `theta` from `PARAMS`; use `(σ − 1)` as the trade elasticity everywhere
2. Add the source-employment factor `L_i` to the trade-share numerator
3. Re-derive the productivity inversion and price-index recovery under this convention

The exact code recipe should be re-derived from R&RH Eqs 9 and 18-21 cleanly when the time comes; the version above is directionally right but worth re-checking against the paper rather than treating as a finalized spec. After this, calibrated `A` and `a` will be different from the current saved values — Phase 3 re-runs end-to-end.

---

### [HIGH] Bug 8 — Trade-cost normalization fixes median τ, not a domestic-share moment → cross-country π_nn spans [0.15, 0.98]
**Files:** `src/calibrate.py:226-237`; `src/run_country.py:377-378`.

**Code:** `scale = median_off_diag_distance / (target_median_τ − 1)` with `target_median_τ = 5`. The comment claims this gives "median π_nn ≈ 0.4" but that's only true under one specific distance distribution.

**Evidence on saved 41-country `*_model_params.json`:**
- Median π_nn range: **0.153 (Nigeria) → 0.977 (Sierra Leone)**
- Bottom 5 most-integrated calibrated countries: Nigeria 0.15, DRC 0.20, Malawi 0.28, Kenya 0.34, Ghana 0.42
- Top 5 most-autarkic calibrated countries: Sierra Leone 0.98, Côte d'Ivoire 0.95, Rwanda 0.95, Burkina Faso 0.93, Eswatini 0.92

**Why this matters:** Welfare gains from paving depend strongly on the baseline π_nn. A country calibrated near autarky (Sierra Leone π_nn = 0.98) has almost no room for paving to reduce trade costs — by construction, not by data. A country calibrated as nearly-fully-integrated (Nigeria π_nn = 0.15) has artificially large welfare elasticity. Cross-country welfare magnitudes are riding on this calibration choice, not on real economic differences.

**Fix (principle, not recipe):** Replace the ad hoc τ-target with calibration to a defensible empirical moment. Two distinct decisions to make:
1. *What moment?* Median π_nn is convenient but not the only choice; share of inter-regional trade in GDP, a gravity-style elasticity from Donaldson-type data, or pinning a single border crossing's flow are all defensible options.
2. *Common across countries, or country-specific?* Forcing the same moment value across all 41 countries (e.g. median π_nn = 0.4 everywhere) is itself a strong assumption — it implies the underlying degree of regional integration is identical across SSA. Country-specific targets (e.g. from country-level trade-flow data where available) would be more honest where data permits, and the common-target fallback can be reserved for countries without such data.

The 1-D root-finder mechanic is straightforward in either case; the substantive call is which moment, and at what level.

---

## Updated remediation order

(Bugs 7 and 8 inserted; previous order shifts.)

1. **Bug 7** (CES vs EK elasticity) — touches the trade-share formula at the deepest level. Drop `theta` from PARAMS, use `(σ − 1)` everywhere in calibration. Calibration must be re-derived end-to-end under this convention.
2. **Bug 2** (π row vs column convention) — clean up at the same time as Bug 7 since they both edit the calibration's trade-share construction.
3. **Bug 1** (`d_hat` formula) — one-line fix in `compute_d_hat`, plus matching update at three other sites.
4. **Bug 5** (extraneous ŵ in Stage 1 welfare) — three sites.
5. **Bug 4** (median → weighted mean; save CV).
6. **Bug 6** (unify `real_income_hat` with `welfare_by_loc`).
7. **Bug 3** (`A**sigma` vs `A**theta` in `sensitivity_sigma_c.py`).
8. **Bug 8** (scale calibration moment) — switch from τ-target to π_nn-target via 1-D root-find. Re-calibrate scale per country.
9. Re-run Phase 3 + Phase 4 for Tanzania end-to-end; verify Stage 1 lands in a sensible range.
10. Push to HPC; re-run all 41 countries.
11. Regenerate all figures in `outputs/figures/`.
12. Rebuild deck with corrected numbers and revised framing (story survives, magnitudes don't).

**Expected post-fix range:** Genuinely unknown until rerun. Earlier numbers in this document ("Tanzania Stage 1 +6-10%", "continental ~3-5%") were back-of-envelope guesses based on partial-fix replays; they are not forecasts and should not be cited. Bug 7's structural rewrite of calibration combined with Bug 8's scale recalibration could shift things in either direction. The qualitative story (paved vs unpaved matters; remote/poor countries gain more) is likely robust; the magnitudes are not predictable without rerunning the full pipeline end-to-end.

1. Bug 2 (π convention) — touches calibration, so do it first
2. Bug 1 (`d_hat`) — small change, immediately fixes the biggest magnitude error
3. Bug 5 (Stage 1 welfare ŵ factor) — three sites
4. Bug 4 (median → weighted mean; save CV)
5. Bug 6 (unify real_income_hat with welfare_by_loc)
6. Bug 3 (σ-sensitivity A**theta vs A**sigma)
7. Re-run Phase 3 + Phase 4 for Tanzania end-to-end; verify Stage 1 lands at ~6-10% and Stage 2 lower.
8. Push to HPC; re-run all 41 countries
9. Regenerate all figures in `outputs/figures/`
10. Rebuild deck with corrected numbers and revised framing (story survives, magnitudes don't)

Expected post-fix Tanzania Stage 1: **+6 to +10%** (was +50%). Continental average: **~3-5%** (was +20%).
