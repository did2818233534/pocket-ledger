#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
SDK=/opt/android-sdk
JDK=/opt/android-studio/jbr
OUT="$PWD/build/db-test"
mkdir -p "$OUT/classes/cn/guga/ledger" "$OUT/dex"
"$JDK/bin/javac" -source 17 -target 17 -classpath "$SDK/platforms/android-36/android.jar:$PWD/build/direct/classes" -d "$OUT/classes" tests/LedgerDbTest.java
cp build/direct/classes/cn/guga/ledger/AvatarCodec.class build/direct/classes/cn/guga/ledger/LedgerDb.class "$OUT/classes/cn/guga/ledger/"
"$JDK/bin/jar" cf "$OUT/test.jar" -C "$OUT/classes" .
JAVA_HOME="$JDK" "$SDK/build-tools/36.0.0/d8" --lib "$SDK/platforms/android-36/android.jar" --min-api 26 --output "$OUT/dex" "$OUT/test.jar"
SERIAL="${ANDROID_SERIAL:-648718eb}"
trap 'adb -s "$SERIAL" shell rm -f /data/local/tmp/pocket-ledger-db-test.dex /data/local/tmp/pocket-ledger-isolated-test.db /data/local/tmp/pocket-ledger-isolated-test.db-wal /data/local/tmp/pocket-ledger-isolated-test.db-shm /data/local/tmp/pocket-ledger-isolated-test.db-journal >/dev/null' EXIT
adb -s "$SERIAL" push "$OUT/dex/classes.dex" /data/local/tmp/pocket-ledger-db-test.dex >/dev/null
adb -s "$SERIAL" shell 'CLASSPATH=/data/local/tmp/pocket-ledger-db-test.dex app_process /system/bin cn.guga.ledger.LedgerDbTest'
