# 3D Models

All designs use **OpenSCAD** as the source format (`.scad`) with exported STLs alongside them.

## Directory Structure

```
models/
├── enclosure/
│   ├── main_cabinet/        # Rack or desktop cabinet for the Orange Pi + USB hub + dongles
│   └── antenna_brackets/    # Mounts to route/secure antenna cables
└── antennas/                # Physical antenna assembly guides / printable parts
```

## Planned Designs

### Main Cabinet
- Houses Orange Pi Max, powered USB hub, 4× dongles
- Ventilation slots (RK3588 runs warm under load)
- Cable routing channels on rear panel
- Removable side panel for dongle access
- Optional: front panel with status LED cutouts (driven by GPIO)

### Antenna Brackets
- Window/sill mount for outdoor antenna egress
- Pole/mast clamp for rooftop antenna installation
- 19 mm (3/4") PVC mast adapter for improvised antenna mounts

### Antenna Parts
- Spider antenna base for 1090 MHz ADS-B (printable radial holder)
- Coil winding form for 5/8λ matching coil (Railroad / Marine antennas)
- Dipole spacer for portable use

## Tools Required
- [OpenSCAD](https://openscad.org/) for editing `.scad` files
- Any FDM printer, PETG or ASA preferred for outdoor parts (UV/temperature resistance)
- PETG or PLA for indoor enclosure parts

## Print Settings (general)
- Layer height: 0.2 mm
- Infill: 20–30% (40%+ for structural brackets)
- Walls: 3 perimeters
- Outdoor parts: PETG or ASA, 4 walls, 40% infill
