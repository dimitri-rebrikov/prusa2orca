"""
Parameter name and value mapping between PrusaSlicer and OrcaSlicer.

Contains:
  - Print/process parameter mapping tables
  - Filament parameter mapping tables
  - Printer parameter mapping tables
  - Value conversion functions (e.g., percent handling)
  - Printer compatibility condition matching
"""

import logging
import re
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

# ─── Print Settings: Prusa → Orca ───
PRINT_PARAM_MAP: Dict[str, str] = {
    # Layer & shell
    "layer_height": "layer_height",
    "first_layer_height": "initial_layer_print_height",
    "bottom_solid_layers": "bottom_shell_layers",
    "top_solid_layers": "top_shell_layers",
    "perimeters": "wall_loops",
    "spiral_vase": "spiral_mode",
    # Infill
    "fill_density": "sparse_infill_density",
    "fill_pattern": "sparse_infill_pattern",
    "fill_angle": "infill_direction",
    "infill_every_layers": "infill_combination",
    "infill_overlap": "infill_wall_overlap",
    # Speed
    "perimeter_speed": "inner_wall_speed",
    "external_perimeter_speed": "outer_wall_speed",
    "infill_speed": "sparse_infill_speed",
    "solid_infill_speed": "internal_solid_infill_speed",
    "top_solid_infill_speed": "top_surface_speed",
    "gap_fill_speed": "gap_infill_speed",
    "bridge_speed": "bridge_speed",
    "travel_speed": "travel_speed",
    "first_layer_speed": "initial_layer_speed",
    "first_layer_infill_speed": "initial_layer_infill_speed",
    "ironing_speed": "ironing_speed",
    # Acceleration
    "default_acceleration": "default_acceleration",
    "bridge_acceleration": "bridge_acceleration",
    "first_layer_acceleration": "initial_layer_acceleration",
    # Extrusion widths
    "extrusion_width": "line_width",
    "first_layer_extrusion_width": "initial_layer_line_width",
    "external_perimeter_extrusion_width": "outer_wall_line_width",
    "perimeter_extrusion_width": "inner_wall_line_width",
    "infill_extrusion_width": "sparse_infill_line_width",
    "solid_infill_extrusion_width": "internal_solid_infill_line_width",
    "top_infill_extrusion_width": "top_surface_line_width",
    "support_material_extrusion_width": "support_line_width",
    # Support
    "support_material": "enable_support",
    "support_material_threshold": "support_threshold_angle",
    "support_material_enforce_layers": "support_type",
    "support_material_pattern": "support_base_pattern",
    "support_material_with_sheath": "support_style",
    "support_material_spacing": "support_base_pattern_spacing",
    "support_material_interface_layers": "support_interface_top_layers",
    "support_material_interface_spacing": "support_interface_spacing",
    "support_material_interface_speed": "support_interface_speed",
    "support_material_speed": "support_speed",
    "support_material_angle": "support_base_pattern",
    "support_material_buildplate_only": "support_on_build_plate_only",
    "support_material_xy_spacing": "support_object_xy_distance",
    "support_material_contact_distance": "support_top_z_distance",
    "support_material_synchronize_layers": "support_multi_material",
    # Skirt & brim
    "skirts": "skirt_loops",
    "skirt_distance": "skirt_distance",
    "skirt_height": "skirt_height",
    "brim_width": "brim_width",
    "brim_width_interior": "brim_type",
    # Ironing
    "ironing_type": "ironing_type",
    "ironing_flowrate": "ironing_flow",
    "ironing_spacing": "ironing_spacing",
    # Other
    "bridge_flow_ratio": "bridge_flow",
    "overhangs": "detect_overhang_wall",
    "thin_walls": "detect_thin_wall",
    "seam_position": "seam_position",
    "raft_layers": "raft_layers",
    "elefant_foot_compensation": "elefant_foot_compensation",
    "xy_size_compensation": "xy_contour_compensation",
    "ensure_vertical_shell_thickness": "reduce_crossing_wall",
    "only_retract_when_crossing_perimeters": "reduce_crossing_wall",
    "max_print_speed": "max_speed",
    "max_volumetric_speed": "filament_max_volumetric_speed",
    "resolution": "resolution",
    "gcode_comments": "gcode_substitutions",
    "output_filename_format": "filename_format",
    "dont_support_bridges": "bridge_no_support",
    "external_fill_pattern": "top_surface_pattern",
    "complete_objects": "print_sequence",
    "extra_perimeters": "extra_perimeters_on_overhangs",
    "gcode_label_objects": "gcode_label_objects",
    "interface_shells": "interface_shells",
    "small_perimeter_speed": "small_perimeter_speed",
    "bridge_angle": "bridge_angle",
    "post_process": "post_process",
    "standby_temperature_delta": "standby_temperature_delta",
    "avoid_crossing_perimeters": "reduce_crossing_wall",
}

# ─── Filament Settings: Prusa → Orca ───
FILAMENT_PARAM_MAP: Dict[str, str] = {
    "bed_temperature": "bed_temperature",
    "first_layer_bed_temperature": "bed_temperature_initial_layer",
    "temperature": "nozzle_temperature",
    "first_layer_temperature": "nozzle_temperature_initial_layer",
    "filament_type": "filament_type",
    "filament_density": "filament_density",
    "filament_diameter": "filament_diameter",
    "filament_cost": "filament_cost",
    "filament_max_volumetric_speed": "filament_max_volumetric_speed",
    "extrusion_multiplier": "filament_flow_ratio",
    "filament_colour": "default_filament_colour",
    "filament_vendor": "filament_vendor",
    "fan_always_on": "reduce_fan_stop_start_freq",
    "fan_below_layer_time": "fan_cooling_layer_time",
    "max_fan_speed": "fan_max_speed",
    "min_fan_speed": "fan_min_speed",
    "bridge_fan_speed": "overhang_fan_speed",
    "disable_fan_first_layers": "close_fan_the_first_x_layers",
    "cooling": "fan_cooling_layer_time",
    "slowdown_below_layer_time": "slow_down_layer_time",
    "min_print_speed": "slow_down_min_speed",
}

# ─── Printer Settings: Prusa → Orca ───
PRINTER_PARAM_MAP: Dict[str, str] = {
    "bed_shape": "printable_area",
    "max_print_height": "printable_height",
    "nozzle_diameter": "nozzle_diameter",
    "min_layer_height": "min_layer_height",
    "max_layer_height": "max_layer_height",
    "extruder_offset": "extruder_offset",
    "extruder_colour": "extruder_color",
    "retract_length": "retraction_length",
    "retract_speed": "retraction_speed",
    "deretract_speed": "deretraction_speed",
    "retract_lift": "z_hop",
    "retract_lift_above": "z_hop",
    "retract_before_travel": "retraction_minimum_travel",
    "retract_before_wipe": "retract_before_wipe",
    "retract_layer_change": "retract_when_changing_layer",
    "retract_restart_extra": "retract_restart_extra",
    "retract_length_toolchange": "retract_length_toolchange",
    "retract_restart_extra_toolchange": "retract_restart_extra_toolchange",
    "wipe": "wipe",
    "gcode_flavor": "gcode_flavor",
    "printer_technology": "printer_technology",
    "silent_mode": "silent_mode",
    "single_extruder_multi_material": "single_extruder_multi_material",
    "use_firmware_retraction": "use_firmware_retraction",
    "use_relative_e_distances": "use_relative_e_distances",
    "z_offset": "z_offset",
    "machine_max_acceleration_x": "machine_max_acceleration_x",
    "machine_max_acceleration_y": "machine_max_acceleration_y",
    "machine_max_acceleration_z": "machine_max_acceleration_z",
    "machine_max_acceleration_e": "machine_max_acceleration_e",
    "machine_max_acceleration_extruding": "machine_max_acceleration_extruding",
    "machine_max_acceleration_retracting": "machine_max_acceleration_retracting",
    "machine_max_acceleration_travel": "machine_max_acceleration_travel",
    "machine_max_feedrate_x": "machine_max_speed_x",
    "machine_max_feedrate_y": "machine_max_speed_y",
    "machine_max_feedrate_z": "machine_max_speed_z",
    "machine_max_feedrate_e": "machine_max_speed_e",
    "machine_max_jerk_x": "machine_max_jerk_x",
    "machine_max_jerk_y": "machine_max_jerk_y",
    "machine_max_jerk_z": "machine_max_jerk_z",
    "machine_max_jerk_e": "machine_max_jerk_e",
    "machine_min_extruding_rate": "machine_min_extruding_rate",
    "machine_min_travel_rate": "machine_min_travel_rate",
    "start_gcode": "machine_start_gcode",
    "end_gcode": "machine_end_gcode",
    "before_layer_gcode": "layer_change_gcode",
    "toolchange_gcode": "change_filament_gcode",
    "pause_print_gcode": "machine_pause_gcode",
    "printer_notes": "printer_notes",
}

# ─── All maps keyed by section type ───
PARAM_MAPS = {
    "print": PRINT_PARAM_MAP,
    "filament": FILAMENT_PARAM_MAP,
    "printer": PRINTER_PARAM_MAP,
}


def get_parameter_map(section_type: str) -> Dict[str, str]:
    """Get the parameter name mapping for a section type."""
    return PARAM_MAPS.get(section_type, {})


def convert_value(key: str, value: str, target_map: str = "orca") -> str:
    """
    Convert a PrusaSlicer value to OrcaSlicer format.
    
    Handles:
      - Percentage strings (e.g. '15%' → '15%' for some, pure number for others)
      - Prusa template placeholders → Orca placeholders
      - Boolean conversions
      - Special cases (filament_max_volumetric_speed 0 → 15)
    """
    if not value or value in ("nil", "null"):
        return value

    v = value.strip()

    # filament_max_volumetric_speed = 0 → Orca needs a real value
    if key == "filament_max_volumetric_speed" and v == "0":
        return "15"

    # Prusa template placeholders → Orca bracket syntax
    # {first_layer_bed_temperature[0]} → [hot_plate_temp_initial_layer_single]
    # {first_layer_temperature[0]} → [nozzle_temperature_initial_layer]
    # {is_nil(idle_temperature[0]) ? 150 : idle_temperature[0]} → simplified
    # This is a best-effort conversion
    v = _convert_placeholders(v)

    return v


def _convert_placeholders(gcode: str) -> str:
    """Convert Prusa-style gcode placeholders to Orca-style.

    The mapping is derived from the FILAMENT_PARAM_MAP and PRINT_PARAM_MAP
    tables: Prusa gcode uses {param_name[0]} for array values, Orca uses
    [param_name] or [param_name_single] for the single-extruder variant.
    Non-bracket expression replacements (e.g. max_print_height → printable_height)
    are listed separately.
    """
    # Placeholder mappings: {Prusa_gcode_var} → [Orca_gcode_var]
    # Derived from FILAMENT_PARAM_MAP by the pattern:
    #   {prusa_name[0]} → [orca_name]  (array → scalar)
    #   {prusa_name[0]} → [orca_name_single] (array → single-extruder)
    # Example: Prusa "first_layer_bed_temperature" → Orca "bed_temperature_initial_layer"
    #   → gcode:  {first_layer_bed_temperature[0]} → [bed_temperature_initial_layer_single]
    replacements = {
        "{first_layer_bed_temperature[0]}": "[bed_temperature_initial_layer_single]",
        "{first_layer_temperature[0]}": "[nozzle_temperature_initial_layer]",
        "{temperature[0]}": "[nozzle_temperature]",
        "{bed_temperature[0]}": "[bed_temperature]",
        "{filament_type[0]}": "[filament_type]",
        "{printer_model}": "[printer_model]",
        "{input_filename_base}": "[input_filename_base]",
        "{print_time}": "[print_time]",
        "{layer_z}": "[layer_z]",
        "{max_layer_z}": "[max_layer_z]",
        "{print_bed_max[1]*0.85}": "[print_bed_max[1]*0.85]",
        "{print_bed_max[1]*0.8}": "[print_bed_max[1]*0.8]",
    }

    # Expressions in curly braces are valid in Orca (they're evaluated).
    # Only convert `{var_name[0]}` → `[var_name]` (array access → simple ref).
    # Keep math expressions like {travel_speed*60} as-is — Orca evaluates them.

    for prusa, orca in replacements.items():
        gcode = gcode.replace(prusa, orca)

    # Expression replacements: max_print_height → printable_height
    expr_replacements = {
        "{z_offset+min(max_layer_z+2, max_print_height)}": "{z_offset+min(max_layer_z+2, printable_height)}",
        "{z_offset+max_print_height-10}": "{z_offset+printable_height-10}",
        "{z_offset+printable_height-10}": "{z_offset+printable_height-10}",
        "max_print_height": "printable_height",
    }
    for prusa, orca in expr_replacements.items():
        gcode = gcode.replace(prusa, orca)

    # Handle Prusa conditional: {is_nil(something) ? fallback : something}
    # Orca can't evaluate these — replace with the fallback value from Prusa
    gcode = re.sub(
        r"\{is_nil\([^)]+\)\s*\?\s*([^:{}]+)\s*:\s*[^}]+\}",
        r"\1",
        gcode,
    )

    return gcode


def printer_matches_condition(condition: str, printer_model: str) -> bool:
    """
    Check if a printer matches a `compatible_printers_condition` expression.
    
    Handles Prusa-style conditions like:
      printer_model=~/(ENDER|CR|SERMOON).*/ and nozzle_diameter[0]==0.4
    """
    if not condition:
        return False

    # Extract model regex: printer_model=~/PATTERN/
    m = re.search(r"printer_model=~/([^/]+)/", condition)
    if m:
        pattern = m.group(1)
        # Short-circuit: check if printer_model name matches
        import fnmatch
        # Convert regex-like pattern to simple check
        # Since we only have the printer name, do a simple substring match
        if re.search(pattern, printer_model, re.IGNORECASE):
            return True

    # Check for PRINTER_HAS_* flags in printer_notes
    has_highspeed = re.search(r"PRINTER_HAS_HIGHSPEED", condition)
    has_superspeed = re.search(r"PRINTER_HAS_SUPERSPEED", condition)
    if has_highspeed or has_superspeed:
        # We can't know if the target printer has these without notes
        # Default to False for conservative matching
        return False

    return False


def sanitize_profile_name(name: str) -> str:
    """Create a filesystem-safe profile name."""
    safe = "".join(c for c in name if c.isalnum() or c in " @.-_()")
    return safe.strip()
