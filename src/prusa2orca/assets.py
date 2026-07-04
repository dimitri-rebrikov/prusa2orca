"""
Asset extraction: bed models (STL), textures (SVG), and thumbnails (PNG).

Downloads or copies from PrusaSlicer source to OrcaSlicer naming convention.
Vendor-agnostic: works with any PrusaSlicer vendor folder on GitHub.
"""

from __future__ import annotations

import io
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Optional

from .models import PrusaSection, SectionType

log = logging.getLogger(__name__)

# PrusaSlicer raw file base URL (no trailing slash)
PRUSA_RAW_BASE = "https://raw.githubusercontent.com/prusa3d/PrusaSlicer/master/resources/profiles"


def find_assets_for_printer(
    sections: Dict[str, PrusaSection],
    printer_model_name: str,
) -> Dict[str, Optional[str]]:
    """
    Find asset filenames for a printer model from the [printer_model:] section.

    Returns dict with keys: bed_model, bed_texture, thumbnail
    """
    for raw_name, section in sections.items():
        if section.section_type != SectionType.PRINTER_MODEL:
            continue
        display_name = section.params.get("name", "")
        profile_name = section.profile_name
        if printer_model_name not in (display_name, profile_name):
            continue

        bed_model = section.params.get("bed_model", "")
        bed_texture = section.params.get("bed_texture", "")
        thumbnail = f"{profile_name}_thumbnail.png"

        return {
            "bed_model": bed_model or None,
            "bed_texture": bed_texture or None,
            "thumbnail": thumbnail,
        }

    return {}


def make_orca_asset_name(prusa_name: str, printer_prefix: str, vendor: str = "") -> str:
    """
    Convert Prusa asset name to Orca convention.

    Examples:
      cr5pro_bed.stl → creality_cr5pro_buildplate_model.stl
      cr5pro.svg     → creality_cr5pro_buildplate_texture.svg
      CR5PROH_thumbnail.png → Creality CR-5 Pro H_cover.png
    """
    vs = "".join(c.lower() for c in vendor if c.isalnum()) if vendor else ""

    if prusa_name.endswith("_bed.stl") or prusa_name.endswith("_bed.STL"):
        base = prusa_name.rsplit("_bed.", 1)[0]
        prefix = f"{vs}_" if vs else ""
        return f"{prefix}{base}_buildplate_model.stl"
    elif prusa_name.endswith(".svg"):
        base = prusa_name.rsplit(".svg", 1)[0]
        prefix = f"{vs}_" if vs else ""
        return f"{prefix}{base}_buildplate_texture.svg"
    elif prusa_name.endswith("_thumbnail.png"):
        return f"{printer_prefix}_cover.png"
    return prusa_name


def download_asset(
    prusa_filename: str,
    vendor_dir: str,
    output_dir: Path,
    printer_prefix: str = "",
    vendor: str = "",
) -> Optional[Path]:
    """
    Download an asset from PrusaSlicer's GitHub repo and save with Orca naming.

    vendor_dir: subdirectory name in PrusaSlicer's profiles (e.g. 'Creality').
    Returns the output path, or None on failure.
    """
    orca_name = make_orca_asset_name(prusa_filename, printer_prefix, vendor) if printer_prefix else prusa_filename
    output_path = output_dir / orca_name

    if output_path.exists():
        log.info(f"  Already exists: {output_path.name}")
        return output_path

    url = f"{PRUSA_RAW_BASE}/{vendor_dir}/{prusa_filename}"
    log.info(f"  Downloading {url} → {output_path.name}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "prusa2orca/0.1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                log.warning(f"  HTTP {response.status} for {url}")
                return None
            data = response.read()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            log.info(f"  Saved {len(data)} bytes")
            return output_path
    except urllib.error.HTTPError as e:
        log.warning(f"  HTTP {e.code} for {url}")
        return None
    except Exception as e:
        log.warning(f"  Failed to download {url}: {e}")
        return None


def generate_bed_texture(
    output_path: Path,
    width_mm: float = 295,
    height_mm: float = 220,
) -> Path:
    """Generate an Orca-style bed texture SVG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg id="a" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_mm} {height_mm}">
  <defs>
    <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
      <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#d0d0d0" stroke-width="0.15"/>
    </pattern>
    <pattern id="grid-large" width="50" height="50" patternUnits="userSpaceOnUse">
      <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#a0a0a0" stroke-width="0.3"/>
    </pattern>
  </defs>
  <rect x="0" y="0" width="{width_mm}" height="{height_mm}" fill="#3a3a3a"/>
  <rect x="5" y="5" width="{width_mm-10}" height="{height_mm-10}" fill="url(#grid)" stroke="#c0c0c0" stroke-width="0.5"/>
  <rect x="5" y="5" width="{width_mm-10}" height="{height_mm-10}" fill="url(#grid-large)"/>
  <circle cx="15" cy="15" r="4" fill="#2a2a2a" stroke="#808080" stroke-width="0.5"/>
  <circle cx="15" cy="15" r="1.5" fill="#1a1a1a"/>
  <circle cx="{width_mm-15}" cy="15" r="4" fill="#2a2a2a" stroke="#808080" stroke-width="0.5"/>
  <circle cx="{width_mm-15}" cy="15" r="1.5" fill="#1a1a1a"/>
  <circle cx="15" cy="{height_mm-15}" r="4" fill="#2a2a2a" stroke="#808080" stroke-width="0.5"/>
  <circle cx="15" cy="{height_mm-15}" r="1.5" fill="#1a1a1a"/>
  <circle cx="{width_mm-15}" cy="{height_mm-15}" r="4" fill="#2a2a2a" stroke="#808080" stroke-width="0.5"/>
  <circle cx="{width_mm-15}" cy="{height_mm-15}" r="1.5" fill="#1a1a1a"/>
  <circle cx="{width_mm/2}" cy="{height_mm/2}" r="4" fill="#2a2a2a" stroke="#808080" stroke-width="0.5"/>
  <circle cx="{width_mm/2}" cy="{height_mm/2}" r="1.5" fill="#1a1a1a"/>
</svg>"""

    output_path.write_text(svg)
    log.info(f"  Generated SVG texture: {output_path.name}")
    return output_path
