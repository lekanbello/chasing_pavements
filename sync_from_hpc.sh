#!/usr/bin/env bash
# Pull results from HPC to local machine.
# Only pulls lightweight files (CSVs, JSONs), not large data files.
#
# Usage: ./sync_from_hpc.sh

HPC="torch"
HPC_ROOT="/scratch/ob708/chasing_pavements"

echo "Pulling results from HPC..."

# Summary CSVs
rsync -avz --progress \
  "${HPC}:${HPC_ROOT}/outputs/ssa_*.csv" \
  "./outputs/" 2>/dev/null

# Per-country result JSONs and param files
rsync -avz --progress \
  "${HPC}:${HPC_ROOT}/data/processed/*_counterfactual_results.json" \
  "${HPC}:${HPC_ROOT}/data/processed/*_model_params.json" \
  "${HPC}:${HPC_ROOT}/data/processed/*_run_status.json" \
  "./data/processed/" 2>/dev/null

# Sensitivity outputs
rsync -avz --progress \
  "${HPC}:${HPC_ROOT}/outputs/welfare_*.txt" \
  "./outputs/" 2>/dev/null

echo ""
echo "Done. Run 'python3 src/collect_results.py' to regenerate summary tables."
