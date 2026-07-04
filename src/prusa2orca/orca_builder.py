"""
Build OrcaSlicer JSON profiles from resolved PrusaSlicer parameters.

Generates:
  - machine_model JSON (printer model registration)
  - machine JSON (printer variant with nozzle)
  - process JSON (print profiles)
  - filament JSON (filament profiles)

Vendor-agnostic: works with any PrusaSlicer .ini (Creality, Voron, Anycubic, etc.)
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
    get_parameter_map,
    sanitize_profile_name,
)
from .models import OrcaProfile, PrusaSection, SectionType
from .parser import PrusaSection, resolve_inherits

log = logging.getLogger(__name__)

# Base62 charset (OrcaSlicer-style)
_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _base62_encode(num: int) -> str:
    if num == 0:
        return _BASE62[0]
    result = []
    while num > 0:
        result.append(_BASE62[num % 62])
        num //= 62
    return "".join(reversed(result))


def make_setting_id(vendor: str, ptype: str, name: str) -> str:
    """Deterministic OrcaSlicer setting_id from vendor/type/name."""
    ns = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    id_str = f"{vendor}/{ptype}/{name}"
    hex_id = uuid.uuid5(ns, id_str).hex[:16]
    return _base62_encode(int(hex_id, 16))


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


def build_machine_model_json(
    prusa_section: PrusaSection,
    vendor: str = "Custom",
) -> OrcaProfile:
    """Build a machine_model JSON from a [printer_model:XYZ] section."""
    params = prusa_section.params
    family = params.get("family", vendor)
    name = params.get("name", "")
    vs = vendor_slug(vendor)
    pk = prusa_section.profile_name.lower()

    data = {
        "type": "machine_model",
        "name": name,
        "model_id": f"{vs}-{prusa_section.profile_name}",
        "nozzle_diameter": params.get("variants", "0.4"),
        "machine_tech": params.get("technology", "FFF"),
        "family": family,
        "bed_model": f"{vs}_{pk}_buildplate_model.stl",
        "bed_texture": f"{vs}_{pk}_buildplate_texture.svg",
        "hotend_model": "",
        "default_materials": params.get("default_materials", ""),
    }

    return OrcaProfile(
        type="machine_model",
        name=name,
        from_field="system",
        instantiation="false",
        data=data,
    )


def build_machine_json(
    resolved_params: Dict[str, str],
    printer_model_name: str,
    vendor: str = "Custom",
    inherits_target: str = "fdm_machine_common",
) -> OrcaProfile:
    """
    Build a machine variant JSON from resolved printer params.

    inherits_target: the Orca base profile to inherit from.
      - 'fdm_machine_common' — works for any vendor (universal base)
      - 'fdm_creality_common' — Creality-specific defaults
      Pass via CLI --machine-inherits.
    """
    nozzle = resolved_params.get("nozzle_diameter", "0.4")
    display_name = _strip_vendor_prefix(printer_model_name, vendor)
    name = f"{vendor} {display_name} {nozzle} nozzle"

    data: Dict[str, Any] = {
        "type": "machine",
        "name": name,
        "inherits": inherits_target,
        "from": "system",
        "setting_id": make_setting_id(vendor, "machine", name),
        "instantiation": "true",
        "printer_model": f"{vendor} {display_name}",
        "printer_structure": "i3",
        "default_print_profile": f"0.20mm Standard @{vendor} {display_name} {nozzle}",
    }

    # Map printer params
    for prusa_key, orca_key in PRINTER_PARAM_MAP.items():
        if prusa_key in resolved_params:
            val = resolved_params[prusa_key]
            if prusa_key in ("nozzle_diameter",):
                data[orca_key] = [val]
            elif prusa_key in (
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
                "min_layer_height", "max_layer_height",
            ):
                data[orca_key] = [val]
            else:
                data[orca_key] = val

    # Bed shape → printable_area list
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

    data["default_filament_profile"] = [f"{vendor} Generic PLA"]
    data["scan_first_layer"] = "0"
    data["nozzle_type"] = "undefine"
    data["auxiliary_fan"] = "0"

    return OrcaProfile(
        type="machine",
        name=name,
        inherits=inherits_target,
        from_field="system",
        setting_id=make_setting_id(vendor, "machine", name),
        data=data,
    )


def build_process_json(
    resolved_params: Dict[str, str],
    section_name: str,
    printer_display_name: str,
    vendor: str = "Custom",
    inherits_target: str = "fdm_process_common",
) -> OrcaProfile:
    """
    Build a process (print profile) JSON from resolved params.

    inherits_target: the Orca base process to inherit from.
      - 'fdm_process_common' — universal
      - 'fdm_process_creality_common' — Creality-specific
    """
    nozzle = resolved_params.get("nozzle_diameter", resolved_params.get("printer_variant", "0.4"))
    layer_h = resolved_params.get("layer_height", "0.20")
    quality_name = _map_quality_name(section_name, layer_h)

    printer_short = _strip_vendor_prefix(printer_display_name, vendor)
    name = f"{quality_name} @{vendor} {printer_short} {nozzle}"

    data: Dict[str, Any] = {
        "type": "process",
        "name": name,
        "inherits": inherits_target,
        "from": "system",
        "setting_id": make_setting_id(vendor, "process", name),
        "instantiation": "true",
    }

    for prusa_key, orca_key in PRINT_PARAM_MAP.items():
        if prusa_key in resolved_params:
            val = convert_value(prusa_key, resolved_params[prusa_key])
            data[orca_key] = val

    for prusa_key, orca_key in FILAMENT_PARAM_MAP.items():
        if prusa_key in resolved_params and orca_key not in data:
            data[orca_key] = convert_value(prusa_key, resolved_params[prusa_key])

    nozzle_for_name = resolved_params.get("nozzle_diameter", resolved_params.get("printer_variant", "0.4"))
    printer_variant_name = f"{vendor} {printer_short} {nozzle_for_name} nozzle"
    data["compatible_printers"] = [printer_variant_name]

    return OrcaProfile(
        type="process",
        name=name,
        inherits=inherits_target,
        from_field="system",
        setting_id=make_setting_id(vendor, "process", name),
        data=data,
    )


def build_filament_json(
    resolved_params: Dict[str, str],
    section_name: str,
    printer_display_name: str,
    vendor: str = "Custom",
) -> OrcaProfile:
    """Build a filament JSON from resolved params."""
    filament_type = resolved_params.get("filament_type", "PLA")
    printer_short = _strip_vendor_prefix(printer_display_name, vendor)
    name = f"{vendor} Generic {filament_type} @{vendor} {printer_short}"

    data: Dict[str, Any] = {
        "type": "filament",
        "name": name,
        "inherits": f"fdm_filament_{filament_type.lower()}",
        "from": "system",
        "setting_id": make_setting_id(vendor, "filament", name),
        "instantiation": "true",
    }

    for prusa_key, orca_key in FILAMENT_PARAM_MAP.items():
        if prusa_key in resolved_params:
            val = convert_value(prusa_key, resolved_params[prusa_key])
            if prusa_key in (
                "bed_temperature", "first_layer_bed_temperature",
                "temperature", "first_layer_temperature",
                "filament_type", "filament_density", "filament_diameter",
                "filament_cost", "filament_max_volumetric_speed",
                "extrusion_multiplier",
            ):
                data[orca_key] = [val]
            else:
                data[orca_key] = val

    data["compatible_printers"] = [f"{vendor} {printer_short} 0.4 nozzle"]

    return OrcaProfile(
        type="filament",
        name=name,
        inherits=f"fdm_filament_{filament_type.lower()}",
        from_field="system",
        setting_id=make_setting_id(vendor, "filament", name),
        data=data,
    )


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
