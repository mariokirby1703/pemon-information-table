#!/usr/bin/env python3
"""Startet den Pemon-Builder aus dem Projektordner."""

from pathlib import Path
import runpy


SCRIPT = Path(__file__).resolve().parent / "src" / "assets" / "pemon-create.py"
runpy.run_path(str(SCRIPT), run_name="__main__")
