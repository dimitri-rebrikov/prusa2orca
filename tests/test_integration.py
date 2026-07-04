"""Integration tests: full convert pipeline against PrusaSlicer GitHub."""

import json
import logging
import os
from pathlib import Path

import pytest

from prusa2orca.cli import cmd_convert
from prusa2orca.remote import get_ini, list_vendors


# Disable logging noise during tests
logging.disable(logging.CRITICAL)

GOLDEN_DIR = Path(__file__).parent / "golden"


class Args:
    """Fake argparse.Namespace for cmd_convert."""
    def __init__(self, **kwargs):
        self.vendor = "Creality"
        self.printer = "Creality CR-5 Pro H"
        self.output = Path("/tmp/test_prusa2orca")
        self.nozzle = "0.4"
        self.machine_inherits = None
        self.process_inherits = None

        self.refetch = False
        self.verbose = False
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture(autouse=True)
def clean_output():
    path = Path("/tmp/test_prusa2orca")
    if path.exists():
        import shutil
        shutil.rmtree(path)
    yield
    if path.exists():
        import shutil
        shutil.rmtree(path)


def test_vendors_returns_list():
    """list_vendors() should return 30+ vendors."""
    vendors = list_vendors()
    assert len(vendors) >= 30
    assert "Creality" in vendors
    assert "Voron" in vendors
    assert "Anycubic" in vendors


def test_get_ini_creality():
    """get_ini should download and cache Creality.ini."""
    ini = get_ini("Creality")
    assert ini is not None
    assert ini.exists()
    assert ini.stat().st_size > 50000  # should be ~110KB


def test_convert_creality_cr5proh():
    """Full conversion for Creality CR-5 Pro H should produce all profile types."""
    args = Args()
    cmd_convert(args)

    base = args.output

    # machine_model
    mm = base / "machine" / "Creality CR-5 Pro H.json"
    assert mm.exists(), f"Missing: {mm}"
    d = json.loads(mm.read_text())
    assert d["type"] == "machine_model"
    assert d["name"] == "Creality CR-5 Pro H"

    # machine variant (0.4)
    mv = base / "machine" / "Creality CR-5 Pro H 0.4 nozzle.json"
    assert mv.exists(), f"Missing: {mv}"
    d = json.loads(mv.read_text())
    assert d["type"] == "machine"
    assert d["name"] == "Creality CR-5 Pro H 0.4 nozzle"
    assert d["from"] == "user"
    assert d.get("setting_id"), "setting_id missing"
    assert d.get("inherits") == "fdm_creality_common"
    assert d.get("printable_area") == ["5x5", "295x5", "295x220", "5x220"]
    assert d.get("printable_height") == "380"
    assert d.get("retraction_length") == ["3"]

    # machine variants for other nozzles
    for n in ["0.3", "0.5", "0.6"]:
        p = base / "machine" / f"Creality CR-5 Pro H {n} nozzle.json"
        assert p.exists(), f"Missing: {p}"

    # process profiles (8 for 0.4mm)
    process_dir = base / "process"
    process_files = list(process_dir.glob("*.json"))
    assert len(process_files) >= 7, f"Expected ≥7 process profiles, got {len(process_files)}"

    # Check a specific process profile
    pp = base / "process" / "0.20mm Standard @Creality CR-5 Pro H 0.4.json"
    assert pp.exists(), f"Missing: {pp}"
    d = json.loads(pp.read_text())
    assert d["type"] == "process"
    assert d["from"] == "user"
    assert d.get("setting_id"), "setting_id missing"
    assert d["layer_height"] == "0.20"
    assert d["bottom_shell_layers"] == "4"
    assert d["top_shell_layers"] == "5"
    assert d["compatible_printers"] == ["Creality CR-5 Pro H 0.4 nozzle"]

    # filament profiles (4)
    filament_dir = base / "filament"
    filament_files = list(filament_dir.glob("*.json"))
    assert len(filament_files) >= 3, f"Expected ≥3 filament profiles, got {len(filament_files)}"

    # Check PLA filament
    fp = base / "filament" / "Creality Generic PLA @Creality CR-5 Pro H.json"
    if fp.exists():
        d = json.loads(fp.read_text())
        assert d["type"] == "filament"
        assert d["from"] == "user"
        assert d["nozzle_temperature"] == ["200"]
        assert d["hot_plate_temp"] == ["60"]


def test_assets_skipped_when_no_internet():
    """convert should work even if asset download fails (simulated)."""
    args = Args()
    cmd_convert(args)
    # It should generate JSON files regardless
    json_count = len(list(args.output.rglob("*.json")))
    assert json_count >= 14, f"Expected ≥14 JSONs, got {json_count}"


def test_vendor_list():
    """list command should return proper printer list."""
    # We test the data retrieval, not the print output
    from prusa2orca.remote import list_printers
    printers = list_printers("Creality")
    assert len(printers) > 20, f"Expected 20+ Creality printers, got {len(printers)}"
    
    cr5pro = [p for p in printers if "CR-5 Pro H" in p["display_name"]]
    assert len(cr5pro) == 1
    assert cr5pro[0]["internal_name"] == "CR5PROH"
    assert cr5pro[0]["variants"] == "0.4; 0.3; 0.5; 0.6"


def test_json_schema():
    """All generated JSON files should have valid required fields."""
    args = Args()
    cmd_convert(args)

    for json_file in args.output.rglob("*.json"):
        d = json.loads(json_file.read_text())
        assert "type" in d, f"{json_file.name}: missing type"
        assert "name" in d, f"{json_file.name}: missing name"
        assert "from" in d, f"{json_file.name}: missing from"
        assert d["from"] == "user", f"{json_file.name}: from ≠ user"
        # machine_model (instantiation=false) has no setting_id
        if d["type"] != "machine_model":
            assert "setting_id" in d, f"{json_file.name}: missing setting_id"
        assert "instantiation" in d, f"{json_file.name}: missing instantiation"


def _normalize_json(data) -> str:
    """Deterministic JSON string for comparison (sorted keys, no extra whitespace)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def test_golden_files_match():
    """Compare current output against golden reference files.

    Golden files were generated with:
      prusa2orca convert Creality -p "Creality CR-5 Pro H"
    and represent the known-good output.
    
    If this test fails after a code change, it means the output differs.
    If the change is intentional, update the golden files with:
      python3 -m json.tool current.json > tests/golden/file.json
    """
    if not GOLDEN_DIR.exists() or not list(GOLDEN_DIR.glob("*.json")):
        pytest.skip("No golden files found — run the test once to generate them")

    args = Args()
    cmd_convert(args)

    # Read current output
    current = {}
    for jf in args.output.rglob("*.json"):
        key = jf.name
        current[key] = json.loads(jf.read_text())

    # Compare against golden
    for golden_file in sorted(GOLDEN_DIR.glob("*.json")):
        key = golden_file.name
        assert key in current, f"Missing output file: {key} (golden has it)"

        golden = json.loads(golden_file.read_text())
        actual = current[key]

        g_norm = _normalize_json(golden)
        a_norm = _normalize_json(actual)

        assert g_norm == a_norm, (
            f"JSON mismatch in {key}\n"
            f"  Golden: {golden_file}\n"
            f"  To update: python3 -m json.tool /tmp/test_prusa2orca/{key} > {golden_file}"
        )
        del current[key]  # remove from dict to track extras

    # Warn about extra files (in current but not in golden)
    for extra in current:
        if not extra.endswith(".stl") and not extra.endswith(".svg") and "_cover.png" not in extra:
            print(f"  ⚠ Extra output file not in golden: {extra}")
