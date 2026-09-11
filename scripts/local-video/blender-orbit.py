"""Compatibility entry point for the shared Blender scene script."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[2] / "services/api/src/vediogen_api/blender_scene.py"), run_name="__main__")
