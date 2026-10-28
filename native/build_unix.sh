#!/bin/sh
# Build the ufbx layer reader for Linux (x64) or macOS (universal arm64 + x86_64).
set -e
cd "$(dirname "$0")"
OUT=../io_scene_fbx_layers/lib
mkdir -p "$OUT"
case "$(uname -s)" in
  Darwin)
    cc -O2 -shared -fvisibility=hidden -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 \
      -o "$OUT/fbxl_ufbx_macos.dylib" fbxl_ufbx.c ufbx/ufbx.c -lm
    ;;
  Linux)
    cc -O2 -shared -fPIC -fvisibility=hidden -o "$OUT/fbxl_ufbx_linux_x64.so" fbxl_ufbx.c ufbx/ufbx.c -lm
    ;;
  *)
    echo "Unsupported platform: $(uname -s)" >&2
    exit 1
    ;;
esac
