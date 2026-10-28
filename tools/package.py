# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

"""
Build dist/io_scene_fbx_layers-<version>.zip, the installable Blender extension, from io_scene_fbx_layers/.
Plain zip (no Blender needed, so it also runs in CI). With --all-platforms it fails unless the ufbx library is
present for every supported platform.
"""

import argparse
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "io_scene_fbx_layers")
LIBS = ("fbxl_ufbx_windows_x64.dll", "fbxl_ufbx_linux_x64.so", "fbxl_ufbx_macos.dylib")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-platforms", action="store_true", help="require the library for every platform")
    args = parser.parse_args()

    with open(os.path.join(ADDON, "blender_manifest.toml"), encoding="utf-8") as f:
        version = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.MULTILINE).group(1)

    present = [lib for lib in LIBS if os.path.isfile(os.path.join(ADDON, "lib", lib))]
    missing = [lib for lib in LIBS if lib not in present]
    if missing:
        print("Missing ufbx libraries: " + ", ".join(missing))
        if args.all_platforms:
            sys.exit(1)

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "io_scene_fbx_layers-{:s}.zip".format(version))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ADDON):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in sorted(filenames):
                if filename.endswith(".pyc"):
                    continue
                path = os.path.join(dirpath, filename)
                zf.write(path, os.path.relpath(path, ADDON).replace(os.sep, "/"))
    print("Created {:s} (libraries: {:s})".format(out, ", ".join(present) or "none"))


if __name__ == "__main__":
    main()
