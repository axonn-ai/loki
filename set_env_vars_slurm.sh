#!/bin/bash
# select_gpu_device wrapper script
export RANK=${SLURM_PROCID}
export WORLD_SIZE=${SLURM_NTASKS}
export LOCAL_RANK=${SLURM_LOCALID}
exec $*
