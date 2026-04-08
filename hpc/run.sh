#!/bin/bash
# SBATCH job script — Chasing Pavements pipeline
#
# Usage:
#   sbatch hpc/run.sh kenya 2     # Kenya Phase 2
#   sbatch hpc/run.sh kenya 3     # Kenya Phase 3
#   sbatch hpc/run.sh kenya 4     # Kenya Phase 4
#   sbatch hpc/run.sh kenya 0     # Kenya all phases
#   sbatch hpc/run.sh tanzania 4  # Tanzania Phase 4
#   sbatch hpc/run.sh senegal 0   # Senegal all phases

#SBATCH --job-name=chasing
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64GB
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/%u/chasing_pavements/logs/job_%j_%x.out
#SBATCH --error=/scratch/%u/chasing_pavements/logs/job_%j_%x.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=%u@nyu.edu
#SBATCH --account=torch_pr_730_general

# ==============================================================================
# Parse arguments
# ==============================================================================
COUNTRY="$1"
PHASE="${2:-0}"

if [ -z "$COUNTRY" ]; then
    echo "Usage: sbatch hpc/run.sh <country> [phase]"
    echo "  country: tanzania, kenya, senegal, ethiopia, nigeria, uganda, ghana, mozambique"
    echo "  phase: 0=all, 1=roads, 2=trade costs, 3=calibration, 4=counterfactual"
    exit 1
fi

# ==============================================================================
# Environment
# ==============================================================================
PROJECT_DIR="/scratch/$USER/chasing_pavements"

echo "=========================================="
echo "Chasing Pavements: ${COUNTRY^^}"
echo "=========================================="
echo "Phase       : $PHASE"
echo "Project dir : $PROJECT_DIR"
echo "Job ID      : $SLURM_JOB_ID"
echo "=========================================="

module purge
module load anaconda3/2025.06
eval "$(conda shell.bash hook)"

# Create conda env if it doesn't exist
ENV_DIR="$PROJECT_DIR/chasing_env"
if [ ! -d "$ENV_DIR" ]; then
    echo "Creating conda environment..."
    conda create -p "$ENV_DIR" python=3.11 -y
    conda activate "$ENV_DIR"
    pip install -r "$PROJECT_DIR/requirements.txt"
    pip install pyyaml rasterstats wbgapi
else
    conda activate "$ENV_DIR"
fi

export PYTHONNOUSERSITE=True
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/data/raw"
mkdir -p "$PROJECT_DIR/data/processed"
mkdir -p "$PROJECT_DIR/outputs"

# ==============================================================================
# Run
# ==============================================================================
cd "$PROJECT_DIR"

CONFIG="configs/${COUNTRY}.yaml"
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config not found: $CONFIG"
    echo "Available configs:"
    ls configs/*.yaml 2>/dev/null
    exit 1
fi

echo "Running: python src/run_country.py $CONFIG --phase $PHASE"
python src/run_country.py "$CONFIG" --phase "$PHASE"

echo "Job completed!"
