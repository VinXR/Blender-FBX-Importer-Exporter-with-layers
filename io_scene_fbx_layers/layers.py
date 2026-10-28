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
    fbx_name_class,
    get_blenderID_key,
    get_fbx_uuid_from_key,
)

FBX_LAYER_TYPE = b"CollectionExclusive"
FBX_LAYER_CLASS = b"DisplayLayer"


# ##### Export #####

def fbx_template_def_display_layer(nbr_users=0):
    # Same defaults Maya/Max write, so layer objects themselves need no Properties70.
    props = {
        b"Color": ((0.8, 0.8, 0.8), "p_color_rgb", False),
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
    for collection, (layer_uuid, _layer_members) in scene_data.data_display_layers.items():
        layer = elem_data_single_int64(root, FBX_LAYER_TYPE, layer_uuid)
        layer.add_string(fbx_name_class(collection.name.encode(), FBX_LAYER_CLASS))
        layer.add_string(FBX_LAYER_CLASS)


# ##### Import #####

def import_display_layers(fbx_table_nodes, fbx_connections, fbx_helper_nodes, view_layer):
    """
    Create one collection per Display Layer, as a child of the collection the importer linked the objects to, and move
    the layer's objects into it. Bones in a layer are ignored.
    """
    from .import_fbx import elem_name_ensure_class

    parent_collection = view_layer.active_layer_collection.collection

    layer_collections = {}
    for fbx_uuid, (fbx_obj, _bl_data) in fbx_table_nodes.items():
        if fbx_obj.id != FBX_LAYER_TYPE or fbx_obj.props[2] != FBX_LAYER_CLASS:
            continue
        collection = bpy.data.collections.new(elem_name_ensure_class(fbx_obj, FBX_LAYER_CLASS))
        parent_collection.children.link(collection)
        layer_collections[fbx_uuid] = collection

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
