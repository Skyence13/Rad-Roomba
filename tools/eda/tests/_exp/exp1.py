import pcbnew, json, os, sys
pcbnew.KIID.SeedGenerator(1234)
p = os.path.abspath("exp.kicad_pcb")
json.dump({"board":{"design_settings":{"rules":{"min_clearance":0.15,"min_track_width":0.15}}},
 "meta":{"filename":"exp.kicad_pro","version":3},
 "net_settings":{"classes":[{"name":"Default","clearance":0.15,"track_width":0.2,"via_diameter":0.6,"via_drill":0.3,"priority":2147483647},
   {"name":"PWR","clearance":0.2,"track_width":0.4,"via_diameter":0.8,"via_drill":0.4,"priority":0}],
   "meta":{"version":4},"netclass_patterns":[{"netclass":"PWR","pattern":"+3V3"},{"netclass":"PWR","pattern":"GND"}]},
 "text_variables":{"REV":"A"}}, open("exp.kicad_pro","w"), indent=2)
b = pcbnew.NewBoard(p)
print("proj", b.GetProject() is not None)
b.SetCopperLayerCount(4)
ds = b.GetDesignSettings()
print("minclr", ds.m_MinClearance, "trk", ds.m_TrackMinWidth)
ns = ds.m_NetSettings
print([str(k) for k in ns.GetNetclasses().keys()] if hasattr(ns,'GetNetclasses') else dir(ns))
ds.SetBoardThickness(pcbnew.FromMM(1.6))
b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
b.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
tb = b.GetTitleBlock(); tb.SetTitle("Exp"); tb.SetRevision("A"); tb.SetDate("2026-11-25"); tb.SetCompany("RR"); tb.SetComment(0,"Doc 1")
# nets
for n in ["GND","+3V3","SIG"]:
    ni = pcbnew.NETINFO_ITEM(b, n); b.Add(ni)
fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/Resistor_SMD.pretty", "R_0402_1005Metric")
print(fp.GetFPID().GetUniStringLibId(), fp.GetFPIDAsString())
fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD","R_0402_1005Metric"))
fp.SetReference("R1"); fp.SetValue("10k")
b.Add(fp)
fp.SetPosition(pcbnew.VECTOR2I_MM(100,100)); fp.SetOrientationDegrees(90)
fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
for pad in fp.Pads():
    pad.SetNet(b.FindNet("GND" if pad.GetNumber()=="1" else "SIG"))
    print(pad.GetNumber(), pad.GetNetname(), pad.GetNetClassName() if hasattr(pad,'GetNetClassName') else '', pcbnew.ToMM(pad.GetPosition()))
print("layer", fp.GetLayerName(), fp.GetOrientationDegrees())
cy = fp.GetCourtyard(pcbnew.B_CrtYd); print("cy", cy.OutlineCount(), cy.BBox().GetWidth()/1e6, cy.BBox().GetHeight()/1e6)
fp.SetPath(pcbnew.KIID_PATH("/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222"))
fp.SetSheetname("/sensor/"); fp.SetSheetfile("sensor.kicad_sch")
print([n for n in dir(fp) if 'Field' in n or 'Attr' in n or 'DNP' in n or 'Model' in n])
print([n for n in dir(pcbnew) if n.startswith('FP_')])
pcbnew.SaveBoard(p, b)
print(open("exp.kicad_pro").read()[:300])
b2 = pcbnew.LoadBoard(p)
for f in b2.GetFootprints():
    print(f.GetReference(), f.GetFPIDAsString(), f.GetPath().AsString(), f.GetLayerName(), [(q.GetNumber(), q.GetNetname(), q.GetEffectiveNetClass().GetName() if hasattr(q,'GetEffectiveNetClass') else '') for q in f.Pads()])
print(b2.GetCopperLayerCount(), b2.GetLayerType(pcbnew.In1_Cu))
