#!/bin/bash
# Half-suite regression with a tight pruner (1-min age, 5s loop);
# log lives in the workspace so a /tmp wipe cannot lose the result.
cd ~/workspace/projects/autonomus-ai-os/backend || exit 1
LOG=~/workspace/projects/autonomus-ai-os/docs/p16/run-logs/half2.log
BASE=/tmp/p16-basetemp
rm -rf "$BASE"; mkdir -p "$BASE"
( while true; do
    find "$BASE" -mindepth 1 -maxdepth 1 -type d -mmin +1 -exec rm -rf {} + 2>/dev/null
    sleep 5
  done ) &
PRUNER=$!
.venv/bin/python -m pytest "$@" -q -p no:cacheprovider --basetemp="$BASE" > "$LOG" 2>&1
CODE=$?
kill $PRUNER 2>/dev/null
wait $PRUNER 2>/dev/null
echo "pytest exit: $CODE"
grep -E "passed|failed" "$LOG" | tail -1
