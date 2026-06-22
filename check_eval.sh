#!/usr/bin/env bash
# Summarize one or more eval run logs, one line per file.
# Usage: ./check_eval.sh <log_file> [<log_file> ...]
#        ./check_eval.sh output_run*

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <log_file> [<log_file> ...]" >&2
  exit 1
fi

# Expand any quoted glob patterns (e.g. "output_run*") into matching files.
shopt -s nullglob
files=()
for arg in "$@"; do
  expanded=($arg)
  if [[ ${#expanded[@]} -eq 0 ]]; then
    files+=("$arg")  # keep literal argument so we can report "not found"
  else
    files+=("${expanded[@]}")
  fi
done
shopt -u nullglob

# Collect stats into an array of tab-separated lines for sorting.
rows=()

for log in "${files[@]}"; do
  if [[ ! -f "$log" ]]; then
    rows+=("n/a	n/a	n/a	n/a	n/a	n/a	n/a	NOT FOUND: $log")
    continue
  fi

  mtime=$(date -r "$log" '+%Y-%m-%d %H:%M' 2>/dev/null || stat -c '%y' "$log" 2>/dev/null | cut -d' ' -f1,2 | sed 's/:[0-9][0-9]\+\s*$//')

  model=$(grep -m1 '^Strategy:' "$log" 2>/dev/null | sed -E 's/^Strategy:.*model:[[:space:]]*//; s/[[:space:]]+$//' || true)
  [[ -z "$model" ]] && model="unknown"

  ok=$(grep -cE 'OK' "$log" 2>/dev/null || true)
  ok=${ok:-0}
  err=$(grep -cE 'ERR' "$log" 2>/dev/null || true)
  err=${err:-0}
  # Filter out rate-limit (429) errors — not real eval failures
  err429=$(grep -cE 'status_code: 429' "$log" 2>/dev/null || true)
  err429=${err429:-0}
  err=$((err - err429))
  # Count timeouts separately for visibility
  timeouts=$(grep -cE 'Timeout after' "$log" 2>/dev/null || true)
  timeouts=${timeouts:-0}
  run=$((ok + err))

  total=$(grep -m1 '^Running [0-9]\+ evals' "$log" 2>/dev/null | sed -E 's/^Running ([0-9]+) evals.*/\1/' || true)
  [[ -z "$total" ]] && total=$run

  if [[ $run -gt 0 ]]; then
    pct_num=$(awk -v ok="$ok" -v run="$run" 'BEGIN { printf "%.1f", (ok/run)*100 }')
    pct="${pct_num}%"
  else
    pct="n/a"
    pct_num="0"
  fi

  last_elapsed=$(grep 'elapsed' "$log" 2>/dev/null | tail -1 || true)
  if [[ -n "$last_elapsed" ]]; then
    elapsed_s=$(echo "$last_elapsed" | sed -E 's/.*\[([0-9]+)\/[0-9]+\][[:space:]]+([0-9]+)s elapsed.*/\2/')
  else
    summary_line=$(grep -A1 '^--- Summary ---$' "$log" 2>/dev/null | tail -1 || true)
    elapsed_s=""
    if [[ -n "$summary_line" ]]; then
      avg=$(echo "$summary_line" | grep -oE 'avg:[^[:space:]]+' | sed 's/avg://')
      if [[ -n "$avg" ]] && awk -v a="$avg" 'BEGIN { exit (a+0 == 0) }'; then
        elapsed_s=$(awk -v avg="$avg" -v total="$total" 'BEGIN { printf "%.0f", avg*total }')
      fi
    fi
  fi

  if [[ -n "$elapsed_s" && "$run" -gt 0 ]]; then
    avg_per=$(awk -v e="$elapsed_s" -v t="$run" 'BEGIN { printf "%.1fs", e/t }')
  else
    avg_per="n/a"
  fi

  rows+=("$pct_num	$mtime	$model	$pct	OK:$ok	ERR:$err	TMO:$timeouts	$avg_per	$log")
done

printf '%-16s  %-34s  %-7s  %-7s  %-7s  %-7s  %-12s  %s\n' \
  "DATE/TIME" "MODEL" "PCT" "OK" "ERR" "TMO" "AVG/SCEN" "FILE"

while IFS=$'\t' read -r _ mtime model pct ok err tmo avg_per log; do
  printf '%-16s  %-34s  %-7s  %-7s  %-7s  %-7s  %-12s  %s\n' \
    "$mtime" "$model" "$pct" "$ok" "$err" "$tmo" "$avg_per" "$log"
done < <(printf '%s\n' "${rows[@]}" | sort -t$'\t' -k1,1 -nr)
