#!/usr/bin/env bash
# Build Java/assets plus the generated Tailscale AAR using the existing Android SDK.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
SDK="${ANDROID_HOME:-/opt/android-sdk}"
TOOLS="$SDK/build-tools/36.0.0"
JDK="${JAVA_HOME:-/opt/android-studio/jbr}"
BUILD="$PWD/build/direct"
if [[ ! -f build/tailscale/mobile.aar ]] || [[ -n "$(find mobiletailscale -type f -newer build/tailscale/mobile.aar -print -quit 2>/dev/null)" ]]; then
    bash build-tailscale.sh
fi
rm -rf "$BUILD/classes" "$BUILD/dex" "$BUILD/mobile"
mkdir -p "$BUILD/gen" "$BUILD/classes" "$BUILD/dex" "$BUILD/mobile" dist
unzip -q -o build/tailscale/mobile.aar -d "$BUILD/mobile"
"$TOOLS/aapt2" compile --dir app/src/main/res -o "$BUILD/resources.zip"
sed 's/<manifest /<manifest package="cn.guga.ledger" /' app/src/main/AndroidManifest.xml > "$BUILD/AndroidManifest.xml"
"$TOOLS/aapt2" link -I "$SDK/platforms/android-36/android.jar" \
  --manifest "$BUILD/AndroidManifest.xml" --rename-manifest-package cn.guga.ledger \
  --min-sdk-version 26 --target-sdk-version 36 --version-code 2 --version-name 1.1.0 \
  --debug-mode --java "$BUILD/gen" -A app/src/main/assets \
  -o "$BUILD/resources.apk" "$BUILD/resources.zip"
find app/src/main/java "$BUILD/gen" -name '*.java' > "$BUILD/sources.txt"
"$JDK/bin/javac" -source 17 -target 17 -encoding UTF-8 \
  -classpath "$SDK/platforms/android-36/android.jar:$BUILD/mobile/classes.jar" -d "$BUILD/classes" @"$BUILD/sources.txt"
"$JDK/bin/jar" cf "$BUILD/classes.jar" -C "$BUILD/classes" .
JAVA_HOME="$JDK" "$TOOLS/d8" --lib "$SDK/platforms/android-36/android.jar" \
  --min-api 26 --output "$BUILD/dex" "$BUILD/classes.jar" "$BUILD/mobile/classes.jar"
cp "$BUILD/resources.apk" "$BUILD/unsigned.apk"
(cd "$BUILD/dex" && zip -q "$BUILD/unsigned.apk" classes*.dex)
mkdir -p "$BUILD/native/lib"
cp -r "$BUILD/mobile/jni/"* "$BUILD/native/lib/"
(cd "$BUILD/native" && zip -q -r "$BUILD/unsigned.apk" lib)
"$TOOLS/zipalign" -f -P 16 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"
JAVA_HOME="$JDK" "$TOOLS/apksigner" sign --ks /opt/android-user/debug.keystore \
  --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android \
  --out "$PWD/dist/小账-1.1.0.apk" "$BUILD/aligned.apk"
JAVA_HOME="$JDK" "$TOOLS/apksigner" verify "$PWD/dist/小账-1.1.0.apk"
printf 'APK: %s/dist/小账-1.1.0.apk\n' "$PWD"
