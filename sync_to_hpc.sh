#!/usr/bin/env bash
# Sync code, configs, and raw data to HPC.
# Usage: ./sync_to_hpc.sh
#
# First time: also download OSM PBFs and GADM data on the HPC itself
# (faster than transferring 700MB+ files over SSH).

HPC="torch"
HPC_ROOT="/scratch/ob708/chasing_pavements"

echo "Syncing code and configs to HPC..."
rsync -avz --progress \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='data/raw/*.osm.pbf' \
  --exclude='data/raw/*.tif' \
  --exclude='data/raw/bfi_gdp_025deg/' \
  --exclude='data/processed/*.gpkg' \
  --exclude='data/processed/*.npy' \
  --exclude='notebooks/' \
  --exclude='*.pdf' \
  --exclude='*.docx' \
  ./ "${HPC}:${HPC_ROOT}/"

echo ""
echo "Done syncing code."
echo ""
echo "NEXT STEPS on the HPC:"
echo "  1. ssh torch"
echo "  2. cd /scratch/ob708/chasing_pavements"
echo "  3. Download data (first time only):"
echo "     curl -L -o data/raw/kenya-latest.osm.pbf https://download.geofabrik.de/africa/kenya-latest.osm.pbf"
echo "     curl -L -o data/raw/gadm41_KEN.gpkg https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_KEN.gpkg"
echo "     curl -L -o data/raw/ken_ppp_2019.tif https://data.worldpop.org/GIS/Population/Global_2000_2020/2019/KEN/ken_ppp_2019.tif"
echo "  4. Copy BFI GDP data: rsync -avz data/raw/bfi_gdp_025deg/ torch:${HPC_ROOT}/data/raw/bfi_gdp_025deg/"
echo "  5. Submit job: sbatch hpc/run.sh kenya 0"
