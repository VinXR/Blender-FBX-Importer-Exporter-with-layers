# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

# FBX-LAYERS: FBX Display Layers <-> Blender Collections.
#
# In FBX a Display Layer is a 'CollectionExclusive' object of class 'DisplayLayer', and each Model in it has an extra
# "OO" connection (Model -> layer). 'Exclusive' means a Model belongs to at most one layer.

import re

import bpy

from .fbx_utils import (
    FBXTemplate,
    elem_data_single_int64,
    elem_properties,
    elem_props_template_init,
    elem_props_template_set,
    fbx_name_class,
    get_blenderID_key,
    get_fbx_uuid_from_key,
)

FBX_LAYER_TYPE = b"CollectionExclusive"
FBX_LAYER_CLASS = b"DisplayLayer"
FBX_LAYER_DEFAULT_COLOR = (0.8, 0.8, 0.8)

# Collections only have 8 theme color tags, so the exact layer color is kept in this custom property for round trips.
COLLECTION_COLOR_PROP = "fbx_layer_color"


# ##### Layer color <-> collection color tag #####

def _theme_color_tags():
    theme = bpy.context.preferences.themes[0]
    return {"COLOR_%02d" % (i + 1): tuple(tag.color) for i, tag in enumerate(theme.collection_color)}


def _nearest_color_tag(color):
    """The FBX default (grey) layer color means no tag, anything else gets the closest theme color tag."""
    if all(abs(a - b) < 1e-4 for a, b in zip(color, FBX_LAYER_DEFAULT_COLOR)):
        return 'NONE'
    tags = _theme_color_tags()
    return min(tags, key=lambda tag: sum((a - b) ** 2 for a, b in zip(tags[tag], color)))


def _collection_layer_color(collection):
    """
    The exact color from the import if the collection still has the tag it was given, otherwise the theme color of
    its current tag (the user changed it in Blender).
    """
    tag = collection.color_tag
    if tag == 'NONE':
        return FBX_LAYER_DEFAULT_COLOR
    stored = collection.get(COLLECTION_COLOR_PROP)
    if stored is not None and len(stored) == 3:
        stored = tuple(float(c) for c in stored)
        if _nearest_color_tag(stored) == tag:
            return stored
    return _theme_color_tags()[tag]


def _find_layer_collection(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        found = _find_layer_collection(child, collection)
        if found is not None:
            return found
    return None


# ##### Export #####

def fbx_template_def_display_layer(nbr_users=0):
    # Same defaults Maya/Max write, so layers with default values need no Properties70.
    props = {
        b"Color": (FBX_LAYER_DEFAULT_COLOR, "p_color_rgb", False),
        b"Show": (True, "p_bool", False),
        b"Freeze": (False, "p_bool", False),
        b"LODBox": (False, "p_bool", False),
    }
    return FBXTemplate(FBX_LAYER_TYPE, b"FbxDisplayLayer", props, nbr_users, [False])


def _primary_collections(scene):
    """
    Map each object to its 'primary' collection: the first collection that directly contains it, in the order the
    View Layer Outliner shows them (child collections before the collection's own objects, depth-first).
    The Scene Collection itself is not a layer.
    """
    primary = {}
    order = []

    def visit(collection):
        order.append(collection)
        for child in collection.children:
            visit(child)
        for ob in collection.objects:
            primary.setdefault(ob, collection)

    for child in scene.collection.children:
        visit(child)
    return primary, order


def export_gather(scene, objects):
    """
    Return {collection: (layer_uuid, [ob_obj, ...])} for every collection that is the primary collection of at least
    one exported object, in Outliner order.
    """
    primary, order = _primary_collections(scene)
    members = {}
    for ob_obj in objects:
        if ob_obj.is_bone:
            # Bones are not objects, they have no collection.
            continue
        # Dupli instances take the layer of the object that generates them.
        bdata = ob_obj.parent.bdata if ob_obj.is_dupli else ob_obj.bdata
        collection = primary.get(bdata)
        if collection is not None:
            members.setdefault(collection, []).append(ob_obj)

    return {collection: (get_fbx_uuid_from_key(get_blenderID_key(collection) + "|FbxDisplayLayer"), members[collection])
            for collection in order if collection in members}


def export_connections(data_display_layers):
    return [(b"OO", ob_obj.fbx_uuid, layer_uuid, None)
            for layer_uuid, layer_members in data_display_layers.values()
            for ob_obj in layer_members]


def fbx_data_display_layer_elements(root, scene_data):
    view_layer = scene_data.depsgraph.view_layer
    for collection, (layer_uuid, _layer_members) in scene_data.data_display_layers.items():
        layer = elem_data_single_int64(root, FBX_LAYER_TYPE, layer_uuid)
        layer.add_string(fbx_name_class(collection.name.encode(), FBX_LAYER_CLASS))
        layer.add_string(FBX_LAYER_CLASS)

        # Hidden: the collection is disabled in viewports, or hidden in the exported view layer (eye icon).
        layer_collection = _find_layer_collection(view_layer.layer_collection, collection)
        show = not (collection.hide_viewport or (layer_collection is not None and layer_collection.hide_viewport))
        freeze = collection.hide_select
        color = _collection_layer_color(collection)
        if (color, show, freeze) == (FBX_LAYER_DEFAULT_COLOR, True, False):
            continue
        tmpl = elem_props_template_init(scene_data.templates, b"DisplayLayer")
        props = elem_properties(layer)
        elem_props_template_set(tmpl, props, "p_color_rgb", b"Color", color)
        elem_props_template_set(tmpl, props, "p_bool", b"Show", show)
        elem_props_template_set(tmpl, props, "p_bool", b"Freeze", freeze)


# ##### Import #####

def _new_layer_collection(parent_layer_collection, name, color, show, freeze):
    """
    Collection for one Display Layer, child of the collection the importer linked the objects to.
    Layer color -> collection color tag (exact color kept in COLLECTION_COLOR_PROP), Show -> hidden in the view layer
    (eye icon), Freeze -> collection not selectable.
    """
    collection = bpy.data.collections.new(name)
    parent_layer_collection.collection.children.link(collection)
    collection.color_tag = _nearest_color_tag(color)
    if collection.color_tag != 'NONE':
        collection[COLLECTION_COLOR_PROP] = color
        collection.id_properties_ui(COLLECTION_COLOR_PROP).update(subtype='COLOR', min=0.0, max=1.0)
    collection.hide_select = freeze
    parent_layer_collection.children[collection.name].hide_viewport = not show
    return collection


def _move_to_collection(obj, collection, parent_collection):
    if collection.objects.get(obj.name) is None:
        collection.objects.link(obj)
    if parent_collection.objects.get(obj.name) is obj:
        parent_collection.objects.unlink(obj)


def import_display_layers(fbx_table_nodes, fbx_connections, fbx_helper_nodes, view_layer, fbx_tmpl):
    """
    Legacy (Python) importer: create one collection per Display Layer and move the layer's objects into it.
    Bones in a layer are ignored.
    """
    from .import_fbx import (
        elem_find_first,
        elem_name_ensure_class,
        elem_props_get_bool,
        elem_props_get_color_rgb,
    )

    parent_layer_collection = view_layer.active_layer_collection
    parent_collection = parent_layer_collection.collection
    tmpl_props = elem_find_first(fbx_tmpl, b'Properties70') if fbx_tmpl is not None else None

    layer_collections = {}
    for fbx_uuid, (fbx_obj, _bl_data) in fbx_table_nodes.items():
        if fbx_obj.id != FBX_LAYER_TYPE or fbx_obj.props[2] != FBX_LAYER_CLASS:
            continue
        fbx_props = (elem_find_first(fbx_obj, b'Properties70'), tmpl_props)
        layer_collections[fbx_uuid] = _new_layer_collection(
            parent_layer_collection,
            elem_name_ensure_class(fbx_obj, FBX_LAYER_CLASS),
            tuple(elem_props_get_color_rgb(fbx_props, b'Color', FBX_LAYER_DEFAULT_COLOR)),
            elem_props_get_bool(fbx_props, b'Show', True),
            elem_props_get_bool(fbx_props, b'Freeze', False))

    if not layer_collections:
        return

    for fbx_link in fbx_connections.elems:
        if fbx_link.props[0] != b'OO' or fbx_link.props_type[1:3] != b'LL':
            continue
        c_src, c_dst = fbx_link.props[1:3]
        collection = layer_collections.get(c_dst)
        if collection is None:
            continue
        helper = fbx_helper_nodes.get(c_src)
        if helper is None or helper.is_bone or helper.bl_obj is None:
            continue
        _move_to_collection(helper.bl_obj, collection, parent_collection)


# ##### Import on top of Blender's C++ importer (ufbx) #####

_NAME_SUFFIX = re.compile(r"^(.*)\.(\d{3,})$")
_MAX_NAME_BYTES = 63


def _split_name(name):
    """'Cube.003' -> ('Cube', 3), 'Cube' -> ('Cube', 0)."""
    match = _NAME_SUFFIX.match(name)
    return (match.group(1), int(match.group(2))) if match else (name, 0)


def _truncate_name(name):
    data = name.encode("utf-8")[:_MAX_NAME_BYTES]
    return data.decode("utf-8", "ignore")


def _same_base(node_name, obj_base):
    # Blender truncates names to 63 bytes, and shortens them further to fit a .NNN suffix.
    if obj_base == node_name:
        return True
    return len(obj_base.encode("utf-8")) >= _MAX_NAME_BYTES - 5 and node_name.startswith(obj_base)


def _object_name_for_node(nodes, node):
    # Same naming as Blender's importer (fbx_import_mesh.cc): geometry transform helpers are "<parent>_GeomAdjust".
    if node["helper"] and node["parent"] >= 0:
        return _truncate_name(nodes[node["parent"]]["name"] + "_GeomAdjust")
    return _truncate_name(node["name"])


def _match_nodes_to_objects(nodes, wanted, new_objects):
    """
    Map ufbx node indices in `wanted` to the objects Blender's C++ importer created for them.
    Blender keeps no FBX id on objects: match by name (ignoring Blender's .NNN suffix), then by world position among
    nodes sharing a name, then by order (Blender numbers duplicates in creation order).
    """
    objects_by_base = {}
    for obj in new_objects:
        base, number = _split_name(obj.name)
        objects_by_base.setdefault(base, []).append((number, obj))

    groups = {}
    for index, node in enumerate(nodes):
        if node["root"] or node["bone"]:
            continue  # Bones become Blender bones, not objects.
        groups.setdefault(_object_name_for_node(nodes, node), []).append(index)

    mapping = {}
    for name, indices in groups.items():
        if not any(i in wanted for i in indices):
            continue
        candidates = [item for base, items in objects_by_base.items() if _same_base(name, base) for item in items]
        if not candidates:
            continue
        pairs = []
        for i in indices:
            pos = nodes[i]["pos"]
            for number, obj in candidates:
                dist = sum((a - b) ** 2 for a, b in zip(obj.matrix_world.translation, pos))
                pairs.append((round(dist, 6), i, number, obj))
        pairs.sort(key=lambda pair: pair[:3])
        used_nodes, used_objects = set(), set()
        for _dist, i, _number, obj in pairs:
            if i in used_nodes or obj in used_objects:
                continue
            used_nodes.add(i)
            used_objects.add(obj)
            mapping[i] = obj
    return {i: obj for i, obj in mapping.items() if i in wanted}


def apply_ufbx_layers(scene_info, new_objects, view_layer):
    """
    After Blender's C++ importer: create one collection per Display Layer and move the layer's objects into it.
    Geometry transform helper objects follow their node. Returns the names of layer nodes that could not be matched
    to an imported object (bones excluded).
    """
    nodes = scene_info["nodes"]
    file_layers = scene_info["layers"]
    if not file_layers:
        return []

    wanted = {i for layer in file_layers for i in layer["nodes"]}
    helpers = {}
    for index, node in enumerate(nodes):
        if node["helper"] and node["parent"] in wanted:
            helpers.setdefault(node["parent"], []).append(index)
    wanted.update(i for indices in helpers.values() for i in indices)
    mapping = _match_nodes_to_objects(nodes, wanted, new_objects)

    parent_layer_collection = view_layer.active_layer_collection
    parent_collection = parent_layer_collection.collection
    unmatched = []
    for layer in file_layers:
        collection = _new_layer_collection(
            parent_layer_collection, _truncate_name(layer["name"]), tuple(layer["color"]),
            layer["visible"], layer["frozen"])
        for i in layer["nodes"]:
            for j in [i] + helpers.get(i, []):
                obj = mapping.get(j)
                if obj is not None:
                    _move_to_collection(obj, collection, parent_collection)
                elif j == i and not nodes[i]["bone"]:
                    unmatched.append(nodes[i]["name"])
    return unmatched
