"""Connector inventory for the whole robot and head.  Board connectors are pulled from the authoritative circuit
definitions; non-board connectors (panel receptacles, inline halves, module and device ends) are tabulated here with
the source of every field.  Status vocabulary:
  verified     = not flagged as recalled/unconfirmed in its source
  UNVERIFIED   = the source flags the item as recalled/unconfirmed
  TBD          = "TBD - not in sources"
"""
import re
from hsrc import src, parts_by_ref

TBD = "TBD - not in sources"
NC = "NC"

ALIASES = {"HEAD_PWR_N": "GND", "BUS_GND": "GND", "PACK_N": "GND", "NC_RESERVED": "NC", None: "NC"}

# ---------------------------------------------------------------- family properties (as stated in the sources)
FAM = {
    "MINIFIT": dict(seal="none stated: unsealed board header inside the shell (no IP rating in sources)",
                    temp="-40 C family (CCR-E05: 'All power and safety connectors are -40 C families'); no datasheet figure in sources",
                    tstat="UNVERIFIED", keying="polarised housing; two Mini-Fit Jr headers on the board with different circuit counts (J_PWR 8, J_HEAD1 10, stage 2 S2-02), so they cannot be cross-mated", geom="dual"),
    "MICROFIT": dict(seal="none stated: unsealed board header inside the shell (no IP rating in sources)",
                     temp="-40 C family (CCR-E05); no datasheet figure in sources", tstat="UNVERIFIED",
                     keying="polarised housing; families cannot cross-mate, same-circuit-count housings can be swapped (see same_count_as)", geom="dual"),
    "CLIK": dict(seal="none stated: unsealed board header inside the shell (no IP rating in sources)",
                 temp="-40 C family (CCR-E05); no datasheet figure in sources", tstat="UNVERIFIED",
                 keying="polarised housing; SAFETY family, yellow wire; cannot mate GH/Micro-Fit/Mini-Fit; same-count CLIK housings can be swapped (see same_count_as)", geom="single"),
    "GH": dict(seal="none stated: unsealed (inside the shell)", temp="-25..+85 C [U] (circuit.py notes, CCR-E05): no margin at -25 C, IB-08 open",
               tstat="UNVERIFIED", keying="polarised housing (JST GH); 4/5/6-pin same-count housings can be swapped (see same_count_as)", geom="single"),
}

SWAPS = {}  # filled from connectors.yaml same_count_as


def gh_mating(n):
    return "GHR-%02dV-S" % n, "SSHL-002T-P0.2 (AWG 26-30)"


def board_chassis():
    S = src()
    out = {}
    for c in S["chs_conn_yaml"]["connectors"]:
        ref = c["ref"]
        fam = ("MINIFIT" if "Mini-Fit" in c["family"] else "MICROFIT" if "Micro-Fit" in c["family"] else
               "CLIK" if "CLIK" in c["family"] else "GH" if "GH" in c["family"] else "IDC")
        F = FAM.get(fam, dict(seal="none stated", temp=TBD, tstat="TBD", keying="shrouded keyed header (FTSH 'K' = key)", geom="idc"))
        pins = {str(k): (v["net"]) for k, v in c["pins"].items()}
        out["CHS." + ref] = dict(
            id="CHS." + ref, board="RR-CHS-MAIN", ref=ref, location="RR-CHS-MAIN, " + c["position"], function=c["function"],
            kind="board_header", mpn=c["board_mpn"], mpn_status="UNVERIFIED" if c["verify"] else "verified (not flagged in source)",
            mating=c["mating_housing"], mating_status="UNVERIFIED" if c["verify"] else "verified (not flagged in source)",
            contacts=c["mating_contacts"], seal=F["seal"], temp=F["temp"], temp_status=F["tstat"], keying=F["keying"],
            geom=F["geom"], family=c["family"], pins=pins,
            awg_rec={str(k): v["awg"] for k, v in c["pins"].items()}, max_current_a=c["max_current_a"],
            same_count_as=c.get("same_count_as"), source="electronics/chassis_main/design/connectors.yaml + circuit.py", notes=c["detail"])
    return out


def _head_loc(ref):
    S = src()
    from hsrc import _pinmap_centres
    c = _pinmap_centres(S["hd_pinmap"]).get(ref)
    return "RR-HEAD-ACQ (head), stage-2 placement: centre (u, v) = %s mm (out/pinmap.json)" % ("(%.1f, %.1f)" % c if c else "n/a")


def board_head():
    S = src()
    hd = S["hd"]
    P = parts_by_ref(hd)
    out = {}
    for ref, info in hd.CONNECTORS.items():
        p = P[ref]
        n = len([k for k in p["pins"] if k != "MP"])
        pins = {}
        for k, v in p["pins"].items():
            if k == "MP":
                continue
            pins[str(k)] = (v[1] if v else NC)
        if p["package"] == "U.FL receptacle":
            kind, geom = "board_header", "coax"
            mating, contacts = TBD + " (circuit.py note: I-PEX MHF I LK locking or U.FL-LP class plug on 1.13 mm 50 ohm micro-coax)", TBD
            seal, temp, tstat = "none stated (inside the head shell)", TBD, "TBD"
            keying = "U.FL snap-on; not polarised against other U.FL receptacles: eight anode + eight bias jacks look identical, identify by label/colour"
        elif p["package"].startswith("JST GH"):
            kind, geom = "board_header", "single"
            m, c = gh_mating(n)
            mating, contacts = m, c
            seal, temp, tstat = FAM["GH"]["seal"], FAM["GH"]["temp"], FAM["GH"]["tstat"]
            keying = FAM["GH"]["keying"]
        elif "Micro-Fit" in p["package"]:
            kind, geom = "board_header", "single_ra"
            mating = "43645-%02d00 (circuit.py note; mating housing not in the chassis tables)" % n
            contacts = "43030 'AWG 18-24 variant for the heater pair' (circuit.py note; suffix not in sources)"
            seal, temp, tstat = "none stated (inside the head shell)", "-40 C family (CCR-E05); no figure in sources", "UNVERIFIED"
            keying = "polarised housing (Micro-Fit 3.0 single row); right-angle header"
        elif "TC2030" in p["package"]:
            kind, geom = "feature", "none"
            mating, contacts, seal, temp, tstat = "Tag-Connect TC2030-IDC-NL cable (spring-pin, no component fitted)", "-", "n/a", TBD, "TBD"
            keying = "alignment pins of the TC2030 footprint"
        elif p["package"].startswith("solder jumper"):
            kind, geom = "feature", "none"
            mating, contacts, seal, temp, tstat, keying = "n/a (solder bridge)", "-", "n/a", "n/a", "n/a", "n/a"
        else:
            raise SystemExit("unclassified head connector %s %s" % (ref, p["package"]))
        out["HEAD." + ref] = dict(
            id="HEAD." + ref, board="RR-HEAD-ACQ", ref=ref, location=_head_loc(ref), function=info["description"],
            kind=kind, mpn=("%s %s" % (info["manufacturer"], info["mpn"])), mpn_status="UNVERIFIED" if p["verify"] else "verified (not flagged in source)",
            mating=mating, mating_status="UNVERIFIED" if p["verify"] or "Micro-Fit" in p["package"] else ("TBD" if mating.startswith(TBD) else "verified (not flagged in source)"),
            contacts=contacts, seal=seal, temp=temp, temp_status=tstat, keying=keying, geom=geom, family=p["package"], pins=pins,
            awg_rec={}, max_current_a=None, same_count_as=None, source="electronics/head_acq/design/circuit.py", notes=p["notes"] or "")
    for ref in ("TP2004", "TP2501"):
        p = P[ref]
        out["HEAD." + ref] = dict(
            id="HEAD." + ref, board="RR-HEAD-ACQ", ref=ref, location="RR-HEAD-ACQ (head), next to the J1/J2 landings", function=p["description"] + " (cable shield drain lands here: 1 Mohm || 10 nF to FRAME on the board)",
            kind="board_pad", mpn="%s %s" % (p["manufacturer"], p["mpn"]), mpn_status="verified (not flagged in source)", mating="drain wire soldered to the pad", mating_status="n/a", contacts="-",
            seal="none stated (inside the head shell)", temp="n/a", temp_status="n/a", keying="n/a", geom="list", family="test pad", pins={"1": [v[1] for v in p["pins"].values()][0]},
            awg_rec={}, max_current_a=None, same_count_as=None, source="electronics/head_acq/design/circuit.py", notes="layout_guidance.md section 4: cable shields terminate on the board SHLD_J1 / SHLD_J2 pads.")
    return out


def board_panel_tof():
    S = src()
    out = {}
    for p in S["pn"].PARTS:
        if p["ref"] in ("J1", "J2"):
            n = len([k for k in p["pins"] if k != "MP"])
            m, c = gh_mating(n)
            pins = {str(k): v[1] for k, v in p["pins"].items() if k != "MP"}
            out["PNL." + p["ref"]] = dict(
                id="PNL." + p["ref"], board="RR-PANEL", ref=p["ref"], location="RR-PANEL (70 x 24 mm) under the annunciator skin at (-80, 97, ~110) mm base_link; %s, top side (stage 2, P1)" % ("J1 at board (u, v) = (30, 20.6)" if p["ref"] == "J1" else "J2 at board (u, v) = (49.5, 20.6)"),
                function=p["description"] + " (stage 2, P1: fitted on the TOP side, mating face toward the v = 24 edge)", kind="board_header", mpn="%s %s" % (p["manufacturer"], p["mpn"]), mpn_status="verified (not flagged in source)",
                mating=m, mating_status="verified (not flagged in source)", contacts=c, seal=FAM["GH"]["seal"], temp="-25..+85 C [U] (panel circuit.py note)",
                temp_status="UNVERIFIED", keying=FAM["GH"]["keying"], geom="single", family="JST GH side entry (top side, stage 2)", pins=pins,
                awg_rec={}, max_current_a=0.15 if p["ref"] == "J1" else 0.1, same_count_as=None, source="electronics/panel/design/circuit.py", notes=p["notes"])
    tof = S["tof"]
    j1 = [p for p in tof["parts"] if p["ref"] == "J1"][0]
    pins = {pp["pin"]: pp["net"] for pp in j1["pins"] if pp["pin"] != "MP"}
    names = _tof_names()
    for i in range(11):
        out["TOF%d.J1" % i] = dict(
            id="TOF%d.J1" % i, board="RR-TOF-A", ref="J1", location="RR-TOF carrier #%d (%s), 18 x 14 mm, behind a 1 mm window" % (i, names[i][0]), function="ToF carrier %s harness connector" % names[i][0],
            kind="board_header", mpn="JST SM06B-GHS-TB(LF)(SN)", mpn_status="verified (not flagged in source)", mating="GHR-06V-S", mating_status="verified (not flagged in source)",
            contacts="SSHL-002T-P0.2 (AWG 26-30)", seal=FAM["GH"]["seal"], temp=FAM["GH"]["temp"], temp_status="UNVERIFIED",
            keying=FAM["GH"]["keying"], geom="single", family="JST GH side entry (bottom side of the carrier)", pins=pins, awg_rec={}, max_current_a=0.04,
            same_count_as=None, source="electronics/tof_carrier/board.py + out/pinmap.json", notes="Carrier pin order: 1 +3V3, 2 GND, 3 SDA, 4 SCL, 5 XSHUT, 6 GPIO1. MP (shield tab) = GND, not a wire.")
    return out


def _tof_names():
    S = src()
    m = S["fw_chs"]["i2c"]["I2C_TOF"]["mux_channels"]
    out = {int(k): (v["id"], v["mux"], v["ch"]) for k, v in m.items()}
    import hdata_cables as hk      # IB-34 (lead decision): harness names of ids 4..7 (firmware pinmap still carries the old LOOK_LO/LI/RI/RO names)
    for i, (nm, zone, keys) in hk.LOOK_MAP.items():
        out[i] = (nm, out[i][1], out[i][2])
    return out


# ---------------------------------------------------------------- non-board connectors / device ends
def _c(id, location, function, kind, mpn, mpn_status, mating, mating_status, contacts, seal, temp, tstat, keying, geom, pins, notes="", source="", family=""):
    return dict(id=id, board=None, ref=id, location=location, function=function, kind=kind, mpn=mpn, mpn_status=mpn_status, mating=mating, mating_status=mating_status,
                contacts=contacts, seal=seal, temp=temp, temp_status=tstat, keying=keying, geom=geom, family=family, pins=pins, awg_rec={}, max_current_a=None,
                same_count_as=None, source=source, notes=notes)


def contract_pins(which):
    S = src()
    return {str(k): v["net"] for k, v in S["contract"]["connectors"][which]["pins"].items()}


def others():
    S = src()
    J1 = contract_pins("J1")
    J2 = contract_pins("J2")
    o = {}
    M16 = "binder M16 IP67 8-pole (series 423/723, '09 0174 xx 08' family), shieldable"
    M12 = "binder M12-A 8-pole (series 763 family), shieldable"
    # --- J1 / J2 receptacles and plugs
    J1 = dict(J1, SH="CHASSIS")
    J2 = dict(J2, SH="CHASSIS")
    J1H = dict(J1, SH="SHLD_J1")
    J2H = dict(J2, SH="SHLD_J2")
    o["J1R"] = _c("J1R", "Left front shoulder skin, (72.0, 32.0, 116.9), axis (0.625, 0.290, 0.725); 45 mm free radial grasp zone", "J1 HEAD POWER / INTERLOCK chassis receptacle (female contacts, touch-safe source)",
                  "panel_receptacle", "TBD - not in sources (family only: %s female panel receptacle)" % M16, "UNVERIFIED",
                  "J1P: M16 8-pole cable plug, male contacts, on the head pigtail (MPN TBD - not in sources)", "TBD", "solder cups or crimp per binder variant: TBD (power_budget.md notes 8-pole solder cups may be limited to 0.5 mm2)",
                  "IP67 mated (contract); IP rating unmated not in sources", "-40..+85 C (parts.yaml j1_receptacle.temp_c, UNVERIFIED)", "UNVERIFIED",
                  "IEC 61076-2-106 M16 8-pole with screw locking; M16 cannot mate J2 (M12) or the L-coded charge inlet", "circ_m16", J1,
                  "Shell: shield bonded to chassis at the receptacle (360 degrees) per contract. Pin-8 NC_RESERVED.", "interface/system/contract.yaml connectors.J1; mechanical/common/purchased/parts.yaml j1_receptacle", "M16 circular 8-pole")
    o["J1P"] = _c("J1P", "Head pigtail end, free length 150..200 mm from the head rear wall port (71.7, 87.5, 39)", "J1 plug on the captive head pigtail (male contacts)",
                  "cable_plug", "TBD - not in sources (family only: %s male cable plug)" % M16, "UNVERIFIED", "J1R", "UNVERIFIED",
                  "TBD (solder cups or crimp per binder variant)", "IP67 mated (contract)", "-40..+85 C (parts.yaml j1_receptacle.temp_c, UNVERIFIED)", "UNVERIFIED",
                  "IEC 61076-2-106 M16 8-pole screw locking", "circ_m16", J1H, "Plug link inside the plug: none for J1. Plug body 62 mm, cable OD 7.5 mm, bend radius 40 mm (parts.yaml j1_receptacle envelope).", "contract; parts.yaml", "M16 circular 8-pole")
    o["J2R"] = _c("J2R", "Right front shoulder skin, (72.0, -32.0, 116.9), axis (0.625, -0.290, 0.725); 45 mm free radial grasp zone", "J2 HEAD DATA chassis receptacle (female contacts)",
                  "panel_receptacle", "TBD - not in sources (family only: %s female panel receptacle)" % M12, "UNVERIFIED", "J2P: M12 A-coded 8-pole cable plug (MPN TBD)", "TBD",
                  "solder cups or crimp per binder variant: TBD", "IP67 mated (contract)", "-40..+85 C (parts.yaml j2_receptacle.temp_c, UNVERIFIED)", "UNVERIFIED",
                  "M12 A-coded (IEC 61076-2-101); cannot mate the L-coded charge inlet or the M16 J1", "circ_m12", J2, "Shield bonded to chassis at the receptacle.", "contract; parts.yaml j2_receptacle", "M12 A-coded 8-pole")
    o["J2P"] = _c("J2P", "Head pigtail end, free length 150..200 mm from the head rear wall port (71.7, -87.5, 39)", "J2 plug on the captive head pigtail (male contacts); pin 7 linked to pin 4 inside the plug",
                  "cable_plug", "TBD - not in sources (family only: %s male cable plug)" % M12, "UNVERIFIED", "J2R", "UNVERIFIED", "TBD", "IP67 mated (contract)",
                  "-40..+85 C (parts.yaml j2_receptacle.temp_c, UNVERIFIED)", "UNVERIFIED", "M12 A-coded", "circ_m12", J2H,
                  "Contract: J2_PRES (pin 7) is linked to pin 4 inside the head plug. The head board footprint R2502 (0 ohm) is DNP and must stay DNP when the plug link is fitted.", "contract; head circuit.py R2502", "M12 A-coded 8-pole")
    # --- LAB extension (NOT part of the robot BOM)
    ext = " LAB ONLY: not part of the robot BOM."
    o["J1X-P"] = _c("J1X-P", "LAB extension, robot end (plugs into J1R)", "J1X plug (male), chassis end; backshell carries the 1.50 kohm 1 % LAB resistor pin 7 to pin 2", "cable_plug",
                    "TBD - not in sources (family only: %s male cable plug with backshell for the resistor)" % M16, "UNVERIFIED", "J1R", "UNVERIFIED", "TBD", "IP67 mated (contract)",
                    "-40..+85 C (UNVERIFIED, as J1)", "UNVERIFIED", "M16 8-pole screw locking", "circ_m16", J1, ext, "contract lab_extension; head_icd.md section 7", "M16 circular 8-pole")
    o["J1X-S"] = _c("J1X-S", "LAB extension, head end (the head plug J1P mates here)", "J1X socket (female), head end", "cable_socket",
                    "TBD - not in sources (family only: %s female cable socket)" % M16, "UNVERIFIED", "J1P", "UNVERIFIED", "TBD", "IP67 mated (contract)",
                    "-40..+85 C (UNVERIFIED, as J1)", "UNVERIFIED", "M16 8-pole screw locking", "circ_m16", J1H, ext, "contract lab_extension", "M16 circular 8-pole")
    o["J2X-P"] = _c("J2X-P", "LAB extension, robot end (plugs into J2R)", "J2X plug (male), chassis end", "cable_plug",
                    "TBD - not in sources (family only: %s male cable plug)" % M12, "UNVERIFIED", "J2R", "UNVERIFIED", "TBD", "IP67 mated (contract)",
                    "-40..+85 C (UNVERIFIED, as J2)", "UNVERIFIED", "M12 A-coded", "circ_m12", J2, ext, "contract lab_extension", "M12 A-coded 8-pole")
    o["J2X-S"] = _c("J2X-S", "LAB extension, head end (the head plug J2P mates here)", "J2X socket (female), head end", "cable_socket",
                    "TBD - not in sources (family only: %s female cable socket)" % M12, "UNVERIFIED", "J2P", "UNVERIFIED", "TBD", "IP67 mated (contract)",
                    "-40..+85 C (UNVERIFIED, as J2)", "UNVERIFIED", "M12 A-coded", "circ_m12", J2H, ext, "contract lab_extension", "M12 A-coded 8-pole")
    # --- pack side
    cp = {"P": "PACK_P", "N": "GND", "A1": "PACK_NTC", "A2": "PACK_PRES_N"}
    o["CPL-B"] = _c("CPL-B", "Battery bay front bulkhead, centre line, mated envelope x -73.5..-16.0, |y| <= 19, z 44..62", "Pack coupler, fixed (bay) half: pack +, pack -, aux 1 PACK_NTC, aux 2 PACK_PRES_N",
                    "inline", "Anderson Power SBS50 (candidate; exact housing/contact kit TBD)", "UNVERIFIED", "CPL-C (cassette half)", "UNVERIFIED", "TBD - not in sources (power contacts, auxiliary contact kit)",
                    "finger-proof (modules sheet)", "-20..+105 C (parts.yaml battery_coupler.temp_c, UNVERIFIED); modules sheet: -40 C rating not confirmed. NO MARGIN at -20 C operation: open item",
                    "UNVERIFIED", "keyed, blind-mate; reverse insertion blocked by an off-centre key rib on the cassette floor (mechanical_interfaces.md); key code TBD", "none", cp,
                    "Pin names P/N/A1/A2 are logical (SBS50 contact numbering not in sources).", "electronics/modules/battery_pack_and_coupler.md; parts.yaml battery_coupler", "Anderson SBS50-class")
    o["CPL-C"] = _c("CPL-C", "Battery cassette, floating +-1 mm", "Pack coupler, cassette half", "inline", "Anderson Power SBS50 (candidate; exact housing/contact kit TBD)", "UNVERIFIED",
                    "CPL-B", "UNVERIFIED", "TBD - not in sources", "finger-proof (modules sheet)", "as CPL-B", "UNVERIFIED", "as CPL-B", "none", cp, "", "modules sheet; parts.yaml", "Anderson SBS50-class")
    o["FUSE-MAIN"] = _c("FUSE-MAIN", "Bay harness, within 150 mm of the bulkhead coupler half (power_budget.md section 5)", "Main fuse, positive pole, 20 A blade, 32 V, >= 1 kA interrupting", "fuse",
                        "TBD - not in sources (20 A blade fuse, 32 V, >= 1 kA; holder TBD)", "TBD", "n/a", "TBD", "TBD", "TBD", "TBD", "TBD", "TBD", "none", {"1": "PACK_P", "2": "VBAT_RAW"},
                        "Series element: net pair PACK_P (coupler side) / VBAT_RAW (board side).", "power_budget.md section 5; battery_pack_and_coupler.md", "automotive blade")
    o["FUSE-CASS"] = _c("FUSE-CASS", "Inside the cassette at the positive terminal (recommended, modules sheet)", "Second 20 A blade fuse inside the cassette (RECOMMENDED, not adopted)", "fuse",
                        "TBD - not in sources (identical to the main fuse)", "TBD", "n/a", "TBD", "TBD", "TBD", "TBD", "TBD", "TBD", "none", {"1": "PACK_P_CELL", "2": "PACK_P"},
                        "Series element: net pair PACK_P_CELL (pack side) / PACK_P (coupler side).", "battery_pack_and_coupler.md", "automotive blade")
    o["PACK"] = _c("PACK", "Inside the removable cassette", "Power-Sonic PSL-SC-12120 terminals F2 (6.35 mm faston), wired once inside the cassette with insulated fastons and AWG 12 leads", "module",
                   "Power-Sonic PSL-SC-12120 (F2 terminals)", "verified (parts.yaml battery_12ah: all dimensions/mass/temp/max_current VERIFIED)", "insulated 6.35 mm faston receptacles (TBD part)", "TBD",
                   "TBD", "none", "discharge -20..+60 C, charge 0..+45 C (parts.yaml, VERIFIED)", "verified", "F2 faston: + / - terminals differ in width only per pack drawing (not in sources): mark polarity at assembly", "terminals",
                   {"+": "PACK_P_CELL", "-": "GND"}, "Cassette NTC (10 kohm, B ~3435-3490, bonded to case) and presence link also live in the cassette.", "battery_pack_and_coupler.md; parts.yaml battery_12ah", "")
    o["NTC-CASS"] = _c("NTC-CASS", "Bonded to the pack case inside the cassette", "Cassette NTC 10 kohm (B ~3435-3490), returned to pack negative", "device", TBD + " (10 kohm NTC, B 3435-3490)", "TBD",
                       "n/a", "TBD", "TBD", "none", TBD, "TBD", "n/a", "leads", {"a": "PACK_NTC", "b": "GND"}, "", "battery_pack_and_coupler.md", "")
    # --- charge inlet
    o["INLET"] = _c("INLET", "Right rear quarter skin (-201.1, -124.8, 88.0), axis (-0.379, -0.925, 0), under a hinged cover; 25 mm depth behind the panel", "Charge inlet M12 L-coded 4+FE male panel receptacle: 1 +24 V, 2 LINK_A, 3 0 V, 4 LINK_B, FE chassis",
                    "panel_receptacle", TBD + " (M12 L-coded, 4 + FE, male panel receptacle; 'part number with the harness lead')", "UNVERIFIED", "CHGPLUG (M12 L-coded female, pins 2-4 linked inside)", "UNVERIFIED",
                    "TBD", "IP rating not in sources", "-40..+85 C (parts.yaml charge_inlet.temp_c, UNVERIFIED)", "UNVERIFIED",
                    "L-coded (IEC 61076-2-111): cannot mate the A-coded J2 or the M16 J1", "circ_m12l", {"1": "CHG_IN", "2": "PLUG_LINK", "3": "GND", "4": "GND", "FE": "CHASSIS"},
                    "Pin assignment is a PROPOSAL in the modules sheet [M][U]. Pin 3 = 0 V to J_PWR pin 7, pin 4 (LINK_B, 0 V at the board) to J_PWR pin 8. FE = chassis via the receptacle flange, no wire.",
                    "electronics/modules/external_24v_supply.md; parts.yaml charge_inlet", "M12 L-coded 4+FE")
    o["CHGPLUG"] = _c("CHGPLUG", "On the lead of the external 24 V supply (Mean Well GST90A24-P1M candidate, plug replaced)", "Charge plug M12 L-coded female, pins 2 and 4 linked inside the plug", "cable_plug",
                      TBD + " (M12 L-coded female)", "UNVERIFIED", "INLET", "UNVERIFIED", "TBD", "TBD", "TBD", "UNVERIFIED", "L-coded", "circ_m12l", {"1": "CHG_IN", "2": "PLUG_LINK", "3": "GND", "4": "GND", "FE": "CHASSIS"},
                      "Supply side: not part of the robot harness; listed because it defines the plug link. Link 2-4 inside the plug.", "external_24v_supply.md", "M12 L-coded 4+FE")
    # --- motors
    for s, n in (("L", "Left"), ("R", "Right")):
        o["MOTOR-" + s] = _c("MOTOR-" + s, "%s gearmotor rear (encoder end); gearbox face at y = %s115" % (n, "+" if s == "L" else "-"), "%s gearmotor Pololu #2828, captive six-wire pigtail re-terminated into a Micro-Fit 3.0 2x3 plug housing" % n,
                             "module", "Pololu #2828 (captive pigtail, no connector)", "verified (parts.yaml motor: ratings VERIFIED)", "Molex 43025-0600 plug housing (to CHS.J_MOT_%s)" % s, "UNVERIFIED",
                             "43030-0007 (AWG 20-24) / 43030-0010 (AWG 26-30)", "none stated", "none published (parts.yaml motor.temp_c null; UNVERIFIED)", "UNVERIFIED", "n/a (captive wires)", "leads",
                             {"1": "MOTC_%s_A" % s, "2": "MOTC_%s_B" % s, "3": "ENC_%s_5V" % s, "4": "GND", "5": "ENCC_%s_A" % s, "6": "ENCC_%s_B" % s},
                             "Lead colours per Pololu product page [D, confirm on the part]: 1 red motor A, 2 black motor B, 3 blue encoder 5 V, 4 green encoder GND, 5 yellow encoder A, 6 white encoder B. Lead length and gauge not published (power_budget assumes AWG 22, 0.25 m): TBD.",
                             "electronics/modules/gearmotor_pololu_2828.md", "")
    # --- LiDAR, CM5
    o["LIDAR-PWR"] = _c("LIDAR-PWR", "LiDAR base on the battery hump, pad (-150, 0), z 150", "LiDAR supply input (Richbeam LakiBeam 1L, 9-36 V)", "module", "Richbeam LakiBeam 1L", "verified (temp/mass VERIFIED in parts.yaml; connector_exit UNVERIFIED)",
                        TBD + " (LiDAR power connector/pigtail not in sources)", "TBD", TBD, "IP65 (parts.yaml lidar.desc)", "-25..+60 C (parts.yaml, VERIFIED)", "verified", TBD, "list", {"1": "V12_LIDAR", "2": "GND"},
                        "Connector exit UNVERIFIED (parts.yaml).", "electronics/modules/lidar.md; parts.yaml lidar", "")
    o["LIDAR-ETH"] = _c("LIDAR-ETH", "LiDAR base", "LiDAR Ethernet pigtail (100BASE-TX), purchased", "module", "Richbeam LakiBeam 1L pigtail", "UNVERIFIED", "RJ45 on the CM5 carrier", "verified (RJ45 is standard)",
                        TBD, "IP65 unit; pigtail connector TBD", "-25..+60 C unit", "verified", TBD, "list", {"TXP": "ETH_TXP", "TXN": "ETH_TXN", "RXP": "ETH_RXP", "RXN": "ETH_RXN"},
                        "Pigtail wire colours and connector are not in the sources; pins named by 100BASE-TX function.", "lidar.md: 'Scanner RJ45/M12 pigtail directly to the carrier RJ45'", "")
    o["CM5-HDR"] = _c("CM5-HDR", "Waveshare CM5-IO-BASE-A, left rear bay (x -154..-69, y 59..115, pcb z 55)", "CM5 carrier 40-pin header: 5 V pins 2 and 4, GND pins 6 and 9 (feed point proposal)", "module",
                      "Waveshare CM5-IO-BASE-A 40-pin header", "UNVERIFIED (modules sheet: whether the carrier back-feeds/protects the header input is [U])", TBD + " (socket/crimp for 2 x AWG 20 per pole)", "TBD", TBD, "none", "carrier temperature rating not published (UNVERIFIED)", "UNVERIFIED",
                      "2x20 header, pin 1 square pad", "list", {"2": "V5_CM5", "4": "V5_CM5", "6": "GND", "9": "GND"},
                      "Alternative in the modules sheet: USB-C power-only pigtail. Check on the bench before the harness is drawn.", "cm5_and_carrier.md", "")
    for k, nm, pins in (("CM5-USB1", "USB-A 1: chassis link (MCU CDC)", {"1": "NC", "2": "MCUC_USB_DM", "3": "MCUC_USB_DP", "4": "GND", "SH": "USB_SHLD"}),
                        ("CM5-USB2", "USB-A 2: head link (FT230X)", {"1": "HUSB_VBUS", "2": "HUSBC_DM", "3": "HUSBC_DP", "4": "GND", "SH": "USB_SHLD"})):
        o[k] = _c(k, "Waveshare CM5-IO-BASE-A", nm, "module", "Waveshare CM5-IO-BASE-A USB 3.2 Gen1 Type-A port", "verified (parts.yaml cm5_carrier interfaces VERIFIED)", "USB-A plug (cable end, TBD part)", "TBD",
                  TBD, "none", "carrier temperature rating not published (UNVERIFIED)", "UNVERIFIED", "USB-A: polarised rectangular", "usba", pins,
                  "Standard USB-A pin order 1 VBUS, 2 D-, 3 D+, 4 GND (USB spec). USB-A plug pin 1 left open on the MCU link: the board pin is NC." if k == "CM5-USB1" else "VBUS from the carrier powers the bridge.", "cm5_and_carrier.md", "")
    o["CM5-RJ45"] = _c("CM5-RJ45", "Waveshare CM5-IO-BASE-A", "RJ45 Gigabit Ethernet, used by the LiDAR", "module", "Waveshare CM5-IO-BASE-A RJ45", "verified (parts.yaml)", "RJ45 plug", "verified (standard)", TBD, "none", "UNVERIFIED", "UNVERIFIED",
                       "RJ45 latch", "list", {"1": "ETH_TXP", "2": "ETH_TXN", "3": "ETH_RXP", "6": "ETH_RXN"}, "100BASE-TX uses pins 1,2,3,6 (standard).", "cm5_and_carrier.md", "")
    # --- operator devices (all coded as logical terminals; XB5 contact-block terminal numbers are not in the sources)
    xb = "Harmony XB5 contact block: terminal type/numbers TBD - not in sources"
    o["ESTOP-DEV"] = _c("ESTOP-DEV", "Right deck (-120.0, -98.0, 130.9), axis (-0.017, -0.341, 0.940); rear body 50 mm deep", "E-stop, 2 NC positive-opening: pole A (chain high side), pole B (coil return)", "device",
                        "Schneider Harmony XB5AS8444", "verified (parts.yaml: contacts_2nc VERIFIED; temp PARTIAL)", "n/a", "TBD", xb, "IP rating not in sources", "-40..+70 C (parts.yaml, PARTIAL)", "UNVERIFIED",
                        "22 mm panel, anti-rotation notch", "list", {"NC1-a": "CH_N1", "NC1-b": "CH_N2", "NC2-a": "COIL_RTN", "NC2-b": "GND"}, "Pole A = NC 1, pole B = NC 2. Positive opening applies to the E-stop only.", "estop_and_operator_switches.md; parts.yaml estop", "")
    o["MODE-DEV"] = _c("MODE-DEV", "Left deck (-135.0, 98.0, 130.3), axis (-0.079, 0.410, 0.909)", "Selector OFF/SERVICE/RUN: EN contact (NC block on the OFF side, closed in SERVICE and RUN) and RUN contact (NO block, closed in RUN only)", "device",
                       "Schneider Harmony XB5AD33 candidate (catalogue assembly has 2 NO: one block must be exchanged to ZBE-102 NC) + ZBE-101 NO block", "UNVERIFIED", "n/a", "TBD", xb, "IP rating not in sources", "-40..+70 C (parts.yaml, UNVERIFIED)", "UNVERIFIED",
                       "22 mm panel", "list", {"EN-a": "EN_SRC", "EN-b": "EN_SYS", "RUN-a": "CH_N0", "RUN-b": "CH_N1"}, "Cam behaviour to be confirmed on the part.", "estop_and_operator_switches.md", "")
    o["HANDS-DEV"] = _c("HANDS-DEV", "Right deck (-172.0, -97.0, 125.2), axis (-0.190, -0.415, 0.890)", "HANDS-ON maintained illuminated pushbutton: 1 NC chain element + 12 V lamp from the real chain state", "device",
                        "Schneider Harmony XB5 illuminated push-push, 1 NC, 12 V LED block (exact reference TBD: ZB5AH... + ZBE-102 + light block)", "UNVERIFIED", "n/a", "TBD", xb, "IP rating not in sources", "-40..+70 C (UNVERIFIED)", "UNVERIFIED",
                        "22 mm panel", "list", {"NC-a": "CH_N2", "NC-b": "CH_N3", "LAMP+": "HANDS_LAMP_P", "LAMP-": "HANDS_LAMP_K"}, "Lamp <= 20 mA.", "estop_and_operator_switches.md", "")
    o["REARM-DEV"] = _c("REARM-DEV", "Left deck (-172.0, 97.0, 125.2), axis (-0.190, 0.415, 0.890)", "REARM/Start guarded flush momentary, 2 NO (NO 1 = capacitor-coupled set path, NO 2 = REARM_BTN to the MCU), 12 V LED block", "device",
                         "Schneider Harmony XB5 guarded flush momentary 2 NO + 12 V LED block (reference TBD)", "UNVERIFIED", "n/a", "TBD", xb, "IP rating not in sources", "-40..+70 C (UNVERIFIED)", "UNVERIFIED",
                         "22 mm panel", "list", {"SET-a": "SET_CAP", "SET-b": "K1_SET", "AUX-a": "BTN_3V3", "AUX-b": "REARM_BTN_RAW", "LAMP+": "V12_AUX", "LAMP-": "LAMP_REARM_K"},
                         "NO 1 closes the latch set path. NO 2 is electrically independent.", "estop_and_operator_switches.md", "")
    o["PAUSE-DEV"] = _c("PAUSE-DEV", "Right deck (-84.0, -112.0, 122.0), axis (0.049, -0.521, 0.852)", "PAUSE/Stop projecting momentary, 1 NO, 12 V LED block", "device",
                        "Schneider Harmony XB5 projecting momentary 1 NO + 12 V LED block (reference TBD)", "UNVERIFIED", "n/a", "TBD", xb, "IP rating not in sources", "-40..+70 C (UNVERIFIED)", "UNVERIFIED",
                        "22 mm panel", "list", {"NO-a": "PAUSE_3V3", "NO-b": "PAUSE_BTN_RAW", "LAMP+": "V12_AUX", "LAMP-": "LAMP_PAUSE_K"}, "Contact supply is PAUSE_3V3 (1 kohm from 3V3 on the chassis board, S2-01f).", "estop_and_operator_switches.md; STAGE2_CHANGE_REQUESTS.md S2-01", "")
    d2 = "Omron D2HW-C201M sealed SPDT, pin plunger, lead wires, M3 screw mount"
    for k, loc, fn, pins in (
            ("BUMP-L-DEV", "Left rear quarter (-236.6, 103.0, 66.0)", "Body bumper switch left, wired NC", {"COM": "CH_N7", "NC": "CH_N8A", "NO": "UNUSED"}),
            ("BUMP-R-DEV", "Right rear quarter (-236.6, -103.0, 66.0)", "Body bumper switch right, wired NC", {"COM": "CH_N8A", "NC": "CH_N8", "NO": "UNUSED"}),
            ("DOCK-DEV", "Behind the left receiver channel (-3.0, 87.5, 23.0), pressed by the left shoe tip", "HEAD_DOCK switch, wired NC", {"COM": "CH_N4", "NC": "CH_N5", "NO": "UNUSED"}),
            ("COVER-DEV", "Charge inlet cover, (-201.1, -124.8, 88.0), hinge at the top", "Inlet cover switch, wired NC (closed with the cover shut)", {"COM": "CH_N3", "NC": "CH_N4A", "NO": "UNUSED"})):
        o[k] = _c(k, loc, fn, "device", "Omron D2HW-C201M", "verified (parts.yaml bumper_switch: temp, ip67 VERIFIED)", "n/a (lead wires)", "TBD",
                  "lead wires; gauge, length and colours not in sources: TBD", "IP67 (parts.yaml, VERIFIED)", "-40..+85 C (parts.yaml VERIFIED; modules sheet still tags it [U])", "verified", "n/a (3 lead wires: COM, NO, NC)", "list",
                  pins, "Wire COM and NC only. The NO lead is cut back and insulated, never connected (a NO throw would not be a chain contact).", "parts.yaml bumper_switch; estop_and_operator_switches.md", d2)
    o["SOUNDER-EXT"] = _c("SOUNDER-EXT", "Panel near the annunciator (position not in sources)", "Optional external 22 mm panel sounder, 12 V self-driven, <= 100 mA, >= 85 dB(A) at 30 cm, -25 C", "device",
                          TBD + " (candidate class: Schneider Harmony XB5KSB/XB5KS2 buzzer; no part verified)", "UNVERIFIED", "n/a", "TBD", TBD, "TBD", TBD, "TBD", "22 mm panel", "list",
                          {"+": "V12_AUX", "-": "BUZ_N"}, "Recommended: the on-board piezo is about 60 dB at 1 m (panel circuit.py).", "panel circuit.py J2; estop_and_operator_switches.md", "")
    # --- heaters and sensors
    o["HTR-CHS"] = _c("HTR-CHS", "Bay floor, 90 x 70 mm pad at x -164..-74", "Chassis/battery-bay heater film, 12 V, 20 W, 7.2 ohm", "device", "Polyimide film heater 90 x 70 mm, 12 V, 20 W class with PSA (catalogue item TBD after thermal test)", "TBD",
                      "n/a", "TBD", TBD, "TBD", "-40..+120 C (parts.yaml chassis_heater, design value)", "UNVERIFIED", "n/a", "leads", {"1": "CHS_HTR_P", "2": "CHS_HTR_MID"}, "", "parts.yaml chassis_heater; CCR-E08(e)", "")
    o["CUT-CHS"] = _c("CUT-CHS", "On the bay heater plate (series, low side)", "Independent bimetal thermal cut-out in series with the bay heater", "device", TBD + " (bimetal cut-out; rating >= 3.04 A at 14.4 V DC needed)", "TBD",
                      "n/a", "TBD", TBD, "TBD", TBD, "TBD", "n/a", "leads", {"1": "CHS_HTR_MID", "2": "GND"}, "Cut-out contact resistance 30 mohm assumed in power_budget.md [A].", "CCR-E08(e); power_budget.md", "")
    o["NTC-BAY"] = _c("NTC-BAY", "Battery bay beside the heater", "Bay air NTC 10 kohm B3435", "device", TBD + " (10 kohm NTC, B3435)", "TBD", "n/a", "TBD", TBD, "TBD", TBD, "TBD", "n/a", "leads", {"a": "NTC_BAY", "b": "GND"}, "", "circuit.py J_NTC; modules", "")
    o["NTC-PACKSURF"] = _c("NTC-PACKSURF", "Pack surface (bay wall against the cassette)", "Pack-surface NTC 10 kohm B3435 (heater plausibility, battery.temp_c[1])", "device", TBD + " (10 kohm NTC, B3435)", "TBD", "n/a", "TBD", TBD, "TBD", TBD, "TBD", "n/a", "leads",
                           {"a": "NTC_PACK", "b": "GND"}, "", "circuit.py J_NTC; firmware pinmap", "")
    o["CHS.W1"] = _c("CHS.W1", "RR-CHS-MAIN, near the clamp circuit (DNP)", "Two 2.5 mm DNP wire pads W1 (1 CLAMP_F, 2 CLAMP_R): NO cable, NO bolt-on resistor (the board carries its own 2 x 9.1 ohm clamp resistors, IB-26 / IB-36)", "board_pad", "2 x TestPoint_Pad_2.5x2.5mm (pcb feature, DNP)", "verified (not flagged)",
                     "none: not wired", "n/a", "-", "n/a", "n/a", "n/a", "n/a", "list", {"1": "CLAMP_F", "2": "CLAMP_R"}, "DNP in rev A; no harness wire (decision: no bolt-on clamp resistor; a 50 W part listed in parts.yaml is stale, IB-26).", "chassis circuit.py W1 and the on-board clamp R (9.1 ohm 2512 x 2)", "")
    # --- splices
    for k, net1, nm in (("SPL-P", "VBAT_RAW", "pack positive 1-to-2 crimp splice (AWG 14 trunk to 2 x AWG 16)"), ("SPL-N", "GND", "pack negative 1-to-2 crimp splice (AWG 14 trunk to 2 x AWG 16)"),
                        ("SPL-HCUT", "HTR_CUT", "head heater: element end / cut-out / J2601 pin 3 sense junction")):
        o[k] = _c(k, "In the loom", nm, "splice", TBD + " (sealed wire-to-wire splice)", "TBD", "n/a", "TBD", TBD, "TBD", TBD, "TBD", "n/a", "list", {"1": net1, "2": net1, "3": net1}, "Splice resistance not in power_budget.md: measure on the first harness.", "harness decision", "")
    # --- head devices
    o["RAIL-F"] = _c("RAIL-F", "Head front bumper rail (184.2, 0.0, 21.0)", "Head rail switch, front zone, NC in the interlock loop", "device", "Omron D2HW-C201M", "verified (parts.yaml)", "n/a", "TBD", "lead wires: TBD", "IP67 (VERIFIED)", "-40..+85 C (VERIFIED)", "verified", "n/a", "list",
                     {"COM": "HEAD_LOOP_OUT", "NC": "LOOP_A", "NO": "UNUSED"}, "NO lead must stay unconnected (CCR-HE-04).", "head circuit.py J2002; CCR-HE-04", d2)
    o["RAIL-L"] = _c("RAIL-L", "Head left rail (131.2, 168.5, 21.0)", "Head rail switch, left zone", "device", "Omron D2HW-C201M", "verified (parts.yaml)", "n/a", "TBD", "lead wires: TBD", "IP67 (VERIFIED)", "-40..+85 C (VERIFIED)", "verified", "n/a", "list",
                     {"COM": "LOOP_A", "NC": "LOOP_B", "NO": "UNUSED"}, "", "head circuit.py J2003", d2)
    o["RAIL-R"] = _c("RAIL-R", "Head right rail (131.2, -168.5, 21.0)", "Head rail switch, right zone", "device", "Omron D2HW-C201M", "verified (parts.yaml)", "n/a", "TBD", "lead wires: TBD", "IP67 (VERIFIED)", "-40..+85 C (VERIFIED)", "verified", "n/a", "list",
                     {"COM": "LOOP_B", "NC": "LOOP_C", "NO": "UNUSED"}, "", "head circuit.py J2004", d2)
    o["LID-SW"] = _c("LID-SW", "Head housing/lid (position not in sources)", "Light-leak lid interlock switch, closed = light-tight", "device", TBD, "TBD", "n/a", "TBD", TBD, TBD, TBD, "TBD", "n/a", "list", {"a": "LID_IN", "b": "GND"},
                     "Switch type and location are not in the sources. Bench bypass is the solder jumper JP2201 (close deliberately, record in the build sheet).", "head circuit.py J2201", "")
    o["HEAD-HEATER"] = _c("HEAD-HEATER", "Under the spreader plate (z 28.5..30.0), tail up the chimney at y = +87.5", "Head heater film 4.8 ohm element (12 V, 30 W peak), polyimide 0.3 mm, zoned per lane", "device", TBD + " (polyimide heater film, 4.8 ohm)", "TBD", "n/a", "TBD", TBD, TBD, TBD, "TBD", "n/a", "list",
                          {"1": "HTR_SW", "2": "HTR_CUT"}, "", "head circuit.py J2601 note; board_envelopes.yaml", "")
    o["HEAD-CUTOUT"] = _c("HEAD-CUTOUT", "On the heater assembly (low side)", "Independent bimetal cut-out, low side of the head heater", "device", TBD + " (bimetal cut-out)", "TBD", "n/a", "TBD", TBD, TBD, TBD, "TBD", "n/a", "list",
                          {"1": "HTR_CUT", "2": "HEAD_HTR_N"}, "Status reads 'tripped' when the heater feed is off, by design (CCR-HE-08).", "head circuit.py J2601; head_icd.md section 3", "")
    o["NTC-SPR"] = _c("NTC-SPR", "Spreader plate, rear chimney", "Spreader NTC (heater control)", "device", TBD + " (NTC, value not in sources)", "TBD", "n/a", "TBD", TBD, TBD, TBD, "TBD", "n/a", "list", {"a": "NTC_HTR", "b": "GND"}, "", "head circuit.py J2601", "")
    # SiPM carriers
    for ch in ("F0", "F1", "F2", "F3", "R0", "R1", "R2", "R3"):
        o["CARR-" + ch] = _c("CARR-" + ch, "SiPM carrier %s in the rear chimney (z 11..28.5, behind the spreader)" % ch, "SiPM carrier %s: anode coax (signal) and bias coax (centre = filtered HV)" % ch, "device",
                             TBD + " (carrier connectors: CCR-HE-06 asks the RFQ for U.FL/MHF-class 50 ohm micro-coax outputs)", "TBD", "n/a", "TBD", TBD, "none (inside head)", TBD, "TBD", TBD, "list",
                             {"A": "%s_A" % ch, "A-SH": "GND", "B": "%s_HVF" % ch, "B-SH": "GND"}, "Bias decoupling >= 10 nF on the carrier (CCR-HE-06).", "head CCR-HE-06; circuit_description.md", "")
    for k in range(4):
        o["CARR-AUX%d" % k] = _c("CARR-AUX%d" % k, "Lane %d SiPM carrier(s)" % k, "Lane %d auxiliary: SiPM NTC (10 kohm within 5 mm of the SiPM, CCR-HE-06), optional LED pulser, optional 3.3 V" % k, "device",
                                 TBD, "TBD", "n/a", "TBD", TBD, "none (inside head)", TBD, "TBD", TBD, "list",
                                 {"1": "NTC_SIPM%d" % k, "2": "GND", "3": "L%d_LED_A" % k, "4": "L%d_LED_K" % k, "5": "L%d_AUX3V3" % k, "6": "GND"}, "LED and 3.3 V pins optional (active carrier / pulser).", "head circuit.py J1001..J1301", "")
    return o


def build_all():
    allc = {}
    for part in (board_chassis(), board_head(), board_panel_tof(), others()):
        for k, v in part.items():
            assert k not in allc, k
            allc[k] = v
    return allc


if __name__ == "__main__":
    a = build_all()
    print(len(a))
