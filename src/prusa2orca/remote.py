"""
Remote operations: fetch vendor INI files and assets from PrusaSlicer's GitHub.
No local .ini files required — everything is downloaded on demand.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

PRUSA_API = "https://api.github.com/repos/prusa3d/PrusaSlicer/contents/resources/profiles"
PRUSA_RAW = "https://raw.githubusercontent.com/prusa3d/PrusaSlicer/master/resources/profiles"

# Cache directory for downloaded .ini files
CACHE_DIR = Path.home() / ".cache" / "prusa2orca"


def _github_get(url: str) -> Optional[dict]:
    """Fetch JSON from GitHub API."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "prusa2orca/0.1",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.warning(f"GitHub API error: {e}")
        return None


def _raw_get(url: str) -> Optional[str]:
    """Fetch raw text from GitHub."""
    req = urllib.request.Request(url, headers={"User-Agent": "prusa2orca/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        log.warning(f"Raw download error: {e}")
        return None


def list_vendors() -> List[str]:
    """List all available printer vendors from PrusaSlicer's GitHub."""
    data = _github_get(PRUSA_API)
    if not data:
        log.error("Could not fetch vendor list from GitHub")
        return []

    vendors = []
    for item in data:
        name = item.get("name", "")
        if name.endswith(".ini") and item.get("type") == "file":
            vendors.append(name.replace(".ini", ""))
    return sorted(vendors)


def list_printers(vendor: str) -> List[Dict[str, str]]:
    """
    List all printer models for a vendor.

    Returns list of dicts with keys: internal_name, display_name, family, variants
    """
    ini_content = _raw_get(f"{PRUSA_RAW}/{vendor}.ini")
    if not ini_content:
        log.error(f"Could not fetch {vendor}.ini from GitHub")
        return []

    printers = []
    section_pattern = re.compile(r"^\[printer_model:(\w+)\]", re.MULTILINE)
    name_pattern = re.compile(r"^name\s*=\s*(.+)", re.MULTILINE)
    family_pattern = re.compile(r"^family\s*=\s*(\w+)", re.MULTILINE)
    variants_pattern = re.compile(r"^variants\s*=\s*(.+)", re.MULTILINE)

    for m in section_pattern.finditer(ini_content):
        key = m.group(1)
        # Extract fields around this section
        section_start = m.start()
        section_end = ini_content.find("\n[", section_start + 1)
        if section_end == -1:
            section_end = len(ini_content)
        block = ini_content[section_start:section_end]

        name_m = re.search(r"^name\s*=\s*(.+)", block, re.MULTILINE)
        family_m = re.search(r"^family\s*=\s*(\w+)", block, re.MULTILINE)
        variants_m = re.search(r"^variants\s*=\s*(.+)", block, re.MULTILINE)

        printers.append({
            "internal_name": key,
            "display_name": name_m.group(1).strip() if name_m else key,
            "family": family_m.group(1).strip() if family_m else "",
            "variants": variants_m.group(1).strip() if variants_m else "0.4",
        })

    return printers


def get_ini(vendor: str, force_refetch: bool = False) -> Optional[Path]:
    """
    Download a vendor .ini file from PrusaSlicer's GitHub and cache it locally.

    Returns the path to the cached file, or None on failure.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{vendor}.ini"

    if cache_path.exists() and not force_refetch:
        log.debug(f"Using cached {cache_path}")
        return cache_path

    content = _raw_get(f"{PRUSA_RAW}/{vendor}.ini")
    if not content:
        log.error(f"Failed to download {vendor}.ini")
        return None

    cache_path.write_text(content, encoding="utf-8")
    log.info(f"Downloaded {vendor}.ini ({len(content)} bytes)")
    return cache_path


def get_vendor_dir(vendor: str) -> Optional[str]:
    """
    Get the actual vendor directory name from PrusaSlicer.
    Some vendors use different casing or naming.
    Returns the directory name as it appears on GitHub.
    """
    data = _github_get(PRUSA_API)
    if not data:
        return vendor
    for item in data:
        if item.get("type") == "dir" and item["name"].lower() == vendor.lower():
            return item["name"]
    # Check if there's a subfolder with the vendor's profiles
    for item in data:
        if item.get("type") == "dir" and item["name"].lower() == vendor.lower():
            return item["name"]
    return vendor


def get_asset_url(vendor: str, filename: str) -> str:
    """Get the raw GitHub URL for a vendor asset file."""
    vendor_dir = get_vendor_dir(vendor)
    return f"{PRUSA_RAW}/{vendor_dir}/{filename}"
