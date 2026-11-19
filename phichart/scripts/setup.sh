#!/usr/bin/env bash
# One-time setup: Python deps, Phira source (TeamFlos/phira), build the headless renderer phira-snap.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PHIRA_DIR="${PHICHART_PHIRA_DIR:-$ROOT/third_party/phira}"
PHIRA_REV="${PHIRA_REV:-b96adc9d5c9aa27a35bf1e19b583a845b91be835}"   # tested commit (v0.8.3+)

echo "== system packages (Debian/Ubuntu) =="
if command -v apt-get >/dev/null; then
  SUDO=""; [ "$(id -u)" != 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq ffmpeg xvfb pkg-config \
    libwayland-dev libasound2-dev libx11-dev libxi-dev libgl1-mesa-dev libegl1-mesa-dev \
    libxkbcommon-dev libgtk-3-dev libxcursor-dev libxrandr-dev libgl1-mesa-dri >/dev/null
fi

echo "== rust toolchain =="
command -v cargo >/dev/null || { curl -sSf https://sh.rustup.rs | sh -s -- -y; source "$HOME/.cargo/env"; }

echo "== python package =="
python3 -m pip install -q -e "$ROOT"

echo "== Phira source -> $PHIRA_DIR =="
if [ ! -d "$PHIRA_DIR/.git" ]; then
  mkdir -p "$(dirname "$PHIRA_DIR")"
  git clone https://github.com/TeamFlos/phira.git "$PHIRA_DIR"
fi
git -C "$PHIRA_DIR" fetch -q origin "$PHIRA_REV" 2>/dev/null || true
git -C "$PHIRA_DIR" checkout -q "$PHIRA_REV" 2>/dev/null || echo "(could not pin $PHIRA_REV, using current checkout)"

echo "== build phira-snap (Phira's prpr engine, headless frame renderer) =="
rm -rf "$PHIRA_DIR/tools/phira-snap"
cp -r "$ROOT/engine/phira-snap" "$PHIRA_DIR/tools/phira-snap"
(cd "$PHIRA_DIR" && cargo build -p phira-snap --release)
echo "built: $PHIRA_DIR/target/release/phira-snap"
echo "done. try: phichart init song.mp3 --out work/song"
