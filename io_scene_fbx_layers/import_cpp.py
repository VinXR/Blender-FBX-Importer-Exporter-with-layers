# SPDX-FileCopyrightText: 2026 VinXR
#
# SPDX-License-Identifier: GPL-2.0-or-later

# FBX-LAYERS: "FBX + Layers" import on top of Blender's C++ FBX importer (bpy.ops.wm.fbx_import, ufbx).
# Blender imports the file; ufbx (ufbx_reader) reads the Display Layers, which are then applied to collections.
# The operator's options are copied at registration time from wm.fbx_import of the running Blender, so they follow
# Blender's own importer as it changes.

import os

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy_extras.io_utils import ImportHelper

from . import layers, ufbx_reader

# Options of wm.fbx_import handled by this operator itself.
_OWN_PROPERTIES = {"rna_type", "filepath", "directory", "files", "filter_glob"}

# Names of the wm.fbx_import options mirrored on the operator, filled in by register().
_mirrored = []


def _mirror_property(prop):
    """bpy.props definition equivalent to the RNA property `prop`, or None for unsupported kinds."""
    common = {"name": prop.name, "description": prop.description, "options": {'SKIP_SAVE'} if prop.is_skip_save else set()}
    if getattr(prop, "is_array", False) and prop.array_length > 0:
        return None
    if prop.type == 'BOOLEAN':
        return BoolProperty(default=prop.default, **common)
    if prop.type == 'INT':
        return IntProperty(default=prop.default, min=prop.hard_min, max=prop.hard_max, soft_min=prop.soft_min,
                           soft_max=prop.soft_max, step=prop.step, subtype=prop.subtype, **common)
    if prop.type == 'FLOAT':
        return FloatProperty(default=prop.default, min=prop.hard_min, max=prop.hard_max, soft_min=prop.soft_min,
                             soft_max=prop.soft_max, step=prop.step, precision=prop.precision, subtype=prop.subtype,
                             unit=prop.unit, **common)
    if prop.type == 'ENUM':
        items = [(item.identifier, item.name, item.description, item.icon, item.value) for item in prop.enum_items]
        if prop.is_enum_flag:
            common["options"].add('ENUM_FLAG')
            return EnumProperty(items=items, default=set(prop.default_flag), **common)
        return EnumProperty(items=items, default=prop.default, **common)
    if prop.type == 'STRING':
        return StringProperty(default=prop.default, subtype=prop.subtype, **common)
    return None


class ImportFBXLayers(bpy.types.Operator, ImportHelper):
    """Import an FBX file with Blender's importer, turning its Display Layers into collections"""
    bl_idname = "import_scene.fbx_layers"
    bl_label = "Import FBX + Layers"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={'HIDDEN'})
    files: CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement,
                              options={'HIDDEN', 'SKIP_SAVE'})
    directory: StringProperty(subtype='DIR_PATH', options={'HIDDEN', 'SKIP_SAVE'})

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        for name in _mirrored:
            layout.prop(self, name)

    def execute(self, context):
        options = {name: getattr(self, name) for name in _mirrored}
        global_scale = options.get("global_scale", 1.0)
        if self.files and self.directory:
            paths = [os.path.join(self.directory, f.name) for f in self.files if f.name]
        else:
            paths = [self.filepath]

        imported = False
        for path in paths:
            try:
                scene_info = ufbx_reader.read_scene(path, global_scale)
            except ufbx_reader.UfbxError as ex:
                scene_info = None
                self.report({'WARNING'}, "Display Layers not read from {!r}: {:s}".format(path, str(ex)))

            before = set(bpy.data.objects)
            if bpy.ops.wm.fbx_import(filepath=path, **options) != {'FINISHED'}:
                continue
            imported = True
            if scene_info is None:
                continue

            context.view_layer.update()  # World matrices are used to tell apart nodes with the same name.
            new_objects = [obj for obj in bpy.data.objects if obj not in before]
            unmatched = layers.apply_ufbx_layers(scene_info, new_objects, context.view_layer)
            if unmatched:
                self.report({'WARNING'}, "{:d} layer member(s) not found among the imported objects: {:s}".format(
                    len(unmatched), ", ".join(unmatched[:10])))
        return {'FINISHED'} if imported else {'CANCELLED'}


def register():
    rna = bpy.ops.wm.fbx_import.get_rna_type()
    _mirrored.clear()
    for prop in rna.properties:
        if prop.is_hidden or prop.identifier in _OWN_PROPERTIES:
            continue
        definition = _mirror_property(prop)
        if definition is not None:
            ImportFBXLayers.__annotations__[prop.identifier] = definition
            _mirrored.append(prop.identifier)
    bpy.utils.register_class(ImportFBXLayers)


def unregister():
    bpy.utils.unregister_class(ImportFBXLayers)
    for name in _mirrored:
        ImportFBXLayers.__annotations__.pop(name, None)
    _mirrored.clear()
