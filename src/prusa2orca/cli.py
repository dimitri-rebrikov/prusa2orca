"""
CLI entry point for prusa2orca.
Generates .orca_printer bundles — import directly in OrcaSlicer.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from .assets import (
    find_assets_for_printer,
    generate_bed_texture,
    make_orca_asset_name,
)
from .mapper import convert_value
from .models import PrusaSection, SectionType
from .orca_builder import (
    build_bundle_structure,
    build_filament_json,
    build_machine_json,
    build_process_json,
    find_printer_model_section,
    find_printer_sections,
    vendor_slug,
    ORCA_VERSION,
)
from .parser import (
    classify_section,
    parse_ini,
    resolve_all,
    resolve_inherits,
)
from .remote import (
    get_ini,
    get_vendor_dir,
    list_printers,
    list_vendors,
)

log = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _safe_fn(name: str) -> str:
    """Filesystem-safe filename."""
    return "".join(c for c in name if c.isalnum() or c in " @.-_()").strip()


# ─────────── COMMANDS ───────────


def cmd_vendors(args: argparse.Namespace):
    """List all available printer vendors."""
    vendors = list_vendors()
    if not vendors:
        log.error("Could not fetch vendor list (no internet?)")
        sys.exit(1)
    print(f"\nAvailable vendors ({len(vendors)}):\n")
    for v in vendors:
        print(f"  {v}")
    print()
    print("Usage: prusa2orca list printers <vendor>")


def cmd_list_printers(args: argparse.Namespace):
    """List all printer models for a vendor."""
    printers = list_printers(args.vendor)
    if not printers:
        log.error(f"No printer models found for vendor '{args.vendor}'")
        sys.exit(1)
    print(f"\n{'Printer Model':50s} {'Internal Key':25s} {'Family':15s} {'Nozzles'}")
    print("-" * 110)
    for p in printers:
        print(f"{p['display_name']:50s} {p['internal_name']:25s} {p['family']:15s} {p['variants']}")


def cmd_convert(args: argparse.Namespace):
    """Convert a printer's profiles to an .orca_printer bundle."""
    vendor: str = args.vendor
    printer_name: str = args.printer
    output_path: Path = args.output

    # Download ini
    ini_path = get_ini(vendor, force_refetch=args.refetch)
    if not ini_path:
        log.error(f"Could not fetch {vendor}.ini from PrusaSlicer GitHub")
        sys.exit(1)

    log.info(f"Reading {vendor}.ini")
    sections = parse_ini(ini_path)
    resolved = resolve_all(sections)
    log.info(f"  {len(resolved)} profiles after inheritance resolution")

    # Find printer model
    pm_section = find_printer_model_section(sections, printer_name)
    pm_key = pm_section.profile_name if pm_section else None
    printer_display = pm_section.params.get("name", printer_name) if pm_section else printer_name

    if pm_section:
        log.info(f"Found printer model: {printer_display}")

    # Filter profiles for this printer
    if printer_name.startswith(vendor):
        printer_short = printer_name[len(vendor) + 1:]
    else:
        printer_short = printer_name

    target_nozzle = args.nozzle or "0.4"

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
            pn = section.profile_name if section else raw_name
            if f"{target_nozzle} mm nozzle" in pn or f"({target_nozzle} " in pn:
                filtered[raw_name] = params
            continue
        if section.section_type == SectionType.FILAMENT:
            filtered[raw_name] = params

    log.info(f"  {len(filtered)} relevant profiles for '{printer_name}' ({target_nozzle}mm)")

    # Build profile dicts (user format)
    printer_dicts: List[tuple] = []     # (subdir, filename, data)
    process_dicts: List[tuple] = []
    filament_dicts: List[tuple] = []

    # Machine variants
    if pm_section:
        pr_sections = find_printer_sections(sections, pm_section.profile_name)
        seen = set()
        for ps in pr_sections:
            if ps.is_template():
                continue
            rp = resolve_inherits(ps, sections)
            nozzle = rp.get("nozzle_diameter", "0.4")
            if (printer_display, nozzle) in seen:
                continue
            seen.add((printer_display, nozzle))
            data = build_machine_json(rp, printer_display, vendor)
            fn = _safe_fn(data["name"])
            printer_dicts.append(("printer", fn, data))

    # Fallback
    if not printer_dicts:
        for raw_name, rp in filtered.items():
            section = sections.get(raw_name)
            if section and section.section_type == SectionType.PRINTER and not section.is_template():
                display_name = section.params.get("renamed_from", section.profile_name)
                data = build_machine_json(
                    rp,
                    display_name.strip('"') if isinstance(display_name, str) else str(display_name),
                    vendor,
                )
                fn = _safe_fn(data["name"])
                printer_dicts.append(("printer", fn, data))

    # Process profiles
    seen_process = set()
    for raw_name, rp in sorted(filtered.items()):
        section = sections.get(raw_name)
        if section and section.section_type == SectionType.PRINT and not section.is_template():
            notes = _get_printer_notes(sections, printer_name)
            if "HIGHSPEED" in raw_name.upper() and "HIGHSPEED" not in notes:
                continue
            if "SUPERSPEED" in raw_name.upper() and "SUPERSPEED" not in notes:
                continue
            data = build_process_json(rp, section.profile_name, printer_name, vendor)
            if data["name"] in seen_process:
                continue
            seen_process.add(data["name"])
            fn = _safe_fn(data["name"])
            process_dicts.append(("process", fn, data))

    # Filament profiles
    seen_filament = set()
    for raw_name, rp in sorted(filtered.items()):
        section = sections.get(raw_name)
        if section and section.section_type == SectionType.FILAMENT and not section.is_template():
            data = build_filament_json(rp, section.profile_name, printer_name, vendor)
            if data["name"] in seen_filament:
                continue
            seen_filament.add(data["name"])
            fn = _safe_fn(data["name"])
            filament_dicts.append(("filament", fn, data))

    # Build bundle
    printer_rel = [f"printer/{fn}.json" for _, fn, _ in printer_dicts]
    process_rel = [f"process/{fn}.json" for _, fn, _ in process_dicts]
    filament_rel = [f"filament/{fn}.json" for _, fn, _ in filament_dicts]

    bundle = build_bundle_structure(printer_name, printer_rel, process_rel, filament_rel)

    # Create .orca_printer ZIP
    safe_output = output_path
    if not safe_output.suffix:
        safe_output = output_path / f"{vendor} {printer_short}.orca_printer"

    safe_output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(safe_output, "w", zipfile.ZIP_DEFLATED) as zf:
        # bundle_structure.json
        zf.writestr("bundle_structure.json", json.dumps(bundle, indent=4))

        # Printer JSONs
        for subdir, fn, data in printer_dicts:
            zf.writestr(f"printer/{fn}.json", json.dumps(data, indent=4))
            log.info(f"  + printer/{fn}.json")

        # Process JSONs
        for subdir, fn, data in process_dicts:
            zf.writestr(f"process/{fn}.json", json.dumps(data, indent=4))
            log.info(f"  + process/{fn}.json")

        # Filament JSONs
        for subdir, fn, data in filament_dicts:
            zf.writestr(f"filament/{fn}.json", json.dumps(data, indent=4))
            log.info(f"  + filament/{fn}.json")

    total = len(printer_dicts) + len(process_dicts) + len(filament_dicts)
    log.info(f"\nDone! {total} profiles → {safe_output}")
    log.info(f"Import: File → Import → Import Configs → select {safe_output}")
    log.info(f"Or drag & drop the file onto OrcaSlicer")


def cmd_assets(args: argparse.Namespace):
    """Download or generate bed model, texture, and thumbnail."""
    vendor: str = args.vendor
    printer_name: str = args.printer
    output_dir: Path = args.output

    ini_path = get_ini(vendor)
    if not ini_path:
        log.error(f"Could not fetch {vendor}.ini")
        sys.exit(1)

    sections = parse_ini(ini_path)
    assets = find_assets_for_printer(sections, printer_name)
    if not assets:
        log.error(f"No assets found for: {printer_name}")
        return

    vdir = get_vendor_dir(vendor)
    for kind, filename in assets.items():
        if filename:
            orca_name = make_orca_asset_name(filename, printer_name, vendor)
            log.info(f"  {kind}: {orca_name}")

    from .assets import download_asset
    result = download_asset(assets["bed_model"], vdir, output_dir, printer_name, vendor)
    if result:
        log.info(f"  ✓ Bed model: {result.name}")

    orca_name = make_orca_asset_name(assets["bed_texture"], printer_name, vendor)
    texture_path = output_dir / orca_name
    from .assets import download_asset as dl
    result = dl(assets["bed_texture"], vdir, output_dir, printer_name, vendor)
    if not result:
        bed_dims = _get_bed_dimensions(sections, printer_name)
        generate_bed_texture(texture_path, bed_dims[0], bed_dims[1])

    dl(assets["thumbnail"], vdir, output_dir, printer_name, vendor)


# ─────────── HELPERS ───────────


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


def _get_printer_notes(sections, printer_name):
    for raw_name, section in sections.items():
        if section.section_type == SectionType.PRINTER and not section.is_template():
            if printer_name in raw_name or printer_name in section.profile_name:
                resolved = resolve_inherits(section, sections)
                return resolved.get("printer_notes", "")
    return ""


# ─────────── MAIN ───────────


def main():
    parser = argparse.ArgumentParser(
        description="Convert PrusaSlicer profiles to OrcaSlicer .orca_printer bundles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  prusa2orca vendors
  prusa2orca list Creality
  prusa2orca convert Creality -p "CR-5 Pro H" -o ./CR-5-Pro-H.orca_printer
  prusa2orca convert Voron -p "Voron V2.4 350" -o ./Voron24.orca_printer
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("vendors", help="List available printer vendors")

    list_p = sub.add_parser("list", help="List printer models for a vendor")
    list_p.add_argument("vendor", type=str, help="Vendor name")

    conv_p = sub.add_parser("convert", help="Convert to .orca_printer bundle")
    conv_p.add_argument("vendor", type=str, help="Vendor name")
    conv_p.add_argument("-p", "--printer", type=str, required=True, help="Printer model name")
    conv_p.add_argument("-o", "--output", type=Path, default=None,
                        help="Output path (.orca_printer file, or directory)")
    conv_p.add_argument("--nozzle", type=str, default="0.4", help="Target nozzle (default: 0.4)")
    conv_p.add_argument("--refetch", action="store_true", help="Force re-download vendor .ini")

    assets_p = sub.add_parser("assets", help="Download bed models and textures")
    assets_p.add_argument("vendor", type=str, help="Vendor name")
    assets_p.add_argument("-p", "--printer", type=str, required=True, help="Printer model name")
    assets_p.add_argument("-o", "--output", type=Path, default=Path("."), help="Output directory")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Auto-detect vendor from printer name
    if hasattr(args, 'vendor') and not args.vendor and hasattr(args, 'printer') and args.printer:
        args.vendor = args.printer.split()[0] if ' ' in args.printer else args.printer

    # Default output: .orca_printer file next to cwd
    if hasattr(args, 'output') and args.output is None and args.command == 'convert':
        safe_name = _safe_fn(args.printer)
        args.output = Path(f"{args.vendor} {safe_name}.orca_printer")

    try:
        if args.command == "vendors":
            cmd_vendors(args)
        elif args.command == "list":
            cmd_list_printers(args)
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
