#!/usr/bin/env bash
# Připraví binárky firmwaru pro nahrávání z prohlížeče (ESP Web Tools).
# Použití:  firmware/scripts/web_flash_bundle.sh <cílová složka>
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-../app/firmware}"
pio run -e laserplan
mkdir -p "$OUT"
B=.pio/build/laserplan
cp "$B/bootloader.bin" "$B/partitions.bin" "$B/firmware.bin" "$OUT/"
cp "$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin" "$OUT/"
VER=$(grep -oP 'LP_FW_VERSION "\K[^"]+' include/config.h)
cat > "$OUT/manifest.json" <<JSON
{
  "name": "LaserPlan",
  "version": "$VER",
  "new_install_prompt_erase": true,
  "builds": [
    {
      "chipFamily": "ESP32-C3",
      "parts": [
        { "path": "bootloader.bin", "offset": 0 },
        { "path": "partitions.bin", "offset": 32768 },
        { "path": "boot_app0.bin", "offset": 57344 },
        { "path": "firmware.bin", "offset": 65536 }
      ]
    }
  ]
}
JSON
echo "Hotovo: $OUT"
