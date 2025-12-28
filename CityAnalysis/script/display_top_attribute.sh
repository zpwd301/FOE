#!/usr/bin/env bash
set -euo pipefail

DIR="$HOME/Documents/FOE/CityAnalysis/input"

# Find the most recently saved city JSON file
latest_file=$(ls -t "$DIR"/city_*.json | head -n 1)

if [ ! -f "$latest_file" ]; then
  echo "No city JSON file found in $DIR" >&2
  exit 1
fi

echo "Inspecting: $latest_file"
echo

# Show top 3 levels of attributes
jq 'paths | select(length <= 3) | join(".")' "$latest_file" | sort -u
