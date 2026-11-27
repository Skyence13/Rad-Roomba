"""Non-connector items of the harness for parts_status.md: cables/wire, contacts, protection, devices, tools, consumables.
Each row: (item, used at, part number or NONE, source document, flag).  NONE = "no part number in any source - to be selected".
Flags: SOURCE = the number is stated in a source document and not flagged there as recalled (NOT checked against a manufacturer page by the
harness engineer); UNVERIFIED = recalled / unconfirmed in its source, or recalled by the harness engineer; TBD = no part number in any source.
WEB CHECK (2026-11-27, outbound access limited): molex.com part page 39000038 -> HTTP 503; JST GH general catalogue PDF (eGH.pdf) fetched but
no readable text (font-less PDF); Anderson SBS50 product page -> HTTP 404.  binder M16/M12 pages and Micro-Fit 43030 were not tried (the first
three attempts failed).  NOTHING in this file was verified against a manufacturer document by the harness engineer."""
NONE = "no part number in any source - to be selected"

WEB = ("not checked: molex.com 503 (39-00-0038)", "not checked: JST catalogue PDF unreadable", "not checked: Anderson page 404")

CABLES = [
    ("Silicone single-core wire AWG 12 (cassette leads W-002)", "W-002", NONE, "modules/battery_pack_and_coupler.md gives AWG 12 only", "TBD"),
    ("Silicone single-core wire AWG 14 trunk (W-001), cold-flexible, rated <= -40 C", "W-001", NONE, "power_budget.md assumes 'PVC-free 105 C' AWG 14: not a cold rating (OI-01)", "TBD"),
    ("Silicone wire AWG 16 / 18 / 20 / 22 / 24 (power, heater, chain)", "W-001..W-044 robot, W-101/W-103 head", NONE, "none", "TBD"),
    ("FEP/ETFE wire AWG 24-28 (signal, ToF, NTC, USB)", "W-009, W-013/14, W-030..W-042", NONE, "none", "TBD"),
    ("Shielded multicore 7 conductors + braid, PUR/TPE jacket <= -40 C, OD <= 7.5 mm (J1)", "W-008, W-101, W-200", NONE, "contract J1 table gives gauges only", "TBD"),
    ("Shielded 4-pair cable, OD <= 6.5 mm (J2)", "W-009, W-102, W-201", NONE, "parts.yaml j2_receptacle gives OD only", "TBD"),
    ("USB 2.0 FS shielded cable AWG 28 with drain", "W-013, W-014", NONE, "none", "TBD"),
    ("ToF cable 6 x AWG 28, 3 twisted pairs + foil + drain", "W-030..W-040", NONE, "none (layout_guidance.md calls it unshielded, OI-13)", "TBD"),
    ("50 ohm 1.13 mm micro-coax, FEP", "W-112..W-119", NONE, "head CCR-HE-06 / circuit_description.md (class only)", "TBD"),
    ("Motor six-wire pigtail (captive)", "W-006, W-007", "Pololu #2828 captive pigtail (gauge not published)", "electronics/modules/gearmotor_pololu_2828.md; parts.yaml motor", "SOURCE"),
    ("LiDAR Ethernet pigtail", "W-012", "Richbeam LakiBeam 1L pigtail (connector TBD)", "electronics/modules/lidar.md", "UNVERIFIED"),
]
CONTACTS = [
    ("Mini-Fit Jr terminal AWG 16", "J_PWR pins 1/2/5/6", "Molex 39-00-0078", "electronics/chassis_main/design/connectors.yaml (verify: true)", "UNVERIFIED"),
    ("Mini-Fit Jr terminal AWG 18-24", "J_PWR rest; J_HEAD1 all (S2-02)", "Molex 39-00-0038 (stage 2 file also says '5556 terminals 18-24 AWG')", "connectors.yaml; chassis_main/STAGE2_CHANGE_REQUESTS.md S2-02 ([U, part numbers recalled])", "UNVERIFIED"),
    ("Mini-Fit Jr receptacle housing 10-way / 8-way", "J_HEAD1 / J_PWR", "Molex 39-01-2100 / 39-01-2080", "STAGE2 S2-02 ('39-01-2100 class') / connectors.yaml", "UNVERIFIED"),
    ("Micro-Fit 3.0 terminal AWG 20-24 / 26-30", "J_CM5, J_HTR, J_LIDAR, J_MOT_x, motor plugs", "Molex 43030-0007 / 43030-0010", "connectors.yaml (verify: true)", "UNVERIFIED"),
    ("Micro-Fit 3.0 terminal AWG 18 variant", "head J2001 pins 3/4, J2601 pins 1/2 (OD-3)", NONE + " ('43030 18-24 AWG variant', suffix not given)", "head_acq/design/circuit.py note", "UNVERIFIED"),
    ("Micro-Fit receptacle housings", "chassis side / head side", "Molex 43025-xx00 / 43645-xx00", "connectors.yaml / head circuit.py", "UNVERIFIED"),
    ("CLIK-Mate terminal AWG 24-30; housing 502439-xx00", "J_MODE, J_ESTOP, J_HANDS, J_COVER, J_DOCK, J_BUMP_x, J_BTN", "Molex 502438-0000; 502439-xx00", "connectors.yaml (verify: true)", "UNVERIFIED"),
    ("JST GH contact AWG 26-30; housing GHR-xxV-S", "all GH connectors (J_PAUSE: GHR-05V-S)", "JST SSHL-002T-P0.2; GHR-xxV-S", "connectors.yaml (verify: false: not flagged)", "SOURCE"),
    ("binder M16 8-pole contacts (solder cup / crimp), wire range vs 0.75 mm2", "J1R, J1P, J1X", NONE + " (family only)", "contract; parts.yaml j1_receptacle", "TBD"),
    ("binder M12 A-coded 8-pole contacts", "J2R, J2P, J2X", NONE + " (family only)", "contract; parts.yaml j2_receptacle", "TBD"),
    ("M12 L-coded 4+FE inlet / plug", "INLET, CHGPLUG", NONE, "external_24v_supply.md", "TBD"),
    ("Anderson SBS50 housings, power contacts, auxiliary contact kit", "CPL-B, CPL-C", "Anderson Power SBS50 (candidate; contacts and kit not named)", "battery_pack_and_coupler.md; parts.yaml battery_coupler", "UNVERIFIED"),
    ("Insulated faston receptacle 6.35 mm", "W-002", NONE, "battery_pack_and_coupler.md", "TBD"),
    ("U.FL / MHF plug for 1.13 mm coax", "W-112..W-119 board ends", NONE + " (class: I-PEX MHF I LK or U.FL-LP)", "head circuit.py J101 note", "TBD"),
    ("USB-A plug", "W-013, W-014", NONE, "none", "TBD"),
    ("Crimp splice, sealed (1-to-2)", "SPL-P, SPL-N, SPL-HCUT", NONE, "none (splice resistance not in power_budget.md)", "TBD"),
]
PROTECT = [
    ("Main blade fuse 20 A, 32 V, >= 1 kA", "W-001", NONE, "power_budget.md section 5", "TBD"),
    ("Fuse holder (blade)", "W-001", NONE, "none", "TBD"),
    ("Cassette fuse (recommended, not adopted)", "W-002", NONE, "battery_pack_and_coupler.md", "TBD"),
    ("Bimetal cut-outs (bay >= 3.04 A at 14.4 V DC; head low side)", "W-041, W-103", NONE, "CCR-E08(e); head circuit.py", "TBD"),
]
DEVICES = [
    ("Omron D2HW-C201M sealed SPDT (bumpers, dock, cover, rail switches)", "W-005, W-020, W-021/22, W-104..106", "Omron D2HW-C201M", "mechanical/common/purchased/parts.yaml bumper_switch (temp, IP67 marked VERIFIED there; modules sheet tags it [U])", "SOURCE"),
    ("Schneider XB5AS8444 E-stop", "W-015", "XB5AS8444", "parts.yaml estop", "SOURCE"),
    ("Mode selector, HANDS-ON, REARM, PAUSE (XB5 family)", "W-016..W-019", "XB5AD33 candidate; ZBE-101/ZBE-102 blocks; HANDS-ON, REARM, PAUSE references TBD", "estop_and_operator_switches.md", "UNVERIFIED"),
    ("Heater films (bay 12 V 20 W 7.2 ohm; head 4.8 ohm)", "W-041, W-103", NONE, "parts.yaml; head circuit.py", "TBD"),
    ("NTC 10 kohm B3435 (bay, pack surface, cassette) and spreader / lane NTCs", "W-002, W-042, W-103, W-108..111", NONE, "none", "TBD"),
    ("Lid interlock switch", "W-107", NONE, "head circuit.py J2201", "TBD"),
    ("External sounder (optional)", "W-024", NONE + " (class XB5KSB/XB5KS2)", "panel circuit.py", "TBD"),
    ("Bus-clamp resistor: NOT a harness part (on-board 2 x CRM2512-JW-9R1ELF, Bourns)", "board", "Bourns CRM2512-JW-9R1ELF", "chassis_main/design/circuit.py (verify=True)", "UNVERIFIED"),
]
TOOLS = [
    ("Crimp tool Mini-Fit Jr (39-00-xxxx terminals)", "J_PWR, J_HEAD1, W-001, W-004, W-008"),
    ("Crimp tool Micro-Fit 3.0 (43030 terminals)", "J_CM5, J_HTR, J_LIDAR, J_MOT_x, head J2001/J2601"),
    ("Crimp tool CLIK-Mate (502438)", "safety looms W-005, W-015..W-018, W-020..W-022"),
    ("Crimp tool JST GH (SSHL-002T-P0.2)", "ToF, panel, NTC, USB, J_PAUSE, J_HEAD2"),
    ("Insertion / extraction tools for the four families", "rework"),
    ("binder M16/M12 solder or crimp tooling, backshell clamp tools", "J1/J2 plugs, LAB extension"),
    ("SBS50 contact crimp tool", "CPL-B, CPL-C"),
    ("U.FL / MHF plug termination tooling for 1.13 mm coax", "W-112..W-119"),
    ("Faston crimp tool", "W-002"),
    ("Four-wire milliohm meter (the power budget assumes 5 mohm per contact pair)", "first-build verification"),
    ("Continuity / insulation tester for the safety looms", "chassis_safety_chain.md section 8"),
    ("Wire stripper, heat gun, label printer for W-xxx.n sleeves", "all"),
]
CONSUMABLES = [
    ("Adhesive-lined heat-shrink boots", "strain relief (STRAIN table)"), ("Yellow safety-loom sleeve", "chain looms"),
    ("Printed wire-number sleeves / labels W-xxx.n", "all cables"), ("P-clips / saddle ties", "all cables"),
    ("Cable glands / sealed strain relief (head rear wall)", "W-101, W-102"), ("Backshell strain-relief clamps", "J1/J2 plugs"),
    ("High-temperature (Kapton) tape and clips", "heater leads W-041, W-103"), ("Adhesive tack for coax pigtails", "W-112..W-119"),
]
