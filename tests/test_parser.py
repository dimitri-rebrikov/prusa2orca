"""Tests for PrusaSlicer INI parser."""

from pathlib import Path
from prusa2orca.parser import classify_section, parse_ini, resolve_inherits, SectionType


def test_classify_section():
    assert classify_section("vendor") == (SectionType.VENDOR, "")
    assert classify_section("printer_model:ENDER3") == (SectionType.PRINTER_MODEL, "ENDER3")
    assert classify_section("print:*common*") == (SectionType.PRINT, "*common*")
    assert classify_section("print:0.16 mm OPTIMAL @CREALITY") == (SectionType.PRINT, "0.16 mm OPTIMAL @CREALITY")
    assert classify_section("filament:*PLA*") == (SectionType.FILAMENT, "*PLA*")
    assert classify_section("printer:*CR5PROH*") == (SectionType.PRINTER, "*CR5PROH*")


def test_parse_includes_inherits(tmp_path):
    ini = tmp_path / "test.ini"
    ini.write_text(
        "[print:*common*]\n"
        "layer_height = 0.2\n"
        "fill_density = 15%\n"
        "\n"
        "[print:*0.16mm*]\n"
        "inherits = *common*\n"
        "layer_height = 0.16\n"
        "bottom_solid_layers = 5\n"
    )
    sections = parse_ini(ini)
    assert len(sections) == 2
    common = sections["print:*common*"]
    assert common.inherits == []
    assert common.params["layer_height"] == "0.2"
    
    detail = sections["print:*0.16mm*"]
    assert detail.inherits == ["*common*"]
    assert detail.params["layer_height"] == "0.16"


def test_resolve_inherits(tmp_path):
    ini = tmp_path / "test.ini"
    ini.write_text(
        "[print:*common*]\n"
        "layer_height = 0.2\n"
        "fill_density = 15%\n"
        "fill_pattern = grid\n"
        "\n"
        "[print:*0.4nozzle*]\n"
        "wall_loops = 3\n"
        "\n"
        "[print:*0.16mm*]\n"
        "inherits = *common*\n"
        "layer_height = 0.16\n"
        "bottom_solid_layers = 5\n"
        "\n"
        "[print:0.16mm OPTIMAL @TEST]\n"
        "inherits = *0.16mm*; *0.4nozzle*\n"
        "top_solid_layers = 7\n"
    )
    sections = parse_ini(ini)
    resolved = resolve_inherits(sections["print:0.16mm OPTIMAL @TEST"], sections)
    assert resolved["layer_height"] == "0.16"    # from *0.16mm*
    assert resolved["fill_density"] == "15%"     # from *common*
    assert resolved["fill_pattern"] == "grid"    # from *common*
    assert resolved["wall_loops"] == "3"         # from *0.4nozzle* (later = wins)
    assert resolved["bottom_solid_layers"] == "5"  # from *0.16mm*
    assert resolved["top_solid_layers"] == "7"     # own
