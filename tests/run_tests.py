# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Run from the project root:
#   blender --background --factory-startup --python-exit-code 1 --python tests/run_tests.py

import os
import sys
import tempfile
import traceback

import addon_utils
import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "tests", "samples")
EXAMPLE = os.path.join(ROOT, "example", "Prova_00.fbx")
OUT_DIR = tempfile.mkdtemp(prefix="fbx_layers_")

sys.path.insert(0, ROOT)
import io_scene_fbx_layers  # noqa: E402
from io_scene_fbx_layers import parse_fbx  # noqa: E402

io_scene_fbx_layers.register()
addon_utils.enable("io_scene_fbx", default_set=True)  # Official exporter, for the M1 comparison.

BONE_CLASSES = {b"LimbNode", b"Limb"}


# ##### Helpers #####

def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = view_layer.layer_collection


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_object(name, *collections, mesh=True):
    data = None
    if mesh:
        data = bpy.data.meshes.new(name)
        data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    ob = bpy.data.objects.new(name, data)
    for col in collections:
        col.objects.link(ob)
    return ob


def build_test_scene():
    """
    Collections (Outliner order): A (child A_sub), B, Src (excluded, instanced), Rig, Empty.
    """
    clear_scene()
    scene_col = bpy.context.scene.collection
    col_a = new_collection("A")
    col_a_sub = new_collection("A_sub", col_a)
    col_b = new_collection("B")
    col_src = new_collection("Src")
    col_rig = new_collection("Rig")
    new_collection("Empty")

    new_object("RootOnly", scene_col)
    new_object("OnlyA", col_a)
    # A_sub is listed before A's own objects in the Outliner, so it wins over A and B.
    new_object("Shared", col_a, col_a_sub, col_b)
    new_object("SharedAB", col_a, col_b)
    # Link order does not matter, Outliner order does.
    new_object("SharedBA", col_b, col_a)

    parent = new_object("Parent", col_b, mesh=False)
    child = new_object("Child", col_a)
    child.parent = parent

    new_object("SrcCube", col_src)
    bpy.context.view_layer.layer_collection.children["Src"].exclude = True
    inst = new_object("Inst", col_b, mesh=False)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = col_src

    arm = bpy.data.armatures.new("RigData")
    rig = bpy.data.objects.new("Rig", arm)
    col_rig.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.edit_bones.new("Bone")
    bone.head = (0.0, 0.0, 0.0)
    bone.tail = (0.0, 0.0, 1.0)
    bpy.ops.object.mode_set(mode='OBJECT')


def fbx_sections(path):
    root, _version = parse_fbx.parse(path)
    return {elem.id: elem for elem in root.elems}


def read_layers(path):
    """Return ([layer names in file order], {layer: [(model name, model class), ...]}, [ObjectType defs])."""
    sections = fbx_sections(path)
    models = {}
    layers = {}
    for elem in sections[b"Objects"].elems:
        name = elem.props[1].split(b"\x00\x01")[0].decode()
        if elem.id == b"Model":
            models[elem.props[0]] = (name, elem.props[2])
        elif elem.id == b"CollectionExclusive" and elem.props[2] == b"DisplayLayer":
            layers[elem.props[0]] = name
    members = {name: [] for name in layers.values()}
    for conn in sections[b"Connections"].elems:
        if conn.props[0] == b"OO" and conn.props[2] in layers and conn.props[1] in models:
            members[layers[conn.props[2]]].append(models[conn.props[1]])
    defs = [d for d in sections[b"Definitions"].elems
            if d.id == b"ObjectType" and d.props[0] == b"CollectionExclusive"]
    return list(layers.values()), members, defs


def strip_layers(path):
    """Element tree of the file without header/timestamps and without anything Display Layer related."""
    sections = fbx_sections(path)
    layer_uuids = {e.props[0] for e in sections[b"Objects"].elems if e.id == b"CollectionExclusive"}

    def tree(elem):
        return (elem.id, tuple(elem.props), tuple(tree(e) for e in elem.elems))

    out = {}
    for sid, section in sections.items():
        if sid in {b"FBXHeaderExtension", b"FileId", b"CreationTime", b"Creator"}:
            continue
        elems = section.elems
        if sid == b"Definitions":
            elems = [e for e in elems if e.id != b"Count" and not (e.id == b"ObjectType" and e.props[0] == b"CollectionExclusive")]
        elif sid == b"Objects":
            elems = [e for e in elems if e.id != b"CollectionExclusive"]
        elif sid == b"Connections":
            elems = [e for e in elems if e.props[2] not in layer_uuids]
        out[sid] = tuple(tree(e) for e in elems)
    return out


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def import_fork(path):
    clear_scene()
    check(bpy.ops.import_scene.fbx_layers(filepath=path) == {'FINISHED'}, "import failed: " + path)


def collection_members(name):
    col = bpy.data.collections.get(name)
    check(col is not None, "missing collection " + name)
    check(bpy.context.scene.collection.children.get(name) is col, name + " is not a child of the import collection")
    return sorted(ob.name for ob in col.objects)


# ##### Tests #####

def test_export_layers():
    build_test_scene()
    path = os.path.join(OUT_DIR, "export_layers.fbx")
    check(bpy.ops.export_scene.fbx_layers(filepath=path) == {'FINISHED'}, "export failed")

    order, members, defs = read_layers(path)
    check(order == ["A", "A_sub", "B", "Rig"], "layer order %r" % order)
    names = {layer: sorted(n for n, _cls in m) for layer, m in members.items()}
    check(names["A"] == ["Child", "OnlyA", "SharedAB", "SharedBA"], "A: %r" % names["A"])
    check(names["A_sub"] == ["Shared"], "A_sub: %r" % names["A_sub"])
    check("Parent" in names["B"] and "Inst" in names["B"] and len(names["B"]) == 3, "B (with 1 dupli): %r" % names["B"])
    check(names["Rig"] == ["Rig"], "Rig: %r" % names["Rig"])
    all_members = {n for m in names.values() for n in m}
    check("RootOnly" not in all_members and "Bone" not in all_members, "RootOnly/Bone must have no layer")

    check(len(defs) == 1, "one CollectionExclusive definition expected")
    count = [e.props[0] for e in defs[0].elems if e.id == b"Count"]
    tmpl = [e.props[0] for e in defs[0].elems if e.id == b"PropertyTemplate"]
    check(count == [4] and tmpl == [b"FbxDisplayLayer"], "definition %r %r" % (count, tmpl))
    return path, names


def test_round_trip(path, exported):
    import_fork(path)
    for layer in ("A", "A_sub", "B", "Rig"):
        check(collection_members(layer) == exported[layer], "%s round trip: %r" % (layer, collection_members(layer)))
    check("RootOnly" in bpy.context.scene.collection.objects, "RootOnly should stay in the import collection")


def test_same_as_official():
    build_test_scene()
    fork_path = os.path.join(OUT_DIR, "cmp_fork.fbx")
    official_path = os.path.join(OUT_DIR, "cmp_official.fbx")
    check(bpy.ops.export_scene.fbx_layers(filepath=fork_path) == {'FINISHED'}, "fork export failed")
    check(bpy.ops.export_scene.fbx(filepath=official_path) == {'FINISHED'}, "official export failed")
    fork, official = strip_layers(fork_path), strip_layers(official_path)
    for sid in official:
        check(fork.get(sid) == official[sid], "section %r differs from the official exporter" % sid)
    check(set(fork) == set(official), "sections differ")


def test_textures_copied_next_to_fbx():
    clear_scene()
    src_dir = tempfile.mkdtemp(prefix="fbx_layers_tex_src_")
    img = bpy.data.images.new("tex_test", 4, 4)
    img.filepath_raw = os.path.join(src_dir, "tex_test.png")
    img.file_format = 'PNG'
    img.save()

    ma = bpy.data.materials.new("MatTex")
    if ma.node_tree is None:
        ma.use_nodes = True
    nodes = ma.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    ma.node_tree.links.new(tex.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    new_object("Textured", bpy.context.scene.collection).data.materials.append(ma)

    out_dir = tempfile.mkdtemp(prefix="fbx_layers_tex_out_")
    path = os.path.join(out_dir, "textured.fbx")
    # Default settings only: copying next to the FBX must be the default.
    check(bpy.ops.export_scene.fbx_layers(filepath=path) == {'FINISHED'}, "export failed")

    check(os.path.isfile(os.path.join(out_dir, "tex_test.png")), "texture not copied next to the FBX")
    check(not os.path.exists(os.path.join(out_dir, "textured.fbm")), "no .fbm folder expected")

    rel_names = []

    def walk(elem):
        if elem.id == b"RelativeFilename":
            rel_names.append(elem.props[0])
        for e in elem.elems:
            walk(e)

    walk(fbx_sections(path)[b"Objects"])
    check(rel_names and all(n == b"tex_test.png" for n in rel_names), "relative paths: %r" % rel_names)


def test_packed_textures_written_next_to_fbx():
    """Packed image whose file is gone from disk, like textures imported from an FBX with embedded media."""
    clear_scene()
    src_dir = tempfile.mkdtemp(prefix="fbx_layers_packed_src_")
    src_path = os.path.join(src_dir, "packed_tex.png")
    img = bpy.data.images.new("packed_tex", 4, 4)
    img.filepath_raw = src_path
    img.file_format = 'PNG'
    img.save()
    img.pack()
    os.remove(src_path)
    packed_data = img.packed_file.data

    ma = bpy.data.materials.new("MatPacked")
    if ma.node_tree is None:
        ma.use_nodes = True
    nodes = ma.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    ma.node_tree.links.new(tex.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    new_object("Packed", bpy.context.scene.collection).data.materials.append(ma)

    out_dir = tempfile.mkdtemp(prefix="fbx_layers_packed_out_")
    path = os.path.join(out_dir, "packed.fbx")
    check(bpy.ops.export_scene.fbx_layers(filepath=path) == {'FINISHED'}, "export failed")

    dst = os.path.join(out_dir, "packed_tex.png")
    check(os.path.isfile(dst), "packed texture not written next to the FBX")
    with open(dst, 'rb') as f:
        check(f.read() == packed_data, "written texture differs from the packed data")


def test_shared_mesh_kept_with_object_materials():
    """Instances (one mesh, Object-linked materials) keep one shared Geometry when their slot layouts match."""
    clear_scene()
    col = bpy.context.scene.collection
    me = bpy.data.meshes.new("SharedMesh")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], [], [(0, 1, 2), (1, 3, 2)])
    mats = {name: bpy.data.materials.new(name) for name in "ABCDE"}
    me.materials.append(mats["A"])
    me.materials.append(mats["B"])
    me.polygons[1].material_index = 1

    def instance(name, ma0, ma1):
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        for slot, ma in zip(ob.material_slots, (mats[ma0], mats[ma1])):
            slot.link = 'OBJECT'
            slot.material = ma

    instance("I1", "A", "B")
    instance("I2", "C", "D")  # Same layout as I1: shares the Geometry.
    instance("I3", "E", "E")  # Both slots map to one FBX material: different layout, own Geometry.

    path = os.path.join(OUT_DIR, "shared_mesh.fbx")
    check(bpy.ops.export_scene.fbx_layers(filepath=path) == {'FINISHED'}, "export failed")

    sections = fbx_sections(path)
    names = {}
    geoms = set()
    for elem in sections[b"Objects"].elems:
        name = elem.props[1].split(b"\x00\x01")[0].decode()
        if elem.id in {b"Model", b"Material"}:
            names[elem.props[0]] = name
        elif elem.id == b"Geometry":
            geoms.add(elem.props[0])
    model_geom = {}
    model_mats = {}
    for conn in sections[b"Connections"].elems:
        if conn.props[0] != b"OO" or conn.props[2] not in names:
            continue
        if conn.props[1] in geoms:
            model_geom[names[conn.props[2]]] = conn.props[1]
        elif conn.props[1] in names:
            model_mats.setdefault(names[conn.props[2]], []).append(names[conn.props[1]])
    check(len(geoms) == 2, "expected 2 geometries, got %d" % len(geoms))
    check(model_geom["I1"] == model_geom["I2"] != model_geom["I3"], "geometry sharing: %r" % model_geom)
    check(model_mats["I2"] == ["C", "D"], "I2 materials: %r" % model_mats.get("I2"))

    import_fork(path)
    obs = {name: bpy.data.objects[name] for name in ("I1", "I2", "I3")}
    check(obs["I1"].data == obs["I2"].data != obs["I3"].data, "re-imported mesh sharing")
    for name, expected in (("I1", ["A", "B"]), ("I2", ["C", "D"]), ("I3", ["E", "E"])):
        ob = obs[name]
        got = [ob.material_slots[p.material_index].material.name.split(".")[0] for p in ob.data.polygons]
        check(got == expected, "%s face materials: %r" % (name, got))


def test_layer_properties():
    """Collection color tag / hidden / not selectable <-> layer Color / Show / Freeze, exact color kept on round trip."""
    from io_scene_fbx_layers import layers

    clear_scene()
    theme = {"COLOR_%02d" % (i + 1): tuple(t.color) for i, t in enumerate(bpy.context.preferences.themes[0].collection_color)}
    exact = (0.1, 0.2, 0.9)
    exact_tag = layers._nearest_color_tag(exact)

    cols = {name: new_collection(name) for name in ("Plain", "Red", "Exact", "Retagged", "Hidden", "Frozen")}
    for name, col in cols.items():
        new_object("ob_" + name, col)
    cols["Red"].color_tag = 'COLOR_01'
    cols["Exact"].color_tag = exact_tag
    cols["Exact"][layers.COLLECTION_COLOR_PROP] = exact
    # Exact color stored, but the tag was changed afterwards in Blender: the new tag wins.
    retag = 'COLOR_04' if exact_tag != 'COLOR_04' else 'COLOR_03'
    cols["Retagged"].color_tag = retag
    cols["Retagged"][layers.COLLECTION_COLOR_PROP] = exact
    bpy.context.view_layer.layer_collection.children["Hidden"].hide_viewport = True
    cols["Frozen"].hide_select = True

    path = os.path.join(OUT_DIR, "layer_props.fbx")
    check(bpy.ops.export_scene.fbx_layers(filepath=path) == {'FINISHED'}, "export failed")

    written = {}
    for elem in fbx_sections(path)[b"Objects"].elems:
        if elem.id == b"CollectionExclusive":
            name = elem.props[1].split(b"\x00\x01")[0].decode()
            props = {}
            for p70 in elem.elems:
                for p in p70.elems:
                    props[p.props[0].decode()] = tuple(p.props[4:]) if p.props[0] == b"Color" else p.props[4]
            written[name] = props

    def close(a, b):
        return all(abs(x - y) < 1e-5 for x, y in zip(a, b))

    check(written["Plain"] == {}, "Plain should have no properties: %r" % written["Plain"])
    check(close(written["Red"]["Color"], theme["COLOR_01"]), "Red color %r" % (written["Red"],))
    check(close(written["Exact"]["Color"], exact), "Exact color %r" % (written["Exact"],))
    check(close(written["Retagged"]["Color"], theme[retag]), "Retagged color %r" % (written["Retagged"],))
    check(written["Hidden"].get("Show") == 0, "Hidden: %r" % written["Hidden"])
    check(written["Frozen"].get("Freeze") == 1, "Frozen: %r" % written["Frozen"])

    import_fork(path)
    lcs = bpy.context.view_layer.layer_collection.children
    got = {name: bpy.data.collections[name] for name in cols}
    check(got["Plain"].color_tag == 'NONE' and layers.COLLECTION_COLOR_PROP not in got["Plain"], "Plain re-imported")
    check(got["Red"].color_tag == 'COLOR_01', "Red tag %r" % got["Red"].color_tag)
    check(got["Exact"].color_tag == exact_tag and close(got["Exact"][layers.COLLECTION_COLOR_PROP], exact),
          "Exact re-imported: %r" % got["Exact"].color_tag)
    check(got["Retagged"].color_tag == retag, "Retagged tag %r" % got["Retagged"].color_tag)
    check(lcs["Hidden"].hide_viewport and not lcs["Plain"].hide_viewport, "Hidden re-imported")
    check(got["Frozen"].hide_select and not got["Plain"].hide_select, "Frozen re-imported")


def test_import_sample(path):
    order, members, _defs = read_layers(path)
    check(order, "sample has no layers: " + path)
    import_fork(path)
    for layer in order:
        expected = sorted(n for n, cls in members[layer] if cls not in BONE_CLASSES)
        got = collection_members(layer)
        check(got == expected, "%s / %s: got %r, expected %r" % (os.path.basename(path), layer, got, expected))
    return {layer: collection_members(layer) for layer in order}


def main():
    results = []

    def run(name, fn, *args):
        try:
            ret = fn(*args)
            results.append((name, True, ""))
            return ret
        except Exception:
            results.append((name, False, traceback.format_exc()))
            return None

    exported = run("export: collections -> display layers", test_export_layers)
    if exported:
        run("round trip: export -> import", test_round_trip, *exported)
    run("M1: same output as official exporter (layers stripped)", test_same_as_official)
    run("export: textures copied next to the FBX, relative paths", test_textures_copied_next_to_fbx)
    run("export: packed textures written next to the FBX", test_packed_textures_written_next_to_fbx)
    run("export: instances keep a shared Geometry", test_shared_mesh_kept_with_object_materials)
    run("layer color / visibility / freeze round trip", test_layer_properties)
    # Sample FBX files with Display Layers are not distributed (third-party assets): drop your own in tests/samples/.
    samples = [EXAMPLE] if os.path.isfile(EXAMPLE) else []
    if os.path.isdir(SAMPLES):
        samples += sorted(os.path.join(SAMPLES, f) for f in os.listdir(SAMPLES) if f.lower().endswith(".fbx"))
    if not samples:
        print("No sample FBX files found, skipping the import sample tests.")
    for path in samples:
        got = run("import: " + os.path.basename(path), test_import_sample, path)
        if got is not None:
            print("    %s -> %r" % (os.path.basename(path), got))

    print()
    for name, ok, err in results:
        print("%s  %s" % ("PASS" if ok else "FAIL", name))
        if err:
            print(err)
    print("Blender %s, output in %s" % (bpy.app.version_string, OUT_DIR))
    if not all(ok for _name, ok, _err in results):
        sys.exit(1)


main()
