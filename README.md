# FBX + Layers for Blender

FBX import and export for Blender with support for **FBX Display Layers**, the layers you get from 3ds Max, Maya and other apps built on the Autodesk FBX SDK.

- **Import:** the file is imported by **Blender's own FBX importer**, the C++ one built on [ufbx](https://github.com/ufbx/ufbx). Each Display Layer then becomes a **Collection** holding the layer's objects, with the layer's color, visibility and freeze state.
- **Export:** a fork of Blender's FBX exporter (`io_scene_fbx` 5.15.0) writes collections as Display Layers, with color, visibility and freeze. Max, Maya and other FBX SDK based apps read them back as layers.
- **Also on export:**
  - Textures are copied next to the FBX by default, with relative paths, including packed images.
  - Instances, i.e. objects sharing a mesh, stay instances.

It installs **alongside** Blender's built-in FBX support and does not replace it.

## Contents

- [Installation](#installation)
- [Usage](#usage)
- [How the import works](#how-the-import-works)
- [How layers are mapped](#how-layers-are-mapped)
- [Textures](#textures)
- [Instances](#instances)
- [Known limitations](#known-limitations)
- [Development](#development)
- [Credits and licenses](#credits-and-licenses)

## Installation

1. Download `io_scene_fbx_layers-<version>.zip` from the [Releases](https://github.com/VinXR/Blender-FBX-Importer-Exporter-with-layers/releases) page.
2. In Blender, open **Edit → Preferences → Get Extensions**, then choose **▾ → Install from Disk…** and select the zip.

Requires Blender **5.1** or newer (tested on 5.1 and 5.2).

Platforms:

- Windows x64
- Linux x64
- macOS (Apple Silicon and Intel)

On other platforms only the *Legacy* import is available (see [Usage](#usage)).

**Updating:** install the new zip the same way, then **restart Blender**. Blender keeps the add-on's old modules and library loaded until it restarts. If several Blender windows are open, restart all of them.

## Usage

| Menu entry | What it does |
|---|---|
| **File → Import → FBX + Layers (.fbx)** | Blender's C++ importer, plus Display Layers → collections. **Recommended.** |
| **File → Import → FBX + Layers (.fbx) (Legacy)** | Fork of Blender's Python importer, which Blender lists as "FBX (.fbx) (Legacy)", plus Display Layers → collections. Kept as a fallback while Blender still ships it. |
| **File → Export → FBX + Layers (.fbx)** | Fork of Blender's FBX exporter, plus collections → Display Layers. |

- The import options are **the same as Blender's own "FBX (.fbx)" importer**. They are read from the running Blender, so they follow Blender updates automatically.
- The export options are those of Blender's exporter. The only different default is **Path Mode = Copy** (see [Textures](#textures)).

## How the import works

1. The file is read with **ufbx 0.20.0**, the same version Blender 5.1/5.2 ships, with the same load options as Blender's importer. This gives the nodes and their Display Layers (name, members, color, visibility, freeze). ufbx runs from a small native library included in the extension, through Python `ctypes`.
2. **Blender's C++ importer** (`bpy.ops.wm.fbx_import`) imports the file with the options chosen in the dialog.
3. Each layer member is matched to the object Blender created for it. Blender keeps no FBX id on imported objects, so the match uses:
   - the **name**, ignoring the `.001`-style suffix Blender adds on clashes;
   - for nodes sharing a name, the **world position**;
   - then the **creation order**, which is how Blender numbers duplicates.

   This also works with duplicate node names in the file and with names that already exist in the scene. Layer members that cannot be matched are listed in a warning.
4. One collection per layer is created and the matched objects are moved into it (see [Layer properties](#layer-properties)).

**Why not just the Legacy importer?** It is the old Python importer, which Blender has marked "Legacy" since 5.0 and will likely remove. Building on Blender's C++ importer and on the same ufbx version keeps this add-on aligned with Blender and ufbx updates. It also brings what the C++ importer does better:

| | FBX + Layers (default) | FBX + Layers (Legacy) |
|---|---|---|
| Display Layers → collections | ✅ | ✅ |
| Instances (shared meshes, per-object materials) | ✅ | ✅ |
| Import speed on large files | fast (C++) | slower (Python) |
| ASCII FBX files | ✅ | ❌ |
| FBX older than 7.1 (version < 7100) | ✅ | ❌ |
| Needs the native ufbx library | yes | no |

## How layers are mapped

### Import

- For every Display Layer in the file, a collection with the layer's name is created as a child of the active collection, and the layer's objects are moved into it.
- Objects that are not in a layer stay in the active collection, as with Blender's importer.
- A layer with no importable objects still creates an (empty) collection.
- Bones inside a layer are ignored, because a bone is not an object in Blender and cannot belong to a collection. The armature stays where the importer puts it.
- When Blender adds a `<name>_GeomAdjust` helper object for a node's geometry transform, the helper goes into the same collection as the node.
- If a collection with the same name already exists, a new one is created anyway (Blender names it `.001`), the same way imported objects are renamed.

### Export

An FBX object can be in at most one Display Layer (FBX layers are "exclusive" collections), while a Blender object can be linked to several collections. Each exported object therefore gets the layer of its **first** collection, using these rules:

- "First" is the first place the object appears in the **Outliner** (View Layer mode), going depth first.
  - Child collections come before the collection's own objects, as in the Outliner.
  - The order in which the object was linked does not matter.
  - Reordering collections in the Outliner can change the layer of an object that is in more than one collection.
- Nested collections are flattened. The layer is named after the collection that directly contains the object; parent collections do not become layers.
- Objects linked only to the **Scene Collection** get no layer.
- Objects in Blender's default "Collection" get a layer called "Collection".
- Instances (collection instances, duplis) get the layer of the object that instances them.
- Only collections with at least one exported object are written. The usual export filters still apply: selected only, visible only, active collection, batch mode, and so on.

### Layer properties

| FBX layer | Blender collection |
|---|---|
| **Color** | Collection **color tag**. Blender only has 8 theme colors, so the closest one is used, and the FBX default grey means no tag. The exact RGB is kept in the collection custom property `fbx_layer_color`, shown as a color in *Collection Properties → Custom Properties*. |
| **Show** = off | Collection hidden in the view layer (eye icon in the Outliner). |
| **Freeze** = on | Collection not selectable. |
| LODBox | Ignored. |

On export:

- **Color**
  - If the collection still has the tag it got on import, the exact `fbx_layer_color` is written.
  - If you changed the tag in Blender, or set one yourself, the theme color of that tag is written.
  - With no tag, the default grey is written.
- **Show** is off when the collection is hidden in the exported view layer (eye icon) or disabled in viewports (monitor icon).
- **Freeze** is on when the collection is not selectable.
- Layers with default values (grey, visible, not frozen) are written without properties, exactly as Maya and Max write them.

The layer color only changes the collection's color tag. Object display colors are not changed.

## Textures

- **Path Mode** defaults to **Copy**: textures are copied into the **same folder as the `.fbx`** and referenced with relative paths (just the file name).
  - Blender's exporter defaults to *Auto* and, in *Copy* mode, puts textures in a `<name>.fbm` subfolder.
- **Packed images** are written from their packed data.
  - This covers textures that came from an FBX with embedded media: Blender keeps those images packed, with a path to a folder that does not exist.
  - Blender's exporter skips these with "missing …, not copying".
- **Embed Textures** still works as before: the textures go inside the FBX.

## Instances

In FBX, objects that share a mesh are one Geometry connected to several nodes, and **materials belong to the node**, not to the geometry.

- **Import:** both import entries keep instances as one shared mesh, with per-object materials where they differ.
- **Export:** objects that share a mesh keep sharing one FBX Geometry, **even when they use different Object-linked materials**.
  - The mesh is only duplicated when the objects' material slot layouts are incompatible: slot *N* has to give the same FBX material index for every object. For example, a two-slot mesh where one object uses two different materials and another object uses the same material twice cannot be shared.
  - Blender's exporter instead duplicates the mesh for every object with Object-linked materials, so instances coming from Max or Maya are exported as separate meshes.

## Known limitations

- **Import (default entry)**
  - Layer members are matched to imported objects by name, position and order, because Blender keeps no FBX id on objects. Ambiguous cases, such as nodes with the same name at the same position, could be swapped. Members that cannot be matched are reported.
  - It needs the bundled native library. On unsupported platforms, use the Legacy entry.
- **Import (Legacy entry)**
  - No ASCII FBX and no FBX older than 7.1.
  - Slower on large files.
- Bones inside a layer are ignored on import and never get a layer on export.
- An object in several collections is exported in one layer only (the first, see [Export](#export)).
- Collection color tags are an approximation of the layer color. The exact color survives a round trip only while the tag is not changed.
- Show maps to the eye icon of the view layer used for import/export. Other view layers are not touched.
- A packed image with no file path at all (e.g. a texture painted in Blender and never saved) may be written without a file extension.
- Export is always binary FBX 7.4, as with Blender's exporter.
- Drag and drop of `.fbx` files is not handled; it stays with Blender's own importer.
- Tested on Blender 5.1 and 5.2 only.

Exported layers have been verified with the **Autodesk FBX SDK 2020.3.11**, the library behind the Max and Maya FBX plug-ins.

The SDK silently drops any layer object that is written without an (empty) child block. This add-on writes it the same way the SDK does.

## Development

### Layout

| Path | What |
|---|---|
| `io_scene_fbx_layers/` | The extension. |
| `io_scene_fbx_layers/import_cpp.py` | Default import: wraps `wm.fbx_import`, mirrors its options. |
| `io_scene_fbx_layers/ufbx_reader.py` | Loads the native library with `ctypes` and reads nodes and layers. |
| `io_scene_fbx_layers/layers.py` | Layer ↔ collection logic for import (both entries) and export. |
| other `io_scene_fbx_layers/*.py` | Fork of Blender's `io_scene_fbx` 5.15.0. Every change is marked `# FBX-LAYERS begin` / `# FBX-LAYERS end`. The first commit of this repository is the unmodified add-on, to diff against. |
| `native/fbxl_ufbx.c` | Small C layer over ufbx: loads a file with Blender's options and returns nodes and layers as JSON. |
| `native/ufbx/` | ufbx, a verbatim copy of Blender's `extern/ufbx` (see `README.blender` for the version). |

### Keeping up with Blender

- **When Blender updates ufbx:**
  1. Copy the new files from Blender's `extern/ufbx` into `native/ufbx/`.
  2. Check that the load options in `native/fbxl_ufbx.c` still match `source/blender/io/fbx/importer/fbx_import.cc`.
  3. Rebuild and run the tests.
- **When Blender changes the importer's options:** nothing to do, they are mirrored at runtime.
- **When Blender changes the Python exporter:** copy the new add-on files and re-apply the marked `FBX-LAYERS` blocks.

### Building the native library

- **Windows** (Visual Studio 2022, x64): `native\build_windows.bat`
- **Linux / macOS:** `sh native/build_unix.sh`. macOS builds a universal arm64 + x86_64 library.

The library goes into `io_scene_fbx_layers/lib/`.

[GitHub Actions](.github/workflows/build.yml) builds all platforms on every push. Linux builds in a manylinux_2_28 container, so the library loads on older distributions. On a `v*` tag, the workflow attaches the packaged zip to the release.

### Tests

```
blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
```

Import tests run with **both** import entries. The tests cover:

- layer export rules;
- export → import round trips;
- layer color, visibility and freeze;
- duplicate node names and names that already exist in the scene;
- texture copying, including packed images;
- instances;
- an ASCII FBX file (`tests/data/layers_ascii.fbx`, converted with the Autodesk FBX SDK);
- the same FBX content as Blender's exporter once the layer data is stripped.

Import tests against real third-party files run only if you drop FBX files that contain Display Layers into `tests/samples/`. None are distributed.

### Packaging

```
python tools/package.py
```

This writes `dist/io_scene_fbx_layers-<version>.zip` with the libraries present in `lib/`. `--all-platforms` makes it fail if any library is missing.

## Credits and licenses

This add-on builds on the work of others:

- **Blender's FBX add-on** (`io_scene_fbx`) by the Blender Foundation.
  - Original authors: Campbell Barton, Bastien Montagne, Jens Restemeier and @Mysteryem.
  - The importer and exporter in this repository are a fork of it.
  - License: GPL-2.0-or-later.
- **[ufbx](https://github.com/ufbx/ufbx)** by Samuli Raivio, the FBX loader used by Blender's C++ importer and by this add-on to read Display Layers.
  - License: dual MIT / public domain (Unlicense). It is used here under the MIT license, as Blender does.
  - `native/ufbx/` is an unmodified copy of the version Blender ships.
  - Its license text is in `native/ufbx/LICENSE` and, in the distributed extension, in `lib/LICENSE-ufbx.txt`.
- **Blender's C++ FBX importer**: the ufbx load options in `native/fbxl_ufbx.c` are taken from Blender's `source/blender/io/fbx/importer/fbx_import.cc`, so that ufbx sees the same nodes as Blender does.

The add-on as a whole is licensed **GPL-2.0-or-later** (see [`LICENSE`](LICENSE)), the license of the code it is based on.

- The native libraries in the release zip are built from `native/`.
- The complete source of every release is in this repository at the matching version tag (see `lib/README.txt` in the extension).

This project is not affiliated with or endorsed by the Blender Foundation or Autodesk. Blender is a trademark of the Blender Foundation; FBX, 3ds Max and Maya are trademarks of Autodesk, Inc.
