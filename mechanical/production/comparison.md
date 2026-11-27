# Prototype (X1C) vs production: comparison (calculated / tool-counted)

Counts from the two models (prototype: `prototype_x1c/out/parts_table.json`, `checks.json` and `rrx/hardware.py`; production: this build). Process content is given as physical quantities per unit (pieces, material volume, bounding-box volume, set-ups, inserts); no prices are estimated.

| Quantity | X1C prototype | Production | Change |
|---|---|---|---|
| Unique made part numbers (robot) | 52 | 44 | -8 |
| Made pieces per robot | 69 | 61 | -8 |
| Skin pieces (lower hull + lid) | 10 | 2 | -8 |
| Purchased part numbers (envelopes in the model) | 26 | 26 | +0 |
| Fasteners: threaded fasteners (screws, nuts) | 183 | 167 | -16 |
| Fasteners: pins and dowels | 18 | 12 | -6 |
| Fasteners: heat-set inserts | 142 | 118 | -24 |
| Fasteners: washers and bushings | 42 | 42 | +0 |
| Fasteners: total | 385 | 339 | -46 |
| Mass with head 'none' (kg) | 6.7 | 7.36 | +0.66 |
| CG x with head 'none' (mm) | -92.5 | -90.7 | +1.80 |
| Forward tip margin with head 'none' (mm) | 81.9 | 80.2 | -1.70 |
| Mass with head 'prototype head RR-HD-X' (kg) | 8.56 | 9.23 | +0.67 |
| CG x with head 'prototype head RR-HD-X' (mm) | -46.6 | -48.4 | -1.80 |
| Forward tip margin with head 'prototype head RR-HD-X' (mm) | 37.4 | 39.2 | +1.80 |
| Mass with head 'production head' (kg) | 8.78 | 9.44 | +0.66 |
| CG x with head 'production head' (mm) | -42.1 | -44.2 | -2.10 |
| Forward tip margin with head 'production head' (mm) | 33.1 | 35.1 | +2.00 |
| Mass with head 'production head + 15 % margin' (kg) | 9.09 | 9.76 | +0.67 |
| CG x with head 'production head + 15 % margin' (mm) | -36.5 | -39.0 | -2.50 |
| Forward tip margin with head 'production head + 15 % margin' (mm) | 27.7 | 30.0 | +2.30 |

## Per-unit process content (calculated from the solids)

**X1C prototype:**

| Process | Pieces | Material volume (cm3) |
|---|---|---|
| FFF print (X1C) | 47 | 1919 |
| fabricated (metal / G10) | 22 | 356 |

Print plates: 20 (prototype `plates.yaml`); heat-set inserts set by hand: 142.

**Production:**

| Process | Pieces | Material volume (cm3) | Bounding-box volume (cm3, SLS packing / stock proxy) |
|---|---|---|---|
| CNC machined 6061-T6 | 9 | 176 | 685 |
| SLS PA11 (large-frame laser sintering) | 2 | 946 | 16099 |
| SLS PA11 (nested in the skin builds) | 31 | 702 | 5223 |
| cast polyurethane (open / two-part mould) | 2 | 132 | 541 |
| laser / waterjet cut sheet | 6 | 36 | 77 |
| laser cut + press-brake bent sheet | 1 | 33 | 34 |
| sheet cut + surface ground | 4 | 3 | 4 |
| turned / milled bar | 5 | 33 | 45 |
| waterjet / laser blank + CNC (one fixture) 6061-T6 | 1 | 197 | 287 |

Machined pieces 15 (2-3 set-ups each assumed, channels 3: slot from below, ears from above, cross holes); heat-set inserts 118 (was 142); skin joints to seal: 1 perimeter (was 1 perimeter + 2 lid flanges + hump curb + hull splice + y = 0 butt joints).

Reading: production removes the bed-size splits (skins 10 -> 2 pieces), the joint hardware that came with them and the inserts in the parts that became aluminium; it adds mass because SLS parts are fully dense (printed parts were 72-85 % fill) and the pods and rims are aluminium. The check suite and the interfaces are identical (see production_report.md).
