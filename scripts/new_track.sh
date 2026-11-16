#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-}"
if [[ -z "$NAME" ]]; then
  echo "Usage: make new-track NAME=my_sound"
  exit 1
fi

DIR="music/$NAME"
CFG="$DIR/config.yaml"

mkdir -p "$DIR"
if [[ -f "$CFG" ]]; then
  echo "Already exists: $CFG"
  exit 1
fi

cat > "$CFG" <<EOF
# Per-track config (this folder = one sound).
# Put the mp3 next to this file — all tracks under music/ are active automatically.
file: ${NAME}.mp3
cooldown_seconds: 5

phrases:
  - example phrase
  - example phrase alias

model:
  path: model
  sample_rate: 16000
  # Extra grammar entries (in addition to phrases + [unk])
  grammar_extra:
    - example phrase
  # ASR substitutions applied before matching (src -> dst)
  normalize:
    did not: dont
    do not: dont
    didnt: dont
  # Fuzzy match: each rule is a list of groups; every group must match (any option in group).
  fuzzy:
    - [[example], [phrase]]
EOF

echo "Created $CFG"
echo "Next: add $DIR/${NAME}.mp3 (bot loads every music/*/config.yaml)"
