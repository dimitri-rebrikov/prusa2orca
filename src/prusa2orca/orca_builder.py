"""
Build OrcaSlicer JSON profiles from resolved PrusaSlicer parameters.

Generates user-format JSONs compatible with .orca_printer bundles:
  - printer/*.json       (machine variant)
  - process/*.json       (print profiles)
  - filament/*.json      (filament profiles)

All use "from": "User" format — importable via Import Configs.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mapper import (
    FILAMENT_PARAM_MAP,
    PRINT_PARAM_MAP,
    PRINTER_PARAM_MAP,
    convert_value,
)
from .models import PrusaSection, SectionType
from .parser import PrusaSection, resolve_inherits
from .remote import get_orca_template

log = logging.getLogger(__name__)

# Orca version for user preset compatibility
ORCA_VERSION = "2.3.1.10"


def vendor_slug(vendor: str) -> str:
    """Lowercase vendor name without spaces/special chars, for filenames."""
    return "".join(c.lower() for c in vendor if c.isalnum())


def find_printer_model_section(
    sections: Dict[str, PrusaSection],
    printer_model_name: str,
) -> Optional[PrusaSection]:
    """Find the [printer_model:XYZ] section for a given printer model name."""
    for raw_name, section in sections.items():
        if section.section_type != SectionType.PRINTER_MODEL:
            continue
        display_name = section.params.get("name", "")
        if printer_model_name in (display_name, section.profile_name):
            return section
    return None


def find_printer_sections(
    sections: Dict[str, PrusaSection],
    printer_model_key: str,
) -> List[PrusaSection]:
    """Find all [printer:...] sections belonging to a printer model."""
    results = []
    for raw_name, section in sections.items():
        if section.section_type != SectionType.PRINTER:
            continue
        resolved = resolve_inherits(section, sections)
        pm = resolved.get("printer_model", "")
        if pm == printer_model_key:
            results.append(section)
    return results


def _strip_vendor_prefix(name: str, vendor: str) -> str:
    """Remove leading vendor prefix from a display name if present."""
    prefix = f"{vendor} "
    if name.startswith(prefix):
        return name[len(prefix):]
    return name


def _user_meta(name: str, settings_key: str, inherits: str = "") -> Dict[str, str]:
    """Common user-format header fields."""
    return {
        "from": "User",
        "name": name,
        settings_key: name,
        "is_custom_defined": "0",
        "version": ORCA_VERSION,
        "inherits": inherits,
    }


def build_machine_json(
    resolved_params: Dict[str, str],
    printer_model_name: str,
    vendor: str = "Custom",
) -> Dict[str, Any]:
    """
    Build a machine variant dict (printer JSON) from resolved printer params.

    User format: no type, no setting_id, no instantiation.
    Uses the actual resolved values as a standalone profile.
    """
    nozzle = resolved_params.get("nozzle_diameter", "0.4")
    display_name = _strip_vendor_prefix(printer_model_name, vendor)
    name = f"{vendor} {display_name} {nozzle} nozzle"

    data = _user_meta(name, "printer_settings_id", inherits="")

    # Apply Orca machine template defaults as fallback
    tmpl = get_orca_template(vendor, "machine", "fdm_machine_common")
    if tmpl:
        for k, v in tmpl.items():
            data.setdefault(k, v)

    # Orca-specific fields
    data["printer_model"] = f"{vendor} {display_name}"
    data["printer_structure"] = "i3"
    data["printer_technology"] = "FFF"
    data["printer_variant"] = nozzle
    data["default_print_profile"] = ""
    data["default_filament_profile"] = [f"{vendor} Generic PLA"]
    data["nozzle_diameter"] = [nozzle]
    data["nozzle_type"] = "undefine"
    data["auxiliary_fan"] = "0"
    data["scan_first_layer"] = "0"
    data["silent_mode"] = "0"
    data["single_extruder_multi_material"] = "1"
    data["wipe"] = ["1"]

    # Map printer params
    for prusa_key, orca_key in PRINTER_PARAM_MAP.items():
        if prusa_key in resolved_params:
            val = resolved_params[prusa_key]
            array_keys = (
                "machine_max_acceleration_x", "machine_max_acceleration_y",
                "machine_max_acceleration_z", "machine_max_acceleration_e",
                "machine_max_acceleration_extruding", "machine_max_acceleration_retracting",
                "machine_max_acceleration_travel",
                "machine_max_feedrate_x", "machine_max_feedrate_y",
                "machine_max_feedrate_z", "machine_max_feedrate_e",
                "machine_max_jerk_x", "machine_max_jerk_y",
                "machine_max_jerk_z", "machine_max_jerk_e",
                "machine_min_extruding_rate", "machine_min_travel_rate",
                "retract_length", "retract_speed", "deretract_speed",
                "retract_lift", "retract_before_travel", "retract_before_wipe",
                "retract_restart_extra", "retract_length_toolchange",
                "retract_restart_extra_toolchange", "wipe",
                "min_layer_height", "max_layer_height", "nozzle_diameter",
            )
            if prusa_key in array_keys:
                data[orca_key] = [val]
            else:
                data[orca_key] = val

    # Bed shape
    if "bed_shape" in resolved_params:
        data["printable_area"] = [x.strip() for x in resolved_params["bed_shape"].split(",")]

    # Gcode with placeholder conversion
    for gcode_key in ("start_gcode", "end_gcode", "before_layer_gcode",
                       "toolchange_gcode", "pause_print_gcode"):
        orca_key = {
            "start_gcode": "machine_start_gcode",
            "end_gcode": "machine_end_gcode",
            "before_layer_gcode": "layer_change_gcode",
            "toolchange_gcode": "change_filament_gcode",
            "pause_print_gcode": "machine_pause_gcode",
        }[gcode_key]
        if gcode_key in resolved_params:
            data[orca_key] = convert_value(gcode_key, resolved_params[gcode_key])

    return data


def build_process_json(
    resolved_params: Dict[str, str],
    section_name: str,
    printer_display_name: str,
    vendor: str = "Custom",
) -> Dict[str, Any]:
    """
    Build a process dict from resolved params.

    User format: no type, setting_id, instantiation, compatible_printers.
    """
    nozzle = resolved_params.get("nozzle_diameter", resolved_params.get("printer_variant", "0.4"))
    layer_h = resolved_params.get("layer_height", "0.20")
    quality_name = _map_quality_name(section_name, layer_h)

    printer_short = _strip_vendor_prefix(printer_display_name, vendor)
    name = f"{vendor} {printer_short} {nozzle} - {quality_name}"

    data = _user_meta(name, "print_settings_id", inherits="")

    # Apply Orca process template defaults as fallback
    tmpl = get_orca_template(vendor, "process", "fdm_process_common")
    if tmpl:
        for k, v in tmpl.items():
            data.setdefault(k, v)

    for prusa_key, orca_key in PRINT_PARAM_MAP.items():
        if prusa_key in resolved_params:
            data[orca_key] = convert_value(prusa_key, resolved_params[prusa_key])

    for prusa_key, orca_key in FILAMENT_PARAM_MAP.items():
        if prusa_key in resolved_params and orca_key not in data:
            data[orca_key] = convert_value(prusa_key, resolved_params[prusa_key])

    # User profiles have inherits="" — every Orca field must be explicit.
    # Prusa only has default_acceleration/bridge_acceleration;
    # expand to all Orca per-move acceleration fields.
    accel = data.get("default_acceleration")
    if accel:
        for acc_key in (
            "inner_wall_acceleration", "outer_wall_acceleration",
            "initial_layer_acceleration", "top_surface_acceleration",
            "sparse_infill_acceleration", "internal_solid_infill_acceleration",
        ):
            if acc_key not in data:
                data[acc_key] = accel

    return data


def build_filament_json(
    resolved_params: Dict[str, str],
    section_name: str,
    printer_display_name: str,
    vendor: str = "Custom",
) -> Dict[str, Any]:
    """Build a filament dict from resolved params."""
    filament_type = resolved_params.get("filament_type", "PLA")
    printer_short = _strip_vendor_prefix(printer_display_name, vendor)
    # Use original Prusa filament name (before @), prefix with printer
    original = section_name.split("@")[0].strip() if "@" in section_name else section_name
    name = f"{vendor} {printer_short} - {original}"

    data = _user_meta(name, "filament_settings_id",
                       inherits=f"fdm_filament_{filament_type.lower()}")

    for prusa_key, orca_key in FILAMENT_PARAM_MAP.items():
        if prusa_key in resolved_params:
            val = convert_value(prusa_key, resolved_params[prusa_key])
            array_keys = (
                "bed_temperature", "first_layer_bed_temperature",
                "temperature", "first_layer_temperature",
                "filament_type", "filament_density", "filament_diameter",
                "filament_cost", "filament_max_volumetric_speed",
                "extrusion_multiplier",
            )
            if prusa_key in array_keys:
                data[orca_key] = [val]
            else:
                data[orca_key] = val

    return data


def build_bundle_structure(
    printer_name: str,
    printer_files: List[str],
    process_files: List[str],
    filament_files: List[str],
) -> Dict[str, Any]:
    """Build bundle_structure.json manifest."""
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in printer_name if c.isalnum() or c in " _-")
    return {
        "bundle_id": f"_{safe_name}_{ts}",
        "bundle_type": "printer config bundle",
        "printer_config": printer_files,
        "process_config": process_files,
        "filament_config": filament_files,
        "version": ORCA_VERSION,
    }


def _map_quality_name(section_name: str, layer_height: str) -> str:
    """Map Prusa quality naming to Orca naming convention."""
    mapping = {
        "0.06": "0.06mm SuperDetail",
        "0.08": "0.08mm SuperDetail",
        "0.10": "0.10mm HighDetail",
        "0.12": "0.12mm Detail",
        "0.16": "0.16mm Optimal",
        "0.20": "0.20mm Standard",
        "0.24": "0.24mm Draft",
        "0.28": "0.28mm SuperDraft",
        "0.32": "0.32mm ExtraDraft",
        "0.36": "0.36mm Chunky",
        "0.44": "0.44mm SuperChunky",
    }
    lh = layer_height.strip()
    if lh in mapping:
        return mapping[lh]

    upper = section_name.upper()
    if "OPTIMAL" in upper:
        return f"{lh}mm Optimal"
    if ("SUPER" in upper and "DETAIL" in upper) or "ULTRADETAIL" in upper:
        return f"{lh}mm SuperDetail"
    if "HIGH" in upper and "DETAIL" in upper:
        return f"{lh}mm HighDetail"
    if "DETAIL" in upper:
        return f"{lh}mm Detail"
    if "SUPER" in upper and "DRAFT" in upper:
        return f"{lh}mm SuperDraft"
    if "DRAFT" in upper:
        return f"{lh}mm Draft"
    if "NORMAL" in upper or "STANDARD" in upper:
        return f"{lh}mm Standard"
    if "SUPER" in upper and "CHUNKY" in upper:
        return f"{lh}mm SuperChunky"
    if "CHUNKY" in upper:
        return f"{lh}mm Chunky"

    return f"{lh}mm Standard"
