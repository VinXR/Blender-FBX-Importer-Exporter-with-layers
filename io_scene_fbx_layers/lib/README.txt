Native libraries used by the default "FBX + Layers" import to read FBX Display Layers:

  fbxl_ufbx_windows_x64.dll   Windows x64
  fbxl_ufbx_linux_x64.so      Linux x64
  fbxl_ufbx_macos.dylib       macOS (arm64 + x86_64)

They are built from native/fbxl_ufbx.c (GPL-2.0-or-later) and ufbx (native/ufbx/, MIT license, see
LICENSE-ufbx.txt in this folder). The complete source code for each release is available at the same version tag of:

  https://github.com/VinXR/Blender-FBX-Importer-Exporter-with-layers

ufbx - Single source file FBX loader, Copyright (c) 2020 Samuli Raivio, https://github.com/ufbx/ufbx
