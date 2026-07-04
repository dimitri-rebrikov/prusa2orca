"""Integration tests: full convert pipeline against PrusaSlicer GitHub."""

import json
import logging
import zipfile
from pathlib import Path

import pytest

from prusa2orca.cli import cmd_convert
from prusa2orca.remote import get_ini, list_vendors

logging.disable(logging.CRITICAL)

GOLDEN_DIR = Path(__file__).parent / "golden"


class Args:
    """Fake argparse.Namespace for cmd_convert."""
    def __init__(self, **kwargs):
        self.vendor = "Creality"
        self.printer = "Creality CR-5 Pro H"
        self.output = Path("/tmp/test_prusa2orca.orca_printer")
        self.nozzle = "0.4"
        self.refetch = False
        self.verbose = False
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture(autouse=True)
def clean_output():
    p = Path("/tmp/test_prusa2orca.orca_printer")
    p.unlink(missing_ok=True)
    yield
    p.unlink(missing_ok=True)


def _extract_bundle(path: Path) -> dict:
    """Extract .orca_printer ZIP into a {filename: data} dict."""
    result = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            result[name] = json.loads(z.read(name))
    return result


# ─── Vendor / Remote ───

def test_vendors_returns_list():
    vendors = list_vendors()
    assert len(vendors) >= 30
    assert "Creality" in vendors
    assert "Voron" in vendors


def test_get_ini_creality():
    ini = get_ini("Creality")
    assert ini is not None and ini.exists() and ini.stat().st_size > 50000


# ─── Convert ───

def test_convert_creality_cr5proh():
    """Full conversion should produce a valid .orca_printer bundle."""
    args = Args()
    cmd_convert(args)

    assert args.output.exists(), f"Output missing: {args.output}"
    assert args.output.stat().st_size > 5000, "Bundle too small"

    bundle = _extract_bundle(args.output)

    # bundle_structure
    bs = bundle.get("bundle_structure.json")
    assert bs is not None, "Missing bundle_structure.json"
    assert bs["bundle_type"] == "printer config bundle"
    assert len(bs["printer_config"]) >= 1
    assert len(bs["process_config"]) >= 1
    assert len(bs["filament_config"]) >= 1

    # Printer (0.4 nozzle)
    printer_key = [k for k in bundle if k.startswith("printer/") and "0.4" in k]
    assert printer_key, "No 0.4 printer found"
    p = bundle[printer_key[0]]
    assert p["from"] == "User"
    assert "type" not in p, "type field should not be present"
    assert "setting_id" not in p, "setting_id should not be present"
    assert p.get("printer_settings_id"), "printer_settings_id missing"
    assert p.get("is_custom_defined") == "0"
    assert p.get("version") == "2.3.1.10"
    assert p.get("inherits") == ""
    assert len(p.get("printer_settings_id", "")) > 0
    assert p.get("retraction_length") == ["3"]

    # Process
    process_key = [k for k in bundle if k.startswith("process/") and "0.20" in k]
    assert process_key, "No process found"
    pr = bundle[process_key[0]]
    assert pr["from"] == "User"
    assert "compatible_printers" not in pr, \
        "compatible_printers should not be in user process"
    assert pr.get("print_settings_id"), "print_settings_id missing"
    assert pr.get("layer_height") == "0.20"

    # Filament
    filament_key = [k for k in bundle if k.startswith("filament/") and "PLA" in k]
    assert filament_key, "No filament found"
    f = bundle[filament_key[0]]
    assert f["from"] == "User"
    assert f.get("filament_settings_id"), "filament_settings_id missing"
    assert f.get("nozzle_temperature") == ["200"]


def test_golden_files_match():
    """Compare key files against golden reference."""
    if not GOLDEN_DIR.exists():
        pytest.skip("No golden files found")

    args = Args()
    cmd_convert(args)

    bundle = _extract_bundle(args.output)

    for golden_file in GOLDEN_DIR.glob("*.json"):
        if golden_file.name == "bundle_structure.json":
            continue  # metadata, not profile JSON
        name = golden_file.stem
        # Replace first "_" with "/" to map golden filename → bundle key
        # e.g. "printer_Creality CR-5 Pro H 0.4 nozzle" → "printer/Creality CR-5 Pro H 0.4 nozzle.json"
        first_underscore = name.find("_")
        if first_underscore == -1:
            pytest.fail(f"Golden file {golden_file.name} has no underscore separator")
        bundle_key = name[:first_underscore] + "/" + name[first_underscore + 1:] + ".json"

        actual_data = bundle.get(bundle_key)
        assert actual_data is not None, (
            f"Golden file {golden_file.name} has no match in bundle "
            f"(expected key: {bundle_key})"
        )

        golden = json.loads(golden_file.read_text())
        # Compare normalized JSON
        g = json.dumps(golden, sort_keys=True, separators=(",", ":"))
        a = json.dumps(actual_data, sort_keys=True, separators=(",", ":"))

        assert g == a, (
            f"JSON mismatch for {bundle_key}\n"
            f"  To update: python3 -c \"import zipfile,json; "
            f"z=zipfile.ZipFile('{args.output}'); "
            f"open('{golden_file}','w').write(json.dumps(json.loads(z.read('{bundle_key}')),indent=4))\""
        )


def test_vendor_list():
    from prusa2orca.remote import list_printers
    printers = list_printers("Creality")
    assert len(printers) > 20
    cr5pro = [p for p in printers if "CR-5 Pro H" in p["display_name"]]
    assert len(cr5pro) == 1
    assert cr5pro[0]["internal_name"] == "CR5PROH"
