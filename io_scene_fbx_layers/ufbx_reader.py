# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

# FBX-LAYERS: reads FBX nodes and Display Layers with ufbx (same version and load options as Blender's C++ importer),
# through the small C library in native/fbxl_ufbx.c, built per platform into lib/.

import ctypes
import json
import os
import platform
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
_lib = None


class UfbxError(Exception):
    pass


def _lib_filename():
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        return "fbxl_ufbx_macos.dylib"  # Universal arm64 + x86_64.
    if machine not in {"amd64", "x86_64"}:
        return None
    if sys.platform == "win32":
        return "fbxl_ufbx_windows_x64.dll"
    if sys.platform.startswith("linux"):
        return "fbxl_ufbx_linux_x64.so"
    return None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    filename = _lib_filename()
    path = os.path.join(_LIB_DIR, filename) if filename else None
    if path is None or not os.path.isfile(path):
        raise UfbxError("ufbx library not available for this platform ({:s} {:s})".format(
            sys.platform, platform.machine()))
    lib = ctypes.CDLL(path)
    lib.fbxl_read_scene.argtypes = (ctypes.c_char_p, ctypes.c_double, ctypes.c_char_p, ctypes.c_int)
    lib.fbxl_read_scene.restype = ctypes.c_void_p
    lib.fbxl_free.argtypes = (ctypes.c_void_p,)
    lib.fbxl_free.restype = None
    lib.fbxl_ufbx_version.argtypes = ()
    lib.fbxl_ufbx_version.restype = ctypes.c_char_p
    _lib = lib
    return lib


def is_available():
    try:
        _load()
    except (UfbxError, OSError):
        return False
    return True


def ufbx_version():
    return _load().fbxl_ufbx_version().decode()


def read_scene(filepath, global_scale=1.0):
    """
    Return {"nodes": [...], "layers": [...]} (see native/fbxl_ufbx.c), node indices being positions in "nodes".
    Raise UfbxError if the library is missing or the file cannot be loaded.
    """
    lib = _load()
    err = ctypes.create_string_buffer(1024)
    ptr = lib.fbxl_read_scene(os.fsencode(filepath) if sys.platform != "win32" else filepath.encode("utf-8"),
                              global_scale, err, len(err))
    if not ptr:
        raise UfbxError(err.value.decode("utf-8", "replace") or "Unknown ufbx error")
    try:
        return json.loads(ctypes.string_at(ptr).decode("utf-8"))
    finally:
        lib.fbxl_free(ptr)
