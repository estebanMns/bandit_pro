#!/usr/bin/env bash
# Genera las carpetas nativas de Android e iOS que faltan, sin tocar lib/, el AndroidManifest
# ni el Info.plist del repositorio (flutter create no sobrescribe archivos existentes).
set -euo pipefail
cd "$(dirname "$0")"

command -v flutter >/dev/null || { echo "Instala Flutter 3.24 o superior: https://docs.flutter.dev/get-started/install"; exit 1; }

flutter create --project-name bandit_mobile_camera --org co.bandit --platforms=android,ios .
# La prueba de ejemplo de flutter create usa un contador que esta app no tiene.
if grep -q "MyApp" test/widget_test.dart 2>/dev/null; then rm test/widget_test.dart; fi
flutter pub get

# Android: flutter_webrtc y mobile_scanner necesitan minSdk 23 o superior.
for gradle in android/app/build.gradle.kts android/app/build.gradle; do
    if [[ -f "$gradle" ]]; then
        sed -i.bak -E 's/minSdk( =|) .*/minSdk\1 23/' "$gradle" && rm -f "$gradle.bak"
    fi
done

cat <<'MSG'

Listo. Pasos manuales que quedan (ver README.md):
  * iOS: en ios/Podfile fija `platform :ios, '15.0'` y activa PERMISSION_CAMERA=1 y
    PERMISSION_MICROPHONE=1 de permission_handler; luego `cd ios && pod install`.
  * Prueba en dispositivos físicos: los simuladores no tienen cámara real.
MSG
