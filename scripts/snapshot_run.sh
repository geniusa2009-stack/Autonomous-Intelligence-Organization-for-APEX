#!/bin/bash
# Run an evaluation from a FROZEN code snapshot, so edits to the working tree never change a running benchmark.
#   git worktree add --detach var/run-snapshot/<commit> <commit>
#   scripts/snapshot_run.sh <commit> scripts/validation_queue.py --max-steps 1
# Data, model weights and artifacts are shared with the main tree (APEX_HOME); code and config come from the
# snapshot; every queue step records the snapshot commit (APEX_RUN_COMMIT).
MAIN=$(cd "$(dirname "$0")/.." && pwd)
SNAP=$MAIN/var/run-snapshot/$1; shift
cd "$SNAP" || exit 2
export APEX_HOME=$MAIN APEX_CONFIG_DIR=$SNAP/config PYTHONPATH=$SNAP APEX_RUN_COMMIT=$(git -C "$SNAP" rev-parse --short HEAD)
exec "$MAIN/.venv/bin/python" "$@"
