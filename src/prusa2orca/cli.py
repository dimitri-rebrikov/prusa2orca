"""
CLI entry point for prusa2orca.
Vendor-agnostic: works with Creality, Voron, Anycubic, Prusa, etc.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .assets import (
    download_asset,
    find_assets_for_printer,
    generate_bed_texture,
    make_orca_asset_name,
)
from .mapper import (
    convert_value,
    get_parameter_map,
    sanitize_profile_name,
)
from .models import OrcaProfile, PrusaSection, SectionType
from .orca_builder import (
    build_filament_json,
    build_machine_json,
    build_machine_model_json,
    build_process_json,
    find_printer_model_section,
    find_printer_sections,
    vendor_slug,
)
from .parser import (
    classify_section,
    filter_by_printer,
    parse_ini,
    resolve_all,
    resolve_inherits,
)

log = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def write_json(profile: OrcaProfile, output_dir: Path):
    """Write a single Orca profile to a JSON file."""
    data = {"type": profile.type, "name": profile.name}
    if profile.inherits:
        data["inherits"] = profile.inherits
    data["from"] = profile.from_field
    if profile.setting_id:
        data["setting_id"] = profile.setting_id
    data["instantiation"] = profile.instantiation
    data.update(profile.data)

    safe_name = "".join(c for c in profile.name if c.isalnum() or c in " @.-_()").strip()
    filepath = output_dir / f"{safe_name}.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    log.info(f"  → {filepath.relative_to(output_dir.parent)}")


def cmd_list(args: argparse.Namespace):
    """List all printers found in a PrusaSlicer .ini file."""
    sections = parse_ini(args.file)

    print(f"\n{'Printer Model':40s} {'Section':25s} {'Families'}")
    print("-" * 85)

    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER_MODEL:
            name = section.params.get("name", "?")
            family = section.params.get("family", "")
            print(f"{name:40s} {section.profile_name:25s} {family}")

    print(f"\n{'Concrete Printer Profiles':40s} {'Template':25s}")
    print("-" * 85)
    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER and not section.is_template():
            inherits = "; ".join(section.inherits)
            print(f"{raw_name:55s} ← {inherits}")


def cmd_convert(args: argparse.Namespace):
    """Convert profiles from a PrusaSlicer .ini file to OrcaSlicer JSON."""
    file_path: Path = args.file
    output_dir: Path = args.output
    printer_name: Optional[str] = args.printer
    vendor: str = args.vendor or "Creality"
    extract_assets: bool = not args.no_assets

    # Inherits targets — allow override for vendor-specific Orca bases
    machine_inherits = args.machine_inherits or f"fdm_{vendor.lower()}_common"
    process_inherits = args.process_inherits or f"fdm_process_{vendor.lower()}_common"

    log.info(f"Reading {file_path}")
    sections = parse_ini(file_path)
    log.info(f"  Found {len(sections)} sections")

    log.info("Resolving inheritance chains...")
    resolved = resolve_all(sections)
    log.info(f"  Resolved {len(resolved)} concrete profiles")

    if printer_name:
        log.info(f"Filtering for printer: {printer_name}")
        pm_key = _find_printer_model_key(sections, printer_name)
        if printer_name.startswith(vendor):
            printer_short = printer_name[len(vendor) + 1:]
        else:
            printer_short = printer_name

        target_nozzle = "0.4"
        filtered = {}
        for raw_name, params in resolved.items():
            section = sections.get(raw_name)
            if section is None:
                continue

            if section.section_type == SectionType.PRINTER:
                pm = params.get("printer_model", "")
                if pm == pm_key or printer_name in raw_name or printer_short in raw_name:
                    filtered[raw_name] = params
                continue

            if section.section_type == SectionType.PRINT:
                profile_name = section.profile_name if section else raw_name
                if f"{target_nozzle} mm nozzle" in profile_name or f"({target_nozzle} " in profile_name:
                    filtered[raw_name] = params
                continue

            if section.section_type == SectionType.FILAMENT:
                filtered[raw_name] = params

        log.info(f"  {len(filtered)} relevant profiles")
    else:
        filtered = resolved

    # Setup output directories
    machine_dir = output_dir / "machine"
    process_dir = output_dir / "process"
    filament_dir = output_dir / "filament"
    machine_dir.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)
    filament_dir.mkdir(parents=True, exist_ok=True)

    # Find printer model section
    pm_section = None
    if printer_name:
        pm_section = find_printer_model_section(sections, printer_name)
        if pm_section:
            log.info(f"Found printer model: {pm_section.params.get('name', '?')}")

    # Generate machine_model JSON
    if pm_section:
        mm_profile = build_machine_model_json(pm_section, vendor)
        write_json(mm_profile, machine_dir)

    # Generate machine variant JSONs
    if pm_section and printer_name:
        printer_display = pm_section.params.get("name", printer_name)
        printer_sections = find_printer_sections(sections, pm_section.profile_name)
        seen_variants = set()
        for ps in printer_sections:
            if ps.is_template():
                continue
            resolved_params = resolve_inherits(ps, sections)
            nozzle = resolved_params.get("nozzle_diameter", "0.4")
            variant_key = (printer_display, nozzle)
            if variant_key in seen_variants:
                continue
            seen_variants.add(variant_key)
            machine_profile = build_machine_json(
                resolved_params, printer_display, vendor,
                inherits_target=machine_inherits,
            )
            write_json(machine_profile, machine_dir)

    # Fallback: generate from resolved params
    if not list(machine_dir.glob("*nozzle*.json")):
        log.info("No explicit printer sections found, generating from resolved params")
        for raw_name, resolved_params in filtered.items():
            section = sections.get(raw_name)
            if section and section.section_type == SectionType.PRINTER and not section.is_template():
                display_name = section.params.get("renamed_from", section.profile_name)
                machine_profile = build_machine_json(
                    resolved_params,
                    display_name.strip('"') if isinstance(display_name, str) else str(display_name),
                    vendor,
                    inherits_target=machine_inherits,
                )
                write_json(machine_profile, machine_dir)

    # Generate process JSONs
    process_count = 0
    seen_process = set()
    for raw_name, resolved_params in sorted(filtered.items()):
        section = sections.get(raw_name)
        if section and section.section_type == SectionType.PRINT and not section.is_template():
            display_name = section.profile_name
            if printer_name:
                notes = _get_printer_notes(sections, printer_name)
                if "HIGHSPEED" in raw_name.upper() and "HIGHSPEED" not in notes:
                    continue
                if "SUPERSPEED" in raw_name.upper() and "SUPERSPEED" not in notes:
                    continue

                pp = build_process_json(
                    resolved_params, display_name, printer_name, vendor,
                    inherits_target=process_inherits,
                )
                if pp.name in seen_process:
                    continue
                seen_process.add(pp.name)
                write_json(pp, process_dir)
                process_count += 1

    log.info(f"Generated {process_count} process profiles")

    # Generate filament JSONs
    filament_count = 0
    seen_filament = set()
    for raw_name, resolved_params in sorted(filtered.items()):
        section = sections.get(raw_name)
        if section and section.section_type == SectionType.FILAMENT and not section.is_template():
            display_name = section.profile_name
            if printer_name:
                fp = build_filament_json(resolved_params, display_name, printer_name, vendor)
                if fp.name in seen_filament:
                    continue
                seen_filament.add(fp.name)
                write_json(fp, filament_dir)
                filament_count += 1

    log.info(f"Generated {filament_count} filament profiles")

    # Extract assets
    if extract_assets and printer_name:
        log.info("Extracting printer assets...")
        assets = find_assets_for_printer(sections, printer_name)
        bed_dims = _get_bed_dimensions(sections, printer_name)
        vendor_dir_name = args.vendor_dir or vendor  # PrusaSlicer subdir name

        if assets.get("bed_model"):
            fn = assets["bed_model"]
            orca_name = make_orca_asset_name(fn, printer_name, vendor)
            out = machine_dir / orca_name
            if not out.exists():
                download_asset(fn, vendor_dir_name, machine_dir, printer_name, vendor)

        if assets.get("bed_texture"):
            fn = assets["bed_texture"]
            orca_name = make_orca_asset_name(fn, printer_name, vendor)
            out = machine_dir / orca_name
            if not out.exists():
                result = download_asset(fn, vendor_dir_name, machine_dir, printer_name, vendor)
                if not result:
                    generate_bed_texture(out, bed_dims[0], bed_dims[1])

        if assets.get("thumbnail"):
            fn = assets["thumbnail"]
            orca_name = make_orca_asset_name(fn, printer_name, vendor)
            out = machine_dir / orca_name
            if not out.exists():
                download_asset(fn, vendor_dir_name, machine_dir, printer_name, vendor)

    # Summary
    total = _count_files(output_dir)
    log.info(f"\nDone! {total} files written to {output_dir}/")
    install_path = f"~/.config/OrcaSlicer/system/{vendor}/"
    log.info(f"Install: cp -r machine/ process/ filament/ {install_path}")


def cmd_assets(args: argparse.Namespace):
    """Download or generate printer assets (bed model, texture, thumbnail)."""
    sections = parse_ini(args.file)
    output_dir: Path = args.output
    printer_name: str = args.printer
    vendor: str = args.vendor or "Creality"
    vendor_dir_name = args.vendor_dir or vendor

    assets = find_assets_for_printer(sections, printer_name)
    if not assets:
        log.error(f"No assets found for printer: {printer_name}")
        return

    log.info(f"Assets for {printer_name}:")
    for kind, filename in assets.items():
        if filename:
            orca_name = make_orca_asset_name(filename, printer_name, vendor)
            log.info(f"  {kind}: {filename} → {orca_name}")

    result = download_asset(assets["bed_model"], vendor_dir_name,
                            output_dir / "machine", printer_name, vendor)
    if result:
        log.info(f"  ✓ Bed model: {result.name}")

    orca_name = make_orca_asset_name(assets["bed_texture"], printer_name, vendor)
    texture_path = output_dir / "machine" / orca_name
    result = download_asset(assets["bed_texture"], vendor_dir_name,
                            output_dir / "machine", printer_name, vendor)
    if not result:
        bed_dims = _get_bed_dimensions(sections, printer_name)
        generate_bed_texture(texture_path, bed_dims[0], bed_dims[1])

    download_asset(assets["thumbnail"], vendor_dir_name,
                   output_dir / "machine", printer_name, vendor)


# ─── Helpers ───

def _get_bed_dimensions(sections, printer_name):
    resolved = resolve_all(sections)
    for raw_name, params in resolved.items():
        section = sections.get(raw_name)
        if section and section.section_type == SectionType.PRINTER:
            pm = params.get("printer_model", "")
            if pm and (pm in printer_name or printer_name in pm):
                bed_shape = params.get("bed_shape", "")
                if bed_shape:
                    coords = bed_shape.split(",")
                    if len(coords) >= 3:
                        try:
                            last = coords[-1].strip()
                            x, y = last.split("x")
                            return int(float(x)) + 5, int(float(y)) + 5
                        except (ValueError, IndexError):
                            pass
    return 300, 225


def _find_printer_model_key(sections, printer_name):
    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER_MODEL:
            display = section.params.get("name", "")
            if display == printer_name or section.profile_name == printer_name:
                return section.profile_name
    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER_MODEL:
            if section.profile_name in printer_name.upper():
                return section.profile_name
    return printer_name.upper().replace(" ", "").replace("-", "")


def _get_printer_notes(sections, printer_name):
    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER and not section.is_template():
            if printer_name in raw_name or printer_name in section.profile_name:
                resolved = resolve_inherits(section, sections)
                return resolved.get("printer_notes", "")
    return ""


def _count_files(directory: Path) -> int:
    return len(list(directory.rglob("*.json")))


def main():
    parser = argparse.ArgumentParser(
        description="Convert PrusaSlicer profiles to OrcaSlicer format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  prusa2orca list Creality.ini
  prusa2orca convert Creality.ini -p "Creality CR-5 Pro H" -o ./profiles
  prusa2orca convert PrusaSlicer.ini -p "Voron V2.4" --vendor Voron -o ./voron
  prusa2orca assets Anycubic.ini -p "Anycubic Kobra 2" --vendor Anycubic -o ./profiles
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # list
    list_p = sub.add_parser("list", help="List printers in a .ini file")
    list_p.add_argument("file", type=Path, help="PrusaSlicer .ini file")

    # convert
    conv_p = sub.add_parser("convert", help="Convert profiles to OrcaSlicer JSON")
    conv_p.add_argument("file", type=Path, help="PrusaSlicer .ini file")
    conv_p.add_argument("-o", "--output", type=Path, default=Path("./orca_profiles"),
                        help="Output directory")
    conv_p.add_argument("-p", "--printer", type=str, default=None,
                        help="Printer model name (e.g. 'Creality CR-5 Pro H')")
    conv_p.add_argument("--vendor", type=str, default=None,
                        help="Vendor name (e.g. 'Creality'). Auto-detected from printer name if omitted.")
    conv_p.add_argument("--vendor-dir", type=str, default=None,
                        help="PrusaSlicer vendor subdirectory for assets (default: same as --vendor)")
    conv_p.add_argument("--machine-inherits", type=str, default=None,
                        help="Orca machine base profile (default: fdm_{vendor}_common → fdm_machine_common fallback)")
    conv_p.add_argument("--process-inherits", type=str, default=None,
                        help="Orca process base profile (default: fdm_process_{vendor}_common → fdm_process_common)")
    conv_p.add_argument("--nozzle", type=str, default="0.4",
                        help="Target nozzle diameter (default: 0.4)")
    conv_p.add_argument("--no-assets", action="store_true",
                        help="Skip downloading bed models/textures")

    # assets
    assets_p = sub.add_parser("assets", help="Download bed models and textures from PrusaSlicer source")
    assets_p.add_argument("file", type=Path, help="PrusaSlicer .ini file")
    assets_p.add_argument("-p", "--printer", type=str, required=True,
                          help="Printer model name")
    assets_p.add_argument("--vendor", type=str, default="Creality",
                          help="Vendor name (default: Creality)")
    assets_p.add_argument("--vendor-dir", type=str, default=None,
                          help="PrusaSlicer vendor subdirectory for assets")
    assets_p.add_argument("-o", "--output", type=Path, default=Path("./orca_profiles"),
                          help="Output directory")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Auto-detect vendor from printer name if not specified
    if hasattr(args, 'vendor') and not args.vendor and hasattr(args, 'printer') and args.printer:
        # Extract first word as vendor name
        args.vendor = args.printer.split()[0] if ' ' in args.printer else args.printer

    try:
        if args.command == "list":
            cmd_list(args)
        elif args.command == "convert":
            cmd_convert(args)
        elif args.command == "assets":
            cmd_assets(args)
    except Exception as e:
        log.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
