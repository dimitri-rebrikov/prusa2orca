# prusa2orca

Convert PrusaSlicer printer profiles (`.ini`) to OrcaSlicer JSON format — with full inheritance chain resolution.

## Features

- **Parse** PrusaSlicer `.ini` files with multi-level `inherits` chains
- **Resolve** template inheritance recursively (`*common* → *printer* → *nozzle*`)
- **Map** Prusa parameter names → Orca parameter names (100+ mappings)
- **Convert** gcode placeholders, value formats, percentage handling
- **Generate** Orca JSON files: `machine_model`, `machine`, `process`, `filament`
- **Extract** bed models (STL), bed textures (SVG), and printer thumbnails from PrusaSlicer GitHub
- **Filter** by printer model to produce only relevant profiles

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Installation

```bash
# Using uv
git clone https://github.com/<your>/prusa2orca.git
cd prusa2orca
uv sync

# Or using pip
pip install -e .
```

## Usage

### List available printers in an INI file

```bash
uv run prusa2orca list Creality.ini
```

### Convert profiles for a specific printer

```bash
uv run prusa2orca convert Creality.ini -p "Creality CR-5 Pro H" -o ./profiles
```

### Download bed models, textures, and thumbnails

```bash
uv run prusa2orca assets Creality.ini -p "Creality CR-5 Pro H" -o ./profiles
```

### Options

| Flag | Description |
|------|-------------|
| `-p, --printer` | Printer model name (e.g. `"Creality CR-5 Pro H"`) |
| `-o, --output` | Output directory (default: `./orca_profiles`) |
| `--vendor` | Vendor name (default: `Creality`) |
| `--no-assets` | Skip downloading bed models/textures |
| `-v` | Verbose debug logging |

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
│   └── ... (8 profiles for 0.4mm nozzle)
└── filament/
    ├── Creality Generic PLA @Creality ...
    ├── Creality Generic ABS @Creality ...
    └── ...
```

## Installation in OrcaSlicer

```bash
# Method 1: Copy to user config
cp -r machine/ process/ filament/ ~/.config/OrcaSlicer/system/Creality/

# Method 2: Copy to Orca source (if building from source)
cp -r machine/ process/ filament/ /path/to/OrcaSlicer/resources/profiles/Creality/
```

Then restart OrcaSlicer. Clear the system cache first if profiles don't show up:
```bash
rm -rf ~/.config/OrcaSlicer/system/Creality/
```

## How it works

PrusaSlicer `.ini` files use a template inheritance system where profiles are built from reusable sections:

```
[print:*common*]            ← base defaults (70+ params)
[print:*0.16mm*]            ← layer-specific overrides
    inherits = *common*
[print:*0.4nozzle*]         ← nozzle-specific overrides  
[print:0.16mm OPTIMAL...]   ← concrete profile
    inherits = *0.16mm*; *0.4nozzle*
```

The tool:
1. Parses all sections with Python's `configparser`
2. Classifies them as `printer_model`, `printer`, `print`, or `filament`
3. Resolves inheritance chains recursively — each template merges its own parents first, then overlays its own params
4. Maps Prusa parameter names to Orca equivalents using a 100+ entry translation table
5. Converts value formats (Prusa → Orca placeholders, percentage handling)
6. Generates properly structured Orca JSON files with deterministic `setting_id` values
7. Filters by printer model and nozzle diameter for clean output

## License

AGPL-3.0
