# FBX + Layers for Blender

A fork of Blender's bundled FBX add-on (`io_scene_fbx` 5.15.0, Blender 5.1) that adds support for **FBX Display Layers**, the layers you get from 3ds Max and Maya.

- **Import:** each Display Layer becomes a Blender **Collection** that holds the layer's objects.
- **Export:** collections are written as Display Layers. Max, Maya and other FBX SDK based apps read them back as layers.

It installs alongside the built-in FBX add-on and does not replace it.

## Installation

1. Download `io_scene_fbx_layers-<version>.zip` from the [Releases](https://github.com/VinXR/Blender-FBX-Importer-Exporter-with-layers/releases) page.
2. In Blender, open **Edit → Preferences → Get Extensions**, then choose **▾ → Install from Disk…** and select the zip.
3. Use **File → Import / Export → FBX + Layers (.fbx)**.

Requires Blender **5.1** or newer (tested on 5.1 and 5.2).

## How layers are mapped

### Import

- For every Display Layer in the file, a collection with the layer's name is created as a child of the active collection. The layer's objects are moved into it.
- Objects that are not in a layer stay in the active collection, as with the built-in importer.
- A layer with no importable objects still creates an (empty) collection.
- Bones inside a layer are ignored, because a bone is not an object in Blender and cannot belong to a collection. The armature stays where the importer puts it.
- Layer properties are mapped as described under [Layer properties](#layer-properties).

### Export

An FBX object can be in at most one Display Layer, while a Blender object can be linked to several collections. Each exported object therefore gets the layer of its **first** collection, using these rules:

- "First" is the first place the object appears in the Outliner (View Layer mode), going depth first.
  - Child collections come before the collection's own objects, as in the Outliner.
  - The order in which the object was linked does not matter.
- Nested collections are flattened. The layer is named after the collection that directly contains the object; parent collections do not become layers.
- Objects linked only to the Scene Collection get no layer.
- Instances (collection instances, duplis) get the layer of the object that instances them.
- Only collections with at least one exported object are written. The usual export filters still apply: selected only, visible only, active collection, and so on.

### Layer properties

| FBX layer | Blender collection |
|---|---|
| **Color** | Collection **color tag**. Blender only has 8 theme colors, so the closest tag is used, and the default grey means no tag. The exact color is kept in the collection custom property `fbx_layer_color`. |
| **Show** = off | Collection hidden in the view layer (eye icon). |
| **Freeze** = on | Collection not selectable. |

On export:

- **Color**
  - If the collection still has the tag it got on import, the exact `fbx_layer_color` is written.
  - If you changed the tag in Blender, the theme color of the new tag is written.
  - With no tag, the default grey is written.
- **Show** is off when the collection is hidden in the exported view layer or disabled in viewports.
- **Freeze** is on when the collection is not selectable.

## Other differences from the built-in exporter

- **Textures are copied next to the FBX by default.** Path Mode defaults to *Copy*. Textures go in the same folder as the `.fbx`, not in a `<name>.fbm` subfolder, and are referenced with relative paths.
  - Packed images are written from their packed data, so textures imported from an FBX with embedded media are exported too. The built-in exporter skips these with "missing …, not copying".
  - *Embed Textures* still works as before.
- **Instances stay instances.** Objects that share a mesh keep sharing one FBX Geometry even when they use different Object-linked materials. In FBX, materials belong to the node, not to the geometry.
  - The mesh is only duplicated when the objects' material slot layouts are incompatible.
  - The built-in exporter duplicates the mesh for every object with Object-linked materials.

Notes:

- Import is based on the Python FBX importer, which Blender 5.1 lists as "FBX (.fbx) (Legacy)".
  - Blender's new default FBX importer is written in C++ and built into Blender, so an add-on cannot extend it.
  - It also ignores Display Layers and does not keep instances: each instance gets its own mesh.
- Drag and drop of `.fbx` files is not handled; it stays with Blender's own importer.

## Development

Changes to the original add-on code are marked with `# FBX-LAYERS begin` / `# FBX-LAYERS end`. This makes them easy to port to newer versions of `io_scene_fbx`. The new logic lives in `io_scene_fbx_layers/layers.py`.

Run the tests from the repository root:

```
blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py
```

Import tests against real files run only if you drop FBX files that contain Display Layers into `tests/samples/`. No sample assets are distributed.

Build the installable zip:

```
cd io_scene_fbx_layers
blender --command extension build --output-dir ../dist
```

## License

GPL-2.0-or-later, the same license as the original add-on. Based on `io_scene_fbx` by the Blender Foundation.
