#!/bin/bash
# Runs N seeded auto-play sessions on the currently booted emulator.
# Usage: run_sessions.sh <api_label> <sessions> <steps> <base_seed> <outdir>
set -u
API="${1:-unknown}"
SESSIONS="${2:-20}"
STEPS="${3:-150}"
BASE="${4:-1000}"
OUT="${5:-artifacts/api$API}"
mkdir -p "$OUT"
for i in $(seq 1 "$SESSIONS"); do
  SEED=$((BASE + i))
  SDIR="$OUT/s$SEED"
  mkdir -p "$SDIR"
  adb logcat -c 2>/dev/null
  # hard cap: ~8s per step worst case plus margin
  timeout $((STEPS * 8 + 300)) python3 "$(dirname "$0")/driver.py" \
      --seed "$SEED" --steps "$STEPS" --out "$SDIR" \
      > "$SDIR/events.jsonl" 2> "$SDIR/driver.err"
  adb logcat -d > "$SDIR/logcat.txt" 2>/dev/null
  # stop the app between sessions so each seed starts clean
  adb shell am force-stop com.superover.cricket 2>/dev/null
  sleep 2
done
python3 "$(dirname "$0")/summarize.py" "$OUT" > "$OUT/summary.md"
echo "done: $OUT"
