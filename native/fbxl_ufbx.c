/* SPDX-FileCopyrightText: 2026 VinXR
 *
 * SPDX-License-Identifier: GPL-2.0-or-later */

/* Thin C layer over ufbx for the FBX + Layers add-on.
 *
 * Loads an FBX file with the same ufbx options as Blender's C++ importer (source/blender/io/fbx/importer/
 * fbx_import.cc, Blender 5.1/5.2, ufbx 0.20.0) so the node list matches what that importer sees, and returns the
 * nodes and Display Layers as a JSON string. A flat string API keeps the Python side (ctypes) independent from
 * ufbx's struct layout. */

#include "ufbx/ufbx.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  define FBXL_EXPORT __declspec(dllexport)
#else
#  define FBXL_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
  char *data;
  size_t len, cap;
  int failed;
} Buf;

static void buf_reserve(Buf *b, size_t extra)
{
  if (b->failed || b->len + extra + 1 <= b->cap) {
    return;
  }
  size_t cap = b->cap ? b->cap : 4096;
  while (cap < b->len + extra + 1) {
    cap *= 2;
  }
  char *data = (char *)realloc(b->data, cap);
  if (!data) {
    b->failed = 1;
    return;
  }
  b->data = data;
  b->cap = cap;
}

static void buf_append(Buf *b, const char *s, size_t n)
{
  buf_reserve(b, n);
  if (b->failed) {
    return;
  }
  memcpy(b->data + b->len, s, n);
  b->len += n;
  b->data[b->len] = '\0';
}

static void buf_printf(Buf *b, const char *fmt, ...)
{
  char tmp[256];
  va_list args;
  va_start(args, fmt);
  int n = vsnprintf(tmp, sizeof(tmp), fmt, args);
  va_end(args);
  if (n > 0) {
    buf_append(b, tmp, (size_t)n < sizeof(tmp) ? (size_t)n : sizeof(tmp) - 1);
  }
}

/* JSON string; ufbx strings are UTF-8 (invalid sequences are already replaced by ufbx). */
static void buf_json_string(Buf *b, ufbx_string s)
{
  buf_append(b, "\"", 1);
  for (size_t i = 0; i < s.length; i++) {
    unsigned char c = (unsigned char)s.data[i];
    if (c == '"' || c == '\\') {
      char esc[2] = {'\\', (char)c};
      buf_append(b, esc, 2);
    }
    else if (c < 0x20) {
      buf_printf(b, "\\u%04x", c);
    }
    else {
      buf_append(b, (const char *)&c, 1);
    }
  }
  buf_append(b, "\"", 1);
}

static const char *attrib_name(ufbx_element_type type)
{
  switch (type) {
    case UFBX_ELEMENT_MESH:
      return "mesh";
    case UFBX_ELEMENT_LIGHT:
      return "light";
    case UFBX_ELEMENT_CAMERA:
      return "camera";
    case UFBX_ELEMENT_BONE:
      return "bone";
    case UFBX_ELEMENT_EMPTY:
      return "empty";
    default:
      return "other";
  }
}

static FILE *open_utf8(const char *path)
{
#ifdef _WIN32
  int wlen = MultiByteToWideChar(CP_UTF8, 0, path, -1, NULL, 0);
  if (wlen <= 0) {
    return NULL;
  }
  wchar_t *wpath = (wchar_t *)malloc(sizeof(wchar_t) * (size_t)wlen);
  if (!wpath) {
    return NULL;
  }
  MultiByteToWideChar(CP_UTF8, 0, path, -1, wpath, wlen);
  FILE *file = _wfopen(wpath, L"rb");
  free(wpath);
  return file;
#else
  return fopen(path, "rb");
#endif
}

FBXL_EXPORT const char *fbxl_ufbx_version(void)
{
  static char version[32];
  snprintf(version, sizeof(version), "%u.%u.%u", ufbx_version_major(ufbx_source_version),
           ufbx_version_minor(ufbx_source_version), ufbx_version_patch(ufbx_source_version));
  return version;
}

FBXL_EXPORT void fbxl_free(char *data)
{
  free(data);
}

/* Returns a malloc'd JSON string (free with fbxl_free), or NULL with a message in `err`:
 * {"nodes": [{"name", "parent" (index or -1), "root", "attrib", "bone", "helper", "visible", "pos": [x, y, z]}],
 *  "layers": [{"name", "visible", "frozen", "color": [r, g, b], "nodes": [index, ...]}]}
 * Node indices are positions in ufbx's node list (`typed_id`). */
FBXL_EXPORT char *fbxl_read_scene(const char *path, double global_scale, char *err, int err_len)
{
  if (err && err_len > 0) {
    err[0] = '\0';
  }
  FILE *file = open_utf8(path);
  if (!file) {
    if (err && err_len > 0) {
      snprintf(err, (size_t)err_len, "Cannot open file");
    }
    return NULL;
  }

  /* Same options as Blender's importer (fbx_import.cc), plus skipping what the layers do not need. */
  ufbx_load_opts opts = {0};
  opts.filename.data = path;
  opts.filename.length = strlen(path);
  opts.evaluate_skinning = false;
  opts.evaluate_caches = false;
  opts.load_external_files = false;
  opts.clean_skin_weights = true;
  opts.use_blender_pbr_material = true;
  opts.geometry_transform_handling = UFBX_GEOMETRY_TRANSFORM_HANDLING_MODIFY_GEOMETRY;
  opts.pivot_handling = UFBX_PIVOT_HANDLING_ADJUST_TO_ROTATION_PIVOT;
  opts.space_conversion = UFBX_SPACE_CONVERSION_ADJUST_TRANSFORMS;
  opts.target_axes.right = UFBX_COORDINATE_AXIS_POSITIVE_X;
  opts.target_axes.up = UFBX_COORDINATE_AXIS_POSITIVE_Z;
  opts.target_axes.front = UFBX_COORDINATE_AXIS_NEGATIVE_Y;
  opts.target_unit_meters = (ufbx_real)(1.0 / global_scale);
  opts.target_camera_axes.right = UFBX_COORDINATE_AXIS_POSITIVE_X;
  opts.target_camera_axes.up = UFBX_COORDINATE_AXIS_POSITIVE_Y;
  opts.target_camera_axes.front = UFBX_COORDINATE_AXIS_POSITIVE_Z;
  opts.target_light_axes.right = UFBX_COORDINATE_AXIS_POSITIVE_X;
  opts.target_light_axes.up = UFBX_COORDINATE_AXIS_POSITIVE_Y;
  opts.target_light_axes.front = UFBX_COORDINATE_AXIS_POSITIVE_Z;
  opts.ignore_animation = true;
  opts.ignore_embedded = true;

  ufbx_error error;
  ufbx_scene *scene = ufbx_load_stdio(file, &opts, &error);
  fclose(file);
  if (!scene) {
    if (err && err_len > 0) {
      snprintf(err, (size_t)err_len, "%s", error.description.data);
    }
    return NULL;
  }

  Buf b = {0};
  buf_append(&b, "{\"nodes\":[", 10);
  for (size_t i = 0; i < scene->nodes.count; i++) {
    const ufbx_node *node = scene->nodes.data[i];
    if (i > 0) {
      buf_append(&b, ",", 1);
    }
    buf_append(&b, "{\"name\":", 8);
    buf_json_string(&b, node->name);
    buf_printf(&b,
               ",\"parent\":%d,\"root\":%s,\"attrib\":\"%s\",\"bone\":%s,\"helper\":%s,\"visible\":%s",
               node->parent ? (int)node->parent->typed_id : -1,
               node->is_root ? "true" : "false",
               attrib_name(node->attrib_type),
               node->bone ? "true" : "false",
               node->is_geometry_transform_helper ? "true" : "false",
               node->visible ? "true" : "false");
    buf_printf(&b,
               ",\"pos\":[%.9g,%.9g,%.9g]}",
               (double)node->node_to_world.m03,
               (double)node->node_to_world.m13,
               (double)node->node_to_world.m23);
  }
  buf_append(&b, "],\"layers\":[", 12);
  for (size_t i = 0; i < scene->display_layers.count; i++) {
    const ufbx_display_layer *layer = scene->display_layers.data[i];
    if (i > 0) {
      buf_append(&b, ",", 1);
    }
    buf_append(&b, "{\"name\":", 8);
    buf_json_string(&b, layer->name);
    buf_printf(&b,
               ",\"visible\":%s,\"frozen\":%s,\"color\":[%.9g,%.9g,%.9g],\"nodes\":[",
               layer->visible ? "true" : "false",
               layer->frozen ? "true" : "false",
               (double)layer->ui_color.x,
               (double)layer->ui_color.y,
               (double)layer->ui_color.z);
    for (size_t j = 0; j < layer->nodes.count; j++) {
      buf_printf(&b, j > 0 ? ",%u" : "%u", layer->nodes.data[j]->typed_id);
    }
    buf_append(&b, "]}", 2);
  }
  buf_append(&b, "]}", 2);
  ufbx_free_scene(scene);

  if (b.failed) {
    free(b.data);
    if (err && err_len > 0) {
      snprintf(err, (size_t)err_len, "Out of memory");
    }
    return NULL;
  }
  return b.data;
}
