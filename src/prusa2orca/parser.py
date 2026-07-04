"""
PrusaSlicer .ini parser with full inheritance chain resolution.

Handles:
  - configparser-based INI reading (case-preserving, no interpolation)
  - Section classification (printer_model:, print:, filament:, printer:, vendor)
  - inheritance resolution (inherits = *common*; *0.4nozzle*)
  - Recursive template merging with proper override order
"""

from __future__ import annotations

import configparser
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .models import PrusaSection, SectionType

log = logging.getLogger(__name__)

# Pattern for section names like "printer_model:ENDER3" or "print:*common*"
_SECTION_PATTERN = re.compile(r"^(printer_model|printer|print|filament|vendor)(?::(.+))?$")


def classify_section(raw_name: str) -> tuple[SectionType, str]:
    """Split 'print:0.16mm @CREALITY' into (SectionType.PRINT, '0.16mm @CREALITY')."""
    m = _SECTION_PATTERN.match(raw_name)
    if not m:
        raise ValueError(f"Unknown section format: {raw_name!r}")
    type_str = m.group(1)
    profile_name = (m.group(2) or "").strip()
    type_map = {
        "vendor": SectionType.VENDOR,
        "printer_model": SectionType.PRINTER_MODEL,
        "printer": SectionType.PRINTER,
        "print": SectionType.PRINT,
        "filament": SectionType.FILAMENT,
    }
    return type_map[type_str], profile_name


def parse_ini(file_path: Path) -> Dict[str, PrusaSection]:
    """
    Parse a PrusaSlicer .ini file and return sections keyed by raw section name.
    
    Each section's `inherits` field is populated from the `inherits =` key.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # preserve key case

    with open(file_path, "r", encoding="utf-8") as f:
        config.read_file(f)

    sections: Dict[str, PrusaSection] = {}
    for raw_name in config.sections():
        items = dict(config.items(raw_name))
        section_type, profile_name = classify_section(raw_name)

        # Parse inherits list (semicolon-separated)
        inherits_raw = items.pop("inherits", "")
        inherits = [t.strip() for t in inherits_raw.split(";") if t.strip()]

        sections[raw_name] = PrusaSection(
            raw_name=raw_name,
            section_type=section_type,
            profile_name=profile_name,
            params=items,
            inherits=inherits,
        )

    return sections


def resolve_inherits(
    section: PrusaSection,
    all_sections: Dict[str, PrusaSection],
    _depth: int = 0,
) -> Dict[str, str]:
    """
    Resolve the full inheritance chain for a section.

    Merges params from all inherited templates (last-inherited wins).
    Handles recursive inheritance (templates that inherit from other templates).

    Prusa inheritance order: first listed = lowest priority, last listed = highest priority.
    Within a single template: its own inherits chain is resolved first, then overlaid.
    """
    if _depth > 20:
        log.warning(f"Max inheritance depth reached for {section.raw_name}")
        return dict(section.params)

    merged: Dict[str, str] = {}

    for template_name in section.inherits:
        # Construct the section key: e.g. "printer:*CR5PROH*"
        type_prefix = section.section_type.value
        template_key = f"{type_prefix}:{template_name}"

        template_section = all_sections.get(template_key)
        if template_section is None:
            log.debug(f"Template {template_key!r} not found, skipping")
            continue

        # Recursively resolve the template's own inheritance
        template_params = resolve_inherits(template_section, all_sections, _depth + 1)
        merged.update(template_params)

    # Own params override everything from inherited templates
    merged.update(section.params)
    return merged


def resolve_all(sections: Dict[str, PrusaSection]) -> Dict[str, Dict[str, str]]:
    """Resolve inheritance for all non-template sections (concrete profiles)."""
    resolved: Dict[str, Dict[str, str]] = {}
    for raw_name, section in sections.items():
        if section.is_template():
            continue  # templates are internal, not user-facing profiles
        resolved[raw_name] = resolve_inherits(section, sections)
    return resolved


def filter_by_printer(
    resolved: Dict[str, Dict[str, str]],
    sections: Dict[str, PrusaSection],
    printer_model: str,
) -> Dict[str, Dict[str, str]]:
    """
    Filter resolved profiles to only those matching a given printer model.
    
    Uses compatible_printers_condition and compatible_printers fields.
    """
    from .mapper import printer_matches_condition

    filtered = {}
    for raw_name, params in resolved.items():
        section = sections.get(raw_name)
        if section is None:
            continue
        
        # Check compatibility conditions
        condition = params.get("compatible_printers_condition", "")
        compat_list = params.get("compatible_printers", "")

        if not condition and not compat_list:
            # No compatibility info — include it (global profile)
            filtered[raw_name] = params
            continue

        if printer_matches_condition(condition, printer_model):
            filtered[raw_name] = params
            continue

        if printer_model in compat_list:
            filtered[raw_name] = params
            continue

    return filtered
