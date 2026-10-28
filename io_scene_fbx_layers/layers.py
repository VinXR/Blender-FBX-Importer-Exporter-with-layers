# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

# FBX-LAYERS: FBX Display Layers <-> Blender Collections.
#
# In FBX a Display Layer is a 'CollectionExclusive' object of class 'DisplayLayer', and each Model in it has an extra
# "OO" connection (Model -> layer). 'Exclusive' means a Model belongs to at most one layer.

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

def import_display_layers(fbx_table_nodes, fbx_connections, fbx_helper_nodes, view_layer, fbx_tmpl):
    """
    Create one collection per Display Layer, as a child of the collection the importer linked the objects to, and move
    the layer's objects into it. Bones in a layer are ignored.
    Layer color -> collection color tag (exact color kept in COLLECTION_COLOR_PROP), Show -> hidden in the view layer
    (eye icon), Freeze -> collection not selectable.
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
        collection = bpy.data.collections.new(elem_name_ensure_class(fbx_obj, FBX_LAYER_CLASS))
        parent_collection.children.link(collection)
        layer_collections[fbx_uuid] = collection

        fbx_props = (elem_find_first(fbx_obj, b'Properties70'), tmpl_props)
        color = tuple(elem_props_get_color_rgb(fbx_props, b'Color', FBX_LAYER_DEFAULT_COLOR))
        collection.color_tag = _nearest_color_tag(color)
        if collection.color_tag != 'NONE':
            collection[COLLECTION_COLOR_PROP] = color
            collection.id_properties_ui(COLLECTION_COLOR_PROP).update(subtype='COLOR', min=0.0, max=1.0)
        collection.hide_select = elem_props_get_bool(fbx_props, b'Freeze', False)
        layer_collection = parent_layer_collection.children[collection.name]
        layer_collection.hide_viewport = not elem_props_get_bool(fbx_props, b'Show', True)

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
        obj = helper.bl_obj
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        if parent_collection.objects.get(obj.name) is obj:
            parent_collection.objects.unlink(obj)
