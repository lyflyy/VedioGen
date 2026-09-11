"""Run with Blender's bundled Python, not the API interpreter.

Imports a supplied GLB or explicitly creates a non-vehicle calibration scene.
No production motorcycle asset or fallback geometry is bundled.
"""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def material(name, color, metallic=0.0):
    value = bpy.data.materials.new(name)
    value.use_nodes = True
    shader = value.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = 0.3
    return value


def calibration():
    # Asymmetric blocks make camera movement and framing measurable without a substitute vehicle.
    for index, (location, scale, color) in enumerate([
        ((-0.7, 0, 0.45), (0.4, 0.35, 0.45), (0.65, 0.08, 0.06)),
        ((0.5, 0.15, 0.8), (0.3, 0.3, 0.8), (0.03, 0.42, 0.32)),
        ((0, -0.45, 0.22), (1.0, 0.15, 0.22), (0.12, 0.22, 0.7)),
    ]):
        bpy.ops.mesh.primitive_cube_add(size=2, location=location)
        obj = bpy.context.object
        obj.name = f"CALIBRATION_ONLY_{index}"
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bevel = obj.modifiers.new("Edge bevel", "BEVEL")
        bevel.width = 0.04
        bevel.segments = 3
        obj.data.materials.append(material(obj.name, color, 0.15))


def bounds(objects):
    return [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]


def aim(obj, point):
    obj.rotation_euler = (point - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--asset", type=Path)
    source.add_argument("--calibration", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=540)
    parser.add_argument("--height", type=int, default=960)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if not (128 <= args.width <= 1920 and 128 <= args.height <= 1920 and 24 <= args.frames <= 300 and args.fps in (24, 30)):
        raise ValueError("Unsupported diagnostic render dimensions or frame count")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; existing evidence is not overwritten")
    if args.asset and (not args.asset.is_file() or args.asset.suffix.lower() != ".glb"):
        raise ValueError("An existing GLB asset is required; no substitute geometry is used")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.calibration:
        calibration()
    else:
        bpy.ops.import_scene.gltf(filepath=str(args.asset.resolve()))
    imported = list(bpy.context.scene.objects)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Asset has no renderable meshes")
    for obj in imported:
        obj.animation_data_clear()
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    corners = bounds(meshes)
    low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    extent = max(high - low)
    if not math.isfinite(extent) or extent < 0.00001:
        raise ValueError("Asset has invalid dimensions")
    center = (low + high) / 2
    root = bpy.data.objects.new("Asset normalization", None)
    bpy.context.collection.objects.link(root)
    for obj in list(bpy.context.scene.objects):
        if obj != root and not obj.parent:
            obj.parent = root
    scale = 2.5 / extent
    root.scale = (scale,) * 3
    root.location = (-center.x * scale, -center.y * scale, -low.z * scale)
    bpy.context.view_layer.update()
    corners = bounds(meshes)
    # Use the box midpoint instead of vertex density to center heterogeneous multi-part assets.
    center = Vector(tuple((min(p[i] for p in corners) + max(p[i] for p in corners)) / 2 for i in range(3)))
    radius = max((p - center).length for p in corners)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 32
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("Neutral studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.18, 0.18, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.015))
    bpy.context.object.data.materials.append(material("Studio floor", (0.18, 0.19, 0.2)))
    for name, position, power, size in [
        ("Key", (3, -4, 6), 1500, 5), ("Fill", (-4, -1, 3), 1000, 4),
        ("Rim", (1, 4, 5), 1700, 4),
    ]:
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = power, "DISK", size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = position
        aim(obj, center)
    data = bpy.data.cameras.new("Orbit camera")
    data.lens = 50
    camera = bpy.data.objects.new("Orbit camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    bpy.context.view_layer.update()
    frame = data.view_frame(scene=scene)
    half_angle = min(math.atan(abs(frame[0].x / frame[0].z)), math.atan(abs(frame[0].y / frame[0].z)))
    distance = radius / math.sin(half_angle) * 1.12
    elevation = math.radians(15)
    data.clip_end = max(100, distance * 10)
    report = {"blenderVersion": bpy.app.version_string, "engine": scene.render.engine,
              "calibrationOnly": args.calibration, "subjectConfirmed": False,
              "asset": str(args.asset.resolve()) if args.asset else None,
              "assetSha256": hashlib.sha256(args.asset.read_bytes()).hexdigest() if args.asset else None,
              "width": args.width, "height": args.height, "fps": args.fps,
              "frames": args.frames, "meshCount": len(meshes), "orbitDegrees": 360, "samples": []}
    scene.frame_start, scene.frame_end = 1, args.frames
    for index in range(args.frames):
        angle = math.radians(-45 + 360 * index / (args.frames - 1))
        camera.location = center + Vector((distance * math.cos(angle) * math.cos(elevation),
                                           distance * math.sin(angle) * math.cos(elevation), distance * math.sin(elevation)))
        aim(camera, center)
        bpy.context.view_layer.update()
        projected = [world_to_camera_view(scene, camera, point) for point in corners]
        if any(p.z <= 0 or not 0.02 <= p.x <= 0.98 or not 0.02 <= p.y <= 0.98 for p in projected):
            raise ValueError(f"Asset would be clipped at frame {index + 1}")
        camera.keyframe_insert("location", frame=index + 1)
        camera.keyframe_insert("rotation_euler", frame=index + 1)
        report["samples"].append({"frame": index + 1, "angleDegrees": -45 + 360 * index / (args.frames - 1),
                                  "position": list(camera.location), "allBoundsInside": True})
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "orbit.blend"))
    for frame_number in range(1, args.frames + 1):
        scene.frame_set(frame_number)
        scene.render.filepath = str(output / f"frame-{frame_number:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"VEDIOGEN_PROGRESS {frame_number}/{args.frames}", flush=True)
    report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    (output / "orbit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
