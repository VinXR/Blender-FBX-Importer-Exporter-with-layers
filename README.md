# FBX + Layers for Blender

A fork of Blender's bundled FBX add-on (`io_scene_fbx` 5.15.0, Blender 5.1) that adds support for **FBX Display Layers**, the layers you get from 3ds Max, Maya and other apps built on the Autodesk FBX SDK.

- **Import:** each Display Layer becomes a Blender **Collection** that holds the layer's objects. The layer's color, visibility and freeze state are applied to the collection.
- **Export:** collections are written as Display Layers, with color, visibility and freeze. Max, Maya and other FBX SDK based apps read them back as layers.
- **Also on export:**
  - Textures are copied next to the FBX by default, with relative paths, including packed images.
  - Instances, i.e. objects sharing a mesh, stay instances.

It installs **alongside** the built-in FBX add-on and does not replace it. All other import/export options are the same as in Blender's own FBX add-on.

## Contents

- [Installation](#installation)
- [Usage](#usage)
- [How layers are mapped](#how-layers-are-mapped)
- [Textures](#textures)
- [Instances](#instances)
- [Why the Python importer and not Blender's C++ (ufbx) importer](#why-the-python-importer-and-not-blenders-c-ufbx-importer)
- [Known limitations](#known-limitations)
- [Development](#development)
- [License](#license)

## Installation

1. Download `io_scene_fbx_layers-<version>.zip` from the [Releases](https://github.com/VinXR/Blender-FBX-Importer-Exporter-with-layers/releases) page.
2. In Blender, open **Edit → Preferences → Get Extensions**, then choose **▾ → Install from Disk…** and select the zip.

Requires Blender **5.1** or newer (tested on 5.1 and 5.2).

**Updating:** install the new zip the same way, then **restart Blender**. Blender keeps the add-on's old Python modules loaded until it restarts. If several Blender windows are open, restart all of them.

## Usage

- **File → Import → FBX + Layers (.fbx)**
- **File → Export → FBX + Layers (.fbx)**

Blender's own entries stay available:

- Import: "FBX (.fbx)" (the C++ importer) and "FBX (.fbx) (Legacy)".
- Export: "FBX (.fbx)".

Export options differ from the built-in exporter only in one default: **Path Mode = Copy** (see [Textures](#textures)).

## How layers are mapped

### Import

- For every Display Layer in the file, a collection with the layer's name is created as a child of the active collection, and the layer's objects are moved into it.
- Objects that are not in a layer stay in the active collection, as with the built-in importer.
- A layer with no importable objects still creates an (empty) collection.
- Bones inside a layer are ignored, because a bone is not an object in Blender and cannot belong to a collection. The armature stays where the importer puts it.
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
  - The built-in exporter defaults to *Auto* and, in *Copy* mode, puts textures in a `<name>.fbm` subfolder.
- **Packed images** are written from their packed data.
  - This covers textures that came from an FBX with embedded media: Blender keeps those images packed, with a path to a folder that does not exist.
  - The built-in exporter skips these with "missing …, not copying".
- **Embed Textures** still works as before: the textures go inside the FBX.

## Instances

In FBX, objects that share a mesh are one Geometry connected to several nodes, and **materials belong to the node**, not to the geometry.

- Objects that share a mesh in Blender keep sharing one FBX Geometry, **even when they use different Object-linked materials**.
- The mesh is only duplicated when the objects' material slot layouts are incompatible: slot *N* has to give the same FBX material index for every object. For example, a two-slot mesh where one object uses two different materials and another object uses the same material twice cannot be shared.
- The built-in exporter instead duplicates the mesh for every object that has Object-linked materials, so instances coming from Max or Maya are exported as separate meshes.

## Why the Python importer and not Blender's C++ (ufbx) importer

Since Blender 5.0 the default FBX importer is written in C++ and built on [ufbx](https://github.com/ufbx/ufbx). The Python importer this add-on is based on is listed as "FBX (.fbx) (Legacy)".

**ufbx reads everything this add-on needs.** It exposes Display Layers (`ufbx_display_layer`: member nodes, `visible`, `frozen`, `ui_color`) and instancing. However, **Blender's C++ importer does not use them**. Tested with Blender 5.1 on a file with four layers and three instances of one mesh:

- every object ended up in a single collection;
- every instance got its own mesh.

**The C++ importer cannot be extended by an add-on.** It is compiled into Blender. Changing it means building Blender and getting the change accepted upstream, which is the right long-term fix but outside the scope of an add-on.

The Python importer, on the other hand, can be forked and shipped as an extension, which is what this add-on does.

**A hybrid was considered and rejected.** It would import with the C++ importer and then read the file again in Python to apply the layers.

- Imported objects would have to be matched to FBX nodes by name, which breaks with duplicate names and `.001` renames.
- Instances would still be lost.

Python bindings for ufbx exist on PyPI, but their provenance could not be verified and they ship only compiled binaries, so they are not used.

### Trade-offs

| | This add-on (Python importer) | Blender's C++ importer |
|---|---|---|
| Display Layers → collections | ✅ (with color, visibility, freeze) | ❌ |
| Instances (shared meshes) | ✅ | ❌ (one mesh per instance) |
| Import speed on large files | slower | much faster |
| ASCII FBX files | ❌ ("ASCII FBX files are not supported") | ✅ |
| FBX older than 7.1 (version < 7100) | ❌ | ✅ |

For ASCII FBX files or very old FBX versions, use Blender's own importer, or convert the file to binary FBX 7.1+ first, for example with Autodesk FBX Converter.

There is only one FBX exporter in Blender, written in Python, so this add-on's exporter is a superset of the built-in one.

## Known limitations

- Import uses the Python importer, so the limits in the table above apply: no ASCII FBX, no FBX older than 7.1, slower than the C++ importer.
- Bones inside a layer are ignored on import and never get a layer on export.
- An object in several collections is exported in one layer only (the first, see [Export](#export)).
- Collection color tags are an approximation of the layer color. The exact color survives a round trip only while the tag is not changed.
- Show maps to the eye icon of the view layer used for import/export. Other view layers are not touched.
- A packed image with no file path at all (e.g. a texture painted in Blender and never saved) may be written without a file extension.
- Export is always binary FBX 7.4, as with the built-in exporter.
- Drag and drop of `.fbx` files is not handled; it stays with Blender's own importer.
- Tested on Blender 5.1 and 5.2 only.

Exported layers have been verified with the **Autodesk FBX SDK 2020.3.11**, the library behind the Max and Maya FBX plug-ins.

The SDK silently drops any layer object that is written without an (empty) child block. This add-on writes it the same way the SDK does.

## Development

- Every change to the original add-on code is marked with `# FBX-LAYERS begin` / `# FBX-LAYERS end`. The new logic lives in `io_scene_fbx_layers/layers.py`.
- The first commit of this repository is the unmodified `io_scene_fbx` 5.15.0. Diff against it to see every change made by the fork.
- To port the fork to a newer `io_scene_fbx`, copy the new add-on files and re-apply the marked blocks.

Run the tests from the repository root:

```
blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
```

The tests cover:

- layer export rules;
- export → import round trips;
- layer color, visibility and freeze;
- texture copying, including packed images;
- instances;
- the same FBX content as the built-in exporter once the layer data is stripped (headers and timestamps aside).

Import tests against real files run only if you drop FBX files that contain Display Layers into `tests/samples/`. No sample assets are distributed.

Build the installable zip:

```
cd io_scene_fbx_layers
blender --command extension build --output-dir ../dist
```

## License

GPL-2.0-or-later, the same license as the original add-on. Based on `io_scene_fbx` by the Blender Foundation.
