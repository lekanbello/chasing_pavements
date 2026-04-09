#!/bin/bash
# Slurm array job — run full pipeline for all enabled SSA countries
#
# Usage:
#   sbatch hpc/run_all.sh                      # all enabled countries
#   sbatch hpc/run_all.sh TZA KEN SEN          # specific countries only
#   sbatch hpc/run_all.sh --phase 1            # phase 1 only, all countries
#   sbatch hpc/run_all.sh TZA KEN --phase 2    # specific countries, specific phase

#SBATCH --job-name=chasing_all
#SBATCH --array=0-47%10
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64GB
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/%u/chasing_pavements/logs/country_%A_%a.out
#SBATCH --error=/scratch/%u/chasing_pavements/logs/country_%A_%a.err
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
mkdir -p "$PROJECT_DIR/data/raw"
mkdir -p "$PROJECT_DIR/data/processed"
mkdir -p "$PROJECT_DIR/outputs"

# ==============================================================================
# Parse arguments: extract --phase and country list
# ==============================================================================
PHASE=0
COUNTRIES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --phase)
            PHASE="$2"
            shift 2
            ;;
        *)
            COUNTRIES+=("$1")
            shift
            ;;
    esac
done

# ==============================================================================
# Determine which country this array task runs
# ==============================================================================
if [ ${#COUNTRIES[@]} -gt 0 ]; then
    # Specific countries provided — index into that list
    if [ "$SLURM_ARRAY_TASK_ID" -ge "${#COUNTRIES[@]}" ]; then
        echo "Array task $SLURM_ARRAY_TASK_ID exceeds country list (${#COUNTRIES[@]}). Exiting."
        exit 0
    fi
    COUNTRY_ISO="${COUNTRIES[$SLURM_ARRAY_TASK_ID]}"
else
    # Use master CSV — get the Nth enabled country
    COUNTRY_ISO=$(python3 -c "
import sys
sys.path.insert(0, 'src')
from country_config import get_enabled_countries
df = get_enabled_countries()
idx = ${SLURM_ARRAY_TASK_ID}
if idx >= len(df):
    print('SKIP')
else:
    print(df.iloc[idx]['iso3'])
")
    if [ "$COUNTRY_ISO" = "SKIP" ]; then
        echo "Array task $SLURM_ARRAY_TASK_ID exceeds enabled country count. Exiting."
        exit 0
    fi
fi

# ==============================================================================
# Run
# ==============================================================================
echo "=========================================="
echo "Country: $COUNTRY_ISO"
echo "Phase:   $PHASE (0=all)"
echo "Job:     $SLURM_JOB_ID / $SLURM_ARRAY_TASK_ID"
echo "=========================================="

python3 src/run_country.py --iso3 "$COUNTRY_ISO" --phase "$PHASE"

echo "Job completed: $COUNTRY_ISO"
