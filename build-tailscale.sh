#!/usr/bin/env bash
# Build the upstream Go userspace client as an Android library, without Android Studio UI.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f /opt/pocket-ledger/toolchain/env.sh ]]; then source /opt/pocket-ledger/toolchain/env.sh; fi
: "${ANDROID_HOME:=/opt/android-sdk}"
export ANDROID_HOME
mkdir -p build/tailscale
cd mobiletailscale
gomobile bind -target=android/arm64,android/amd64 -androidapi 26 -ldflags='-s -w' -o ../build/tailscale/mobile.aar .
cd ..
python3 scripts/tailscale-notices.py
