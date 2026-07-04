# prusa2orca

Convert PrusaSlicer printer profiles to OrcaSlicer JSON — **no local files required**.

## Features

- **No local .ini files needed** — fetches everything from PrusaSlicer's GitHub
- **List vendors** — see all 30+ supported printer brands
- **List printers** — see all models for a vendor
- **Convert** — full profile conversion with inheritance resolution
- **Assets** — auto-download bed STL, SVG texture, and printer thumbnail
- **Vendor-agnostic** — Creality, Voron, Anycubic, Sovol, etc.
- **100+ parameter mappings** — print, filament, printer settings

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Installation

```bash
git clone https://github.com/dimitri-rebrikov/prusa2orca.git
cd prusa2orca
uv sync
```

## Usage

### List all vendors

```bash
uv run prusa2orca vendors
```

### List printers for a vendor

```bash
uv run prusa2orca list Creality
uv run prusa2orca list Voron
uv run prusa2orca list Anycubic
```

### Convert a printer's profiles

```bash
# Erzeugt eine .orca_printer Datei — direkt in Orca importierbar
uv run prusa2orca convert Creality -p "Creality CR-5 Pro H" -o ./CR-5-Pro-H.orca_printer
uv run prusa2orca convert Voron -p "Voron V2.4 350" -o ./Voron24.orca_printer

# Import: File → Import → Import Configs → .orca_printer auswählen
# Oder: Datei auf Orca-Fenster ziehen
```

### Options

| Flag | Description |
|------|-------------|
| `-p, --printer` | Printer model name (e.g. `"Creality CR-5 Pro H"`) |
| `-o, --output` | Output path (`.orca_printer` file, default: auto-named) |
| `--nozzle` | Target nozzle diameter (default: `0.4`) |
| `--refetch` | Force re-download of the vendor .ini |
| `-v` | Verbose logging |

## Output

Eine einzelne `.orca_printer` Datei (ZIP):

```
Creality CR-5 Pro H.orca_printer
├── bundle_structure.json        ← Manifest
├── printer/*.json               ← Druckervarianten (pro Düse)
├── process/*.json               ← Druckprofile (layer heights)
└── filament/*.json              ← Filamentprofile (PLA, PETG, ABS, TPU)
```

## Installation in OrcaSlicer

```bash
# 1. .orca_printer Datei generieren
uv run prusa2orca convert Creality -p "CR-5 Pro H" -o ./CR-5-Pro-H.orca_printer

# 2. In Orca importieren:
#    File → Import → Import Configs → CR-5-Pro-H.orca_printer auswählen
#    Oder: Datei auf das Orca-Fenster ziehen
```

## How it works

PrusaSlicer `.ini` files use template inheritance:
```
[print:*common*]            → base defaults
[print:*0.16mm*]            → layer-specific overrides
    inherits = *common*
[print:0.16mm OPTIMAL...]   → concrete profile
    inherits = *0.16mm*; *0.4nozzle*
```

The tool resolves the full inheritance chain, maps Prusa parameter names to
Orca equivalents, and generates properly structured JSON files with
deterministic `setting_id` values.

## Supported vendors

Anker, Anycubic, Artillery, BIBO, BIQU, CocoaPress, Creality, E2D, Elegoo,
FLSun, Geeetech, HartSmartProducts, INAT, Infinity3D, Jubilee, LNL3D,
LulzBot, MakerGear, PapapiuLab, Print4Taste, PrusaResearch, QIDITechnology,
RatRig, Rigid3D, Snapmaker, Sovol, TriLAB, Trimaker, Ultimaker, Voron,
Zonestar, gCreate

## License

MIT
