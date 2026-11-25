import pcbnew, os
pcbnew.KIID.SeedGenerator(99)
p = os.path.abspath("exp.kicad_pcb")
b = pcbnew.LoadBoard(p)
print("before", [(pcbnew.ToMM(t.GetStart()), pcbnew.ToMM(t.GetEnd()), t.GetWidth(), t.IsLocked()) for t in b.GetTracks()])
print("ses", pcbnew.ImportSpecctraSES(b, os.path.abspath("exp.ses")))
print("after n=", len(b.GetTracks()))
for t in b.GetTracks():
    print(t.GetClass(), t.GetNetname(), pcbnew.ToMM(t.GetStart()), pcbnew.ToMM(t.GetEnd()), t.GetWidth(), t.IsLocked(), t.GetLayerName())
f = pcbnew.ZONE_FILLER(b); print("fill", f.Fill(b.Zones()))
b.BuildConnectivity()
c = b.GetConnectivity(); print("unconnected", c.GetUnconnectedCount(True))
z=b.Zones()[0]
print([n for n in dir(z) if 'DoNotAllow' in n or 'Island' in n or 'PadConnection' in n or 'Thermal' in n or 'MinThickness' in n or 'Clearance' in n or 'Priority' in n])
print([n for n in dir(pcbnew) if 'ZONE_CONNECTION' in n or 'ISLAND' in n or n.startswith('DIM_') or 'PCB_DIM' in n][:40])
pcbnew.SaveBoard(os.path.abspath("exp_routed.kicad_pcb"), b, True)
