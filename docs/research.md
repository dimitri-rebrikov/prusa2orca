# OrcaSlicer Profile Architecture — Research Notes

## 1. Profile Types

OrcaSlicer uses four profile types, stored as JSON files:

| Type | `type` field | Purpose | Example |
|------|-------------|---------|---------|
| **machine_model** | `"machine_model"` | Printer series definition | `Creality CR-5 Pro H.json` |
| **machine** | `"machine"` | Printer variant (per nozzle) | `Creality CR-5 Pro H 0.4 nozzle.json` |
| **process** | `"process"` | Print quality/speed settings | `0.20mm Standard @Creality ...` |
| **filament** | `"filament"` | Material profile | `Generic PLA @Creality ...` |

Source: [OrcaSlicer Wiki — How to Create Profiles](https://www.orcaslicer.com/wiki/developer_reference/how_to_create_profiles.html)

---

## 2. File Locations

OrcaSlicer loads profiles from two locations:

### System profiles (`resources/profiles/`)
- Shipped with the application
- Vendor directory structure: `resources/profiles/<Vendor>/`
  - `machine/fdm_machine_common.json` — base machine template
  - `machine/fdm_<vendor>_common.json` — vendor-specific overrides
  - `machine/<Printer> <Variant>.json` — concrete printer variants
  - `process/` — print process profiles
  - `filament/` — filament profiles
- Registered in `resources/profiles/<Vendor>.json` (vendor manifest)
- Read-only in UI (cannot edit directly)

### User profiles (`~/.config/OrcaSlicer/user/<UID>/`)
- Created by user modifications in UI
- Or imported via `File → Import → Import Configs`
- Subdirectories: `machine/`, `process/`, `filament/`

### Cached system profiles (`~/.config/OrcaSlicer/system/<Vendor>/`)
- Mirror of `resources/profiles/<Vendor>/` — used at runtime
- Rebuilt on version mismatch during Orca startup
- **Not safe for manual placement** — deleted on updates

---

## 3. Inheritance System

### System profile inheritance

Profiles inherit from base templates via the `"inherits"` field:

```
fdm_machine_common              (universal machine base)
  └── fdm_creality_common       (Creality-specific machine overrides)
       └── Creality CR-5 Pro H 0.4 nozzle   (concrete instance)
```

```
fdm_process_common               (universal process base)
  └── fdm_process_creality_common (Creality process overrides)
       └── 0.20mm Standard @Creality ...     (concrete instance)
```

The `"instantiation"` field distinguishes:
- `"instantiation": "false"` — base template (not user-selectable, no `setting_id`)
- `"instantiation": "true"` — concrete instance (user-selectable, has `setting_id`)

Source: [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/developer_reference/how_to_create_profiles.html#setting-ids)

### User profile inheritance

User profiles created via UI or Import Configs use a different format (see §5).

---

## 4. System Profile JSON Format

### machine_model
```json
{
    "type": "machine_model",
    "name": "Creality CR-5 Pro H",
    "model_id": "Creality-CR5-Pro-H",
    "nozzle_diameter": "0.4",
    "machine_tech": "FFF",
    "family": "Creality",
    "bed_model": "creality_cr5pro_buildplate_model.stl",
    "bed_texture": "creality_cr5pro_buildplate_texture.svg",
    "hotend_model": "",
    "default_materials": "Creality Generic PLA;..."
}
```
- No `setting_id` (base profile)
- `"instantiation": "false"`

### machine (variant)
```json
{
    "type": "machine",
    "name": "Creality CR-5 Pro H 0.4 nozzle",
    "inherits": "fdm_creality_common",
    "from": "system",
    "setting_id": "ZOxwNAzICHVJnfKk",
    "instantiation": "true",
    "printer_model": "Creality CR-5 Pro H",
    "printer_structure": "i3",
    "nozzle_diameter": ["0.4"],
    "printable_area": ["5x5", "295x5", "295x220", "5x220"],
    "printable_height": "380",
    "retraction_length": ["3"]
}
```

### process
```json
{
    "type": "process",
    "name": "0.20mm Standard @Creality CR-5 Pro H 0.4",
    "inherits": "fdm_process_creality_common",
    "from": "system",
    "setting_id": "AIB92VWGReN",
    "instantiation": "true",
    "layer_height": "0.20",
    "bottom_shell_layers": "4",
    "compatible_printers": ["Creality CR-5 Pro H 0.4 nozzle"]
}
```

### filament
```json
{
    "type": "filament",
    "name": "Generic PLA @System",
    "inherits": "fdm_filament_pla",
    "from": "system",
    "setting_id": "GFL99",
    "instantiation": "true",
    "filament_type": ["PLA"],
    "nozzle_temperature": ["205"]
}
```

---

## 5. User Profile JSON Format (Import Configs)

**Critical finding from GitHub Issue #12223:**

User process presets require a **completely different JSON format** from system presets. This format is undocumented in Orca's wiki.

### User process preset
```json
{
    "from": "User",
    "inherits": "0.20mm Standard @Qidi XPlus4",
    "is_custom_defined": "0",
    "name": "My Custom Preset",
    "print_settings_id": "My Custom Preset",
    "version": "2.3.1.10",
    "wall_loops": "3"
}
```

### Rules for user-format JSON
- **No** `type`, `setting_id`, `instantiation` fields
- **No** `compatible_printers` (causes "import corresponding printer first" error)
- `"from": "User"` — **capital U** required
- `"is_custom_defined": "0"` — required
- `"version": "<OrcaVersion>"` — required
- `"<type>_settings_id": "<name>"` — required (`print_settings_id`, `filament_settings_id`, `printer_settings_id`)
- `"inherits": ""` — empty string for standalone profiles
- Only the **diff** (changed values) should be included, not all settings

Source: [GitHub Issue #12223](https://github.com/OrcaSlicer/OrcaSlicer/issues/12223)

---

## 6. .orca_printer Bundle Format

A **ZIP archive** containing:
```
bundle.orca_printer
├── bundle_structure.json          ← manifest
├── printer/*.json                 ← printer variant(s)
├── process/*.json                 ← process profile(s)
└── filament/*.json                ← filament profile(s)
```

### bundle_structure.json
```json
{
    "bundle_id": "_CR-5 Pro H_20260704184407",
    "bundle_type": "printer config bundle",
    "printer_config": ["printer/Creality CR-5 Pro H 0.4 nozzle.json"],
    "process_config": ["process/..."],
    "filament_config": ["filament/..."],
    "version": "01.10.01.01"
}
```

Orca handles these extensions identically (all ZIP-based):
- `.orca_printer` — printer config bundle
- `.orca_bundle` — alias for `.orca_printer`
- `.orca_filament` — filament bundle
- `.zip` — generic fallback

Source: [OrcaSlicer PresetBundle.cpp line 1323](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/PresetBundle.cpp)

---

## 7. PrusaSlicer .ini Format

### Section types
```
[vendor]                           → vendor metadata
[printer_model:ENDER3]             → printer model definition
[print:*common*]                   → print template (wildcard = template)
[print:0.16mm OPTIMAL @CREALITY]   → concrete print profile
[filament:*PLA*]                   → filament template
[filament:Generic PLA @CREALITY]   → concrete filament profile
[printer:*CR5PROH*]                → printer template
[printer:Creality CR-5 Pro H ...]  → concrete printer profile
```

### Inheritance
Templates use semicolon-separated `inherits` lists, last-inherited wins:
```ini
[print:0.16mm OPTIMAL (0.4 mm nozzle) @CREALITY]
inherits = *0.16mm*; *0.4nozzle*
```

Resolution order:
1. `[print:*common*]` (base defaults, ~70 params)
2. `[print:*0.16mm*]` (layer-specific: `layer_height=0.16`, `bottom_solid_layers=5`)
3. `[print:*0.4nozzle*]` (nozzle-specific: `extrusion_width=0.44`, `perimeters=3`)
4. Concrete profile (`top_solid_layers=7`)

PrusaSlicer uses `*wildcard*` section names for templates — they are NOT user-selectable.

### Printer template chain (CR-5 Pro H example)
```
[printer:*common*]                  → base: gcode_flavor, machine limits, retraction
  └── [printer:*bowdenallmetalhotend*]  → retract_length = 3
       └── [printer:*slowabl*]          → G29 ABL start gcode (large bed)
            └── [printer:*descendingz*] → descending Z end gcode
                 └── [printer:*CR5PROH*]  → bed_shape, max_print_height, printer_model
                      └── [printer:*0.4nozzle*] → nozzle_diameter, layer height range
```

### Template file (Creality.ini)
- 422 sections, ~110KB
- Shared across all Creality printers
- Templates are per-vendor, stored in `resources/profiles/<Vendor>.ini`

Source: [Prusa3D GitHub](https://github.com/prusa3d/PrusaSlicer/blob/master/resources/profiles/Creality.ini)

---

## 8. Parameter Mapping

### Print settings (Prusa → Orca)
| Prusa Key | Orca Key | Notes |
|-----------|----------|-------|
| `layer_height` | `layer_height` | 1:1 |
| `bottom_solid_layers` | `bottom_shell_layers` | Renamed |
| `top_solid_layers` | `top_shell_layers` | Renamed |
| `fill_density` | `sparse_infill_density` | Renamed |
| `fill_pattern` | `sparse_infill_pattern` | Renamed |
| `perimeters` | `wall_loops` | Renamed |
| `perimeter_speed` | `inner_wall_speed` | Split in Orca |
| `external_perimeter_speed` | `outer_wall_speed` | Split in Orca |
| `infill_speed` | `sparse_infill_speed` | Renamed |
| `first_layer_speed` | `initial_layer_speed` | Renamed |
| `support_material` | `enable_support` | Renamed |
| `support_material_xy_spacing` | `support_object_xy_distance` | Renamed |
| `skirts` | `skirt_loops` | Renamed |
| `bridge_flow_ratio` | `bridge_flow` | Renamed |
| `default_acceleration` | `default_acceleration` | 1:1 — also expanded to inner/outer/infill/initial/top |
| `bridge_acceleration` | `bridge_acceleration` | 1:1 |

### Filament settings
| Prusa Key | Orca Key | Notes |
|-----------|----------|-------|
| `bed_temperature` | `hot_plate_temp` | Renamed |
| `temperature` | `nozzle_temperature` | Renamed |
| `first_layer_temperature` | `nozzle_temperature_initial_layer` | Renamed |
| `extrusion_multiplier` | `filament_flow_ratio` | Renamed |
| `filament_max_volumetric_speed` | `filament_max_volumetric_speed` | Prusa 0 → Orca 15 |
| `bridge_fan_speed` | `overhang_fan_speed` | Renamed |

### Printer settings
| Prusa Key | Orca Key | Notes |
|-----------|----------|-------|
| `bed_shape` | `printable_area` | Same format "XxY" list |
| `max_print_height` | `printable_height` | Renamed |
| `retract_length` | `retraction_length` | Renamed |
| `retract_speed` | `retraction_speed` | Renamed |
| `deretract_speed` | `deretraction_speed` | Renamed |
| `retract_lift` | `z_hop` | Renamed |
| `start_gcode` | `machine_start_gcode` | 1:1 with placeholder conversion |
| `end_gcode` | `machine_end_gcode` | 1:1 with placeholder conversion |

### Placeholder conversion
Prusa-style → Orca-style:
| Prusa | Orca |
|-------|------|
| `{first_layer_bed_temperature[0]}` | `[hot_plate_temp_initial_layer_single]` |
| `{first_layer_temperature[0]}` | `[nozzle_temperature_initial_layer]` |
| `{temperature[0]}` | `[nozzle_temperature]` |
| `{filament_type[0]}` | `[filament_type]` |
| `{max_print_height}` | `printable_height` |
| `{is_nil(idle_temperature[0]) ? 150 : idle_temperature[0]}` | simplified |

---

## 9. setting_id Generation

OrcaSlicer uses a deterministic algorithm for `setting_id`:

```
setting_id = base62( uuid5(namespace="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                           name="<vendor>/<type>/<profile_name>") )
```

- Only for `"instantiation": "true"` profiles
- Globally unique across all vendors
- Deterministic: same inputs always produce same id
- Base62 charset: `0-9A-Za-z`
- Takes first 16 hex chars of UUID5, encodes to base62

Source: [OrcaSlicer Wiki](https://www.orcaslicer.com/wiki/developer_reference/how_to_create_profiles.html#setting-ids)

---

## 10. Key GitHub Issues

| Issue | Summary |
|-------|---------|
| [#1648](https://github.com/OrcaSlicer/OrcaSlicer/issues/1648) | Request: Allow import of PrusaSlicer .ini files — never implemented |
| [#12223](https://github.com/OrcaSlicer/OrcaSlicer/issues/12223) | **Critical**: User process presets require completely different JSON format from system presets. No `type`, `setting_id`, `instantiation`, `compatible_printers`. Must use `"from": "User"`, add `is_custom_defined`, `version`, `<type>_settings_id`. |
| [#10939](https://github.com/OrcaSlicer/OrcaSlicer/issues/10939) | Cannot export user process presets (export button broken) |
| [#9536](https://github.com/OrcaSlicer/OrcaSlicer/issues/9536) | Cannot inherit from user profiles — only system profiles can be parents |
| [#4944](https://github.com/OrcaSlicer/OrcaSlicer/issues/4944) | "0 configs imported" — silent failure with wrong format |
| [#1213](https://github.com/OrcaSlicer/OrcaSlicer/issues/1213) | Cannot import process profiles — matching `compatible_printers` string exactly required |

---

## 11. Existing Conversion Tools

| Tool | Language | Approach | Status |
|------|----------|----------|--------|
| [nerdCopter/Prusa2Orca](https://github.com/nerdCopter/Prusa2Orca) | Python/Tkinter | GUI tool, 13 print param mappings, no inherits resolution | Unmaintained fork of robertoSreis/Prusa2Orca |
| [theophile/SuperSlicer_to_Orca](https://github.com/theophile/SuperSlicer_to_Orca_scripts) | Perl | CLI tool, 60+ mappings, handles inherits, percent→absolute conversion | 310 stars, last commit Mar 2024 |
| samwiseg0 [Gist](https://gist.github.com/samwiseg0/3d4cb07742db83343bf7ef381c7c86b3) | Python | Filament-only converter, 38 mappings | Simple, no inherits |

### Key limitations of existing tools
- None resolve Prusa's `*wildcard*` template inheritance chain
- None output `.orca_printer` bundles
- None use the correct user-format (`"from": "User"`)
- None are vendor-agnostic (most hardcode Creality paths)

---

## 12. Design Decisions for prusa2orca

| Design Decision | Rationale |
|----------|-----------|
| **Remote INI fetching** | No local files needed — fetches from PrusaSlicer GitHub on demand |
| **Vendor-agnostic** | Single codebase handles Creality, Voron, Anycubic, etc. |
| **`.orca_printer` output** | Orca's native import format — drag & drop or Import Configs |
| **User-format JSONs** | `"from": "User"` — update-safe, no system directory manipulation |
| **`inherits=""` für alle Typen** | User-Format kann System-Templates (`fdm_machine_common`, `fdm_filament_pla`) nicht referenzieren — `find_preset2()` findet nur user-facing Presets, keine Base-Templates mit `instantiation: false`. Quelle: [Preset.cpp Zeile 1684–1701](https://github.com/OrcaSlicer/OrcaSlicer/blob/main/src/libslic3r/Preset.cpp). Gilt für Printer, Process **und** Filament gleichermaßen. |
| **Orca-Template-Defaults von GitHub** | `remote.get_orca_template()` holt `fdm_process_common.json`, `fdm_machine_common.json`, `fdm_filament_*.json` zur Laufzeit von OrcaSlicer's GitHub. Fallback: vendor-spezifisch → `Default/`. Werden als Basis gesetzt, Prusa-Werte überschreiben. Keine hartcodierten Defaults. |
| **Acceleration-Expandierung** | Da `inherits=""`, müssen alle Orca-Felder explizit gesetzt sein. Prusa's `default_acceleration` wird auf alle per-move Acceleration-Felder expandiert. |
| **Prusa-Werte explizit übernommen** | Alle Werte aus der `.ini` werden explizit gesetzt. `inherits=""` ist korrekt für neue Drucker ohne existierendes Parent-Preset. |
| **No hardcoded fallbacks** | Every value must come from the Prusa source data |
| **Deterministic filenames** | Profile names sanitized for cross-platform filesystem compatibility |

## 13. Re-Import / Overwriting Profiles

Wenn ein `.orca_printer` Bundle bereits importiert wurde und erneut
importiert werden soll (z. B. nach einer Neugenerierung), muss OrcaSlicer
den alten Bundle-Cache löschen. Sonst ignoriert der Import die neuen Dateien.

### Vorgehen

1. **OrcaSlicer schließen**
2. **Alten Bundle-Ordner löschen** — je nach OS:

   | OS | Pfad |
   |---|---|
   | **Windows** | `%APPDATA%\OrcaSlicer\user\default\_local\<bundle_id>\` |
   | **Linux** | `~/.config/OrcaSlicer/user/<UID>/local/<bundle_id>/` |
   | **macOS** | `~/Library/Application Support/OrcaSlicer/user/<UID>/local/<bundle_id>/` |

   Die `<bundle_id>` steht in der `bundle_structure.json` des `.orca_printer`-Bundles
   (z. B. `_Creality CR-5 Pro H_20260704184407`).

3. **Oder gesamten `_local`-Ordner leeren** (entfernt alle importierten Bundles):

   ```bash
   # Linux
   rm -rf ~/.config/OrcaSlicer/user/*/local/*/

   # Windows (PowerShell)
   Remove-Item "$env:APPDATA\OrcaSlicer\user\*\_local\*\" -Recurse
   ```

4. **OrcaSlicer starten** und `.orca_printer` erneut importieren
   (`File → Import → Import Configs`)

### Hintergrund

Beim Import speichert Orca die Profile unter `user/<UID>/local/<bundle_id>/`.
Die `bundle_id` wird aus dem Bundle generiert. Ein erneuter Import mit derselben
`bundle_id` wird von Orca als "bereits vorhanden" erkannt und ignoriert —
selbst wenn sich der Inhalt geändert hat. Daher muss der alte Ordner vorher
gelöscht werden.

