#!/bin/bash
# Slurm job script for individual analysis scripts
#
# Usage:
#   sbatch hpc/run_analysis.sh sensitivity_unknown --iso3 TZA
#   sbatch hpc/run_analysis.sh market_road_distances --country KEN
#   sbatch hpc/run_analysis.sh sensitivity_sigma_c
#   sbatch hpc/run_analysis.sh sensitivity_scale
#   sbatch hpc/run_analysis.sh price_elasticity --country all
#   sbatch hpc/run_analysis.sh collect_results
#   sbatch hpc/run_analysis.sh validate_surface

#SBATCH --job-name=chasing_analysis
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32GB
#SBATCH --time=03:00:00
#SBATCH --output=/scratch/%u/chasing_pavements/logs/analysis_%j_%x.out
#SBATCH --error=/scratch/%u/chasing_pavements/logs/analysis_%j_%x.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=%u@nyu.edu
#SBATCH --account=torch_pr_730_general

# ==============================================================================
# Environment
# ==============================================================================
PROJECT_DIR="/scratch/$USER/chasing_pavements"
cd "$PROJECT_DIR"

module purge
module load anaconda3/2025.06
eval "$(conda shell.bash hook)"
conda activate "$PROJECT_DIR/chasing_env"
export PYTHONNOUSERSITE=True

mkdir -p "$PROJECT_DIR/logs"

# ==============================================================================
# Parse arguments
# ==============================================================================
SCRIPT_NAME="$1"
shift

if [ -z "$SCRIPT_NAME" ]; then
    echo "Usage: sbatch hpc/run_analysis.sh <script_name> [args...]"
    echo ""
    echo "Available scripts:"
    echo "  sensitivity_unknown    --iso3 TZA"
    echo "  market_road_distances  --country KEN"
    echo "  sensitivity_sigma_c"
    echo "  sensitivity_scale"
    echo "  price_elasticity       --country all"
    echo "  collect_results"
    echo "  validate_surface"
    exit 1
fi

SCRIPT_PATH="src/${SCRIPT_NAME}.py"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "ERROR: Script not found: $SCRIPT_PATH"
    exit 1
fi

# ==============================================================================
# Run
# ==============================================================================
echo "=========================================="
echo "Script: $SCRIPT_PATH"
echo "Args:   $@"
echo "Job ID: $SLURM_JOB_ID"
echo "=========================================="

python3 "$SCRIPT_PATH" "$@"

echo "Job completed!"
