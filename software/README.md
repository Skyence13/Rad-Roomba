# Offline four-segment mapping demonstration

From this directory, run the commands with Python 3.8 or later. No additional packages, hardware, network access or ROS installation are needed.

```sh
python3 map_demo.py --self-test
python3 map_demo.py --out demo_output
```

Open `demo_output/beta_map.svg` in a browser and `demo_output/cells.csv` in a spreadsheet. The checked-in `example_output/` contains the output generated from the supplied program. The output directory can be replaced by running the command again. Both the seed and count model are fixed. On the reference run, 640 of 880 display cells had some valid exposure. Six segment intervals were excluded. The self-test verifies geometry, reversing direction, rejection of frame duplicates and pose gaps, fault exclusion and blank data for cells with zero valid exposure.

## Technician interface

Read **Operator_Interface.md** for the production interface design. Open **guide_demo.html** directly in a phone or computer browser to try a synthetic three-stop queue, with a technician inside the trailer. Try a protected-field intrusion, an independent hands-on inhibit, a registered offset for a hand survey, and return to park. Both examples here run offline. The production webpage will be served by the onboard computer to authenticated clients.

## Data flow

1. The simulator creates a time series of base poses and per-segment count intervals on two forward-driven passes with opposite headings. The second pass is laterally shifted 43.75 mm. This is a local test region along two lane paths. No motion is generated during the intervening turnaround.
2. Four rectangular 100 × 80 mm active masks have centres 87.5 mm apart and the optical row is 204 mm in front of the drive axle. The two centre segments straddle the synthetic patch on the first pass. The detector model includes a lateral seam and a spatially varying photon background.
3. Each floor segment reports synthetic alpha-like and beta-window counts and its own reference count. Independent Poisson observations are drawn using the tabulated live times. A single uniform 90 × 60 mm patch carries 1.0 and 2.4 Bq/cm² respectively in the fixture's invented alpha and beta calibration channels. The Poisson fields and constants in the source are **simulation parameters**.
4. Processing re-reads the emitted CSV files as an **analysis fixture downstream of head decoding**. Live data from the real head travels through the interface in the ICD. The head driver must decode, validate and synchronize each record before emitting equivalent observations. The four `bins.csv` rows per period flatten the four segments in an ICD ACQ record. This fixture assumes that alpha and beta share one measured floor live-time gate. Hardware reporting unequal `segments[n].alpha.live_us` and `segments[n].beta_window.live_us` requires distinct weights and rate denominators for the two channels. The reference always has its own live time. The fixture restart and quality fields are local examples. In production the host binds the head identity, boot and approved geometry at connection and tags received intervals with that association in the archive. Routine count packets carry the sequence, acquisition time, live times, counts and health. A disconnect or lost session invalidates the binding. Host localization failures stay separate from head flags.
5. The example interpolates bracketed poses, rotates the footprint through the base heading, clips rectangles to each cell at three quadrature times per interval, and assigns a weight equal to floor-channel live time times average cell overlap fraction. The reconstruction is the weighted mean of **footprint-average segment estimates**. It illustrates motion blur, seam effects and map-cell correlations. It cannot resolve the actual local field within a tile. A larger render cell or more interpolation points cannot compensate for insufficient counts.
6. For a candidate observation the inferred concentration is `(F/tF – k·R/tR – b)/K`. Here `F` is a floor-window count, `R` a reference count, and times are in seconds. The two synthetic transfer coefficients `k` relate photon-only floor and reference count rates. Channel/segment `K` has units cps per Bq/cm². Signed estimates are retained; only the colour scale clips values.
7. Counting variance for a single observation uses `(F/tF² + k²·R/tR²)/K²`. Cell-level variance uses squared per-observation weights divided by squared total weight. It is an observed-count approximation and can understate uncertainty at very small counts. A reference count reused for the two windows induces covariance between them. Entries in adjacent cells also share the same underlying observation. The example does not propagate calibration, geometry, coincidence, spectrum or localization uncertainties. It does not compute detection limits, release status or a statistically qualified clearance map.

## Files and interpretation

| File | Contents |
|---|---|
| `poses.csv` | Fixture-clock timestamp in seconds and base-link pose in trailer coordinates. |
| `bins.csv` | Pass, sequence within the pass, segment ID, uncorrected integer counts, elapsed period, measured floor/reference live seconds, quality flag. |
| `cells.csv` | Output cell centres, valid-exposure flag, area-weighted live seconds, signed alpha/beta estimates and approximate counting SD. A blank measurement means no valid exposure. |
| `beta_map.svg` | Beta-window illustration with dashed injected patch. Grey means no valid exposure. Blue represents near-zero or negative estimates under the artificial calibration. A coloured sliver is not evidence of full spatial coverage. |

The production survey must compute union area of the uncertainty-eroded footprint and a separately validated statistical sensitivity bound. Demonstration poses are noise-free when valid. Data gaps, fault states and detector response must be qualified on the actual rover before live operation. The script sends no commands to hardware.
