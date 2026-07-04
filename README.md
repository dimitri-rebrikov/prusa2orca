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
# Konvertiert Profile + lädt Bett-Modell/Textur/Thumbnail automatisch runter
uv run prusa2orca convert Creality -p "Creality CR-5 Pro H" -o ./profiles
uv run prusa2orca convert Voron -p "Voron V2.4 350" \
  --machine-inherits fdm_machine_common --process-inherits fdm_process_common \
  --nozzle 0.4 -o ./voron

# Danach in OrcaSlicer: File → Import → Import Configs → alle .json auswählen
```

### Options

| Flag | Description |
|------|-------------|
| `-p, --printer` | Printer model name (e.g. `"Creality CR-5 Pro H"`) |
| `-o, --output` | Output directory |
| `--nozzle` | Target nozzle diameter (default: `0.4`) |
| `--machine-inherits` | Orca machine base profile (default: auto-detect) |
| `--process-inherits` | Orca process base profile (default: auto-detect) |
| `--refetch` | Force re-download of the vendor .ini |
| `-v` | Verbose logging |

## Output structure

```
profiles/
├── machine/
│   ├── Creality CR-5 Pro H.json                 (machine_model)
│   ├── Creality CR-5 Pro H 0.4 nozzle.json      (machine variant)
│   ├── creality_cr5pro_buildplate_model.stl      (bed STL)
│   ├── creality_cr5pro_buildplate_texture.svg    (bed texture)
│   └── Creality CR-5 Pro H_cover.png             (thumbnail)
├── process/
│   ├── 0.06mm SuperDetail @Creality ...
│   ├── 0.20mm Standard @Creality ...
│   └── (8+ profiles per nozzle)
└── filament/
    ├── Creality Generic PLA @Creality ...
    ├── Creality Generic ABS @Creality ...
    └── ...
```

## Installation in OrcaSlicer

**Methode 1 — Per UI importieren (empfohlen):**

```bash
uv run prusa2orca convert Creality -p "CR-5 Pro H" -o ./profiles
# OrcaSlicer → File → Import → Import Configs → alle .json auswählen
```

**Methode 2 — Direkt ins User-Verzeichnis kopieren:**

```bash
# Orca einmal starten → schließen (damit User-Ordner existiert)
uv run prusa2orca convert Creality -p "CR-5 Pro H" -o ./profiles

UID=$(ls ~/.config/OrcaSlicer/user/ | head -1)
mkdir -p ~/.config/OrcaSlicer/user/$UID/creality
cp -ri profiles/* ~/.config/OrcaSlicer/user/$UID/creality/
```

> Beide Methoden legen Profile als `"from": "user"` an → **update-sicher** und via `Import Configs` kompatibel.

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
