#!/usr/bin/env bash
set -euo pipefail

DIR="$HOME/Documents/FOE/CityAnalysis/input"
if [ ! -d "$DIR" ]; then
  mkdir -p "$DIR"
fi

today="$(date +%Y-%m-%d)"
base="$DIR/city_${today}.json"
file="$base"

# If file exists, add numeric suffix
count=1
while [ -e "$file" ]; do
  file="$DIR/city_${today}_$count.json"
  count=$((count + 1))
done

# Save clipboard to file
pbpaste > "$file"

# Remove possible UTF-8 BOM
LC_ALL=C sed -i '' $'1s/^\xEF\xBB\xBF//' "$file"

# Validate & prettify JSON with jq
if jq empty "$file" 2>/dev/null; then
  tmp="$(mktemp)"
  jq . "$file" > "$tmp" && mv "$tmp" "$file"
  echo "Saved and prettified: $file"
else
  echo "Warning: clipboard does not contain valid JSON. Saved as-is: $file" >&2
  exit 1
fi
