#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
JDK=/opt/android-studio/jbr
SDK=/opt/android-sdk
OUT="$PWD/build/update-test"
SERIAL="${ANDROID_SERIAL:-648718eb}"
mkdir -p "$OUT/classes" "$OUT/dex"
"$JDK/bin/javac" -source 17 -target 17 -classpath "$SDK/platforms/android-36/android.jar:build/direct/classes:app/libs/*" -d "$OUT/classes" tests/ReleaseUpdaterTest.java
"$JDK/bin/jar" cf "$OUT/test.jar" -C "$OUT/classes" .
JAVA_HOME="$JDK" "$SDK/build-tools/36.0.0/d8" --lib "$SDK/platforms/android-36/android.jar" --min-api 26 --output "$OUT/dex" "$OUT/test.jar"
trap 'adb -s "$SERIAL" shell rm -f /data/local/tmp/ledger-update-test.dex >/dev/null' EXIT
adb -s "$SERIAL" push "$OUT/dex/classes.dex" /data/local/tmp/ledger-update-test.dex >/dev/null
APP_PATH=$(adb -s "$SERIAL" shell pm path cn.guga.ledger | tr -d '\r' | sed 's/^package://')
adb -s "$SERIAL" shell "CLASSPATH=$APP_PATH:/data/local/tmp/ledger-update-test.dex app_process /system/bin dev.guga.updates.ReleaseUpdaterTest"
