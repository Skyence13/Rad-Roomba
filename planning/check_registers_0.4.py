#!/usr/bin/env python3
"""Consistency checks for the design 0.4 registers.  Run:  python3 planning/check_registers_0.4.py
Exit code 0 = all checks pass.  Read-only."""
import csv, os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PL = os.path.join(ROOT, 'planning')
fails = []
def rd(n):
    with open(os.path.join(PL, n), encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)
def check(cond, msg):
    if not cond: fails.append(msg)
def ids(rows, k): return [r[k] for r in rows]
def split(s): return [x for x in s.split('|') if x]

files = {'requirements': ('requirements.csv', 'requirements_0.4.csv', 'requirement_id', 'verification_ids'),
         'verification': ('verification.csv', 'verification_0.4.csv', 'test_id', 'requirement_ids'),
         'risks': ('risks.csv', 'risks_0.4.csv', 'risk_id', None),
         'decisions': ('decisions.csv', 'decisions_0.4.csv', 'decision_id', None)}
data = {}
for name, (b, n, key, link) in files.items():
    bf, br = rd(b); nf, nr = rd(n)
    data[name] = (bf, br, nf, nr)
    check(nf[:len(bf)] == bf, f'{n}: baseline columns not preserved in order')
    check(len(set(ids(nr, key))) == len(nr), f'{n}: duplicate IDs')
    check(ids(nr, key)[:len(br)] == ids(br, key), f'{n}: baseline rows not first / IDs changed')
    for x, y in zip(br, nr):
        for c in bf:
            if x[c] != y[c]:
                allowed = (c == link) or (name == 'decisions' and c in ('status_or_current_direction', 'resolution_and_reference'))
                check(allowed, f'{n}: baseline field {c} changed in {x[key]}')
                if c == link:
                    check(set(split(x[c])) <= set(split(y[c])), f'{n}: {x[key]} lost baseline links')
        for c in nf:
            if c not in bf and name != 'decisions': pass
    print(f'{n}: {len(nr)} rows ({len(nr)-len(br)} new), {len(nf)} columns')

R = {r['requirement_id']: r for r in data['requirements'][3]}
V = {r['test_id']: r for r in data['verification'][3]}
for q, r in R.items():
    for v in split(r['verification_ids']):
        check(v in V, f'{q} cites missing {v}')
        if v in V: check(q in split(V[v]['requirement_ids']), f'{q} lists {v} but {v} does not list {q}')
    check(r['verification_ids'] != '', f'{q} has no verification')
for v, r in V.items():
    for q in split(r['requirement_ids']):
        check(q in R, f'{v} cites missing {q}')
        if q in R: check(v in split(R[q]['verification_ids']), f'{v} lists {q} but {q} does not list {v}')
    check(r['evidence_class_now'] in ('calculated', 'simulated', 'tool-checked', 'physically-measured', 'pending'), f'{v}: bad evidence class')
    check(r['evidence_reference'] != '', f'{v}: empty evidence_reference')
for d in data['decisions'][3]:
    for q in split(d['requirement_ids']): check(q in R, f"{d['decision_id']} cites missing {q}")
for k in data['risks'][3]:
    for q in split(k['requirement_ids']): check(q in R, f"{k['risk_id']} cites missing {q}")
    for v in split(k['verification_ids']): check(v in V, f"{k['risk_id']} cites missing {v}")
rqnew = [q for q in R if int(q[3:]) > 51]
for q in rqnew: check(R[q]['design_response_0_4'] != '' and R[q]['source_decision_0_4'] != '', f'{q}: missing design response or source decision')
for q, r in R.items(): check(r['design_response_0_4'] != '', f'{q}: empty design_response_0_4')
# decisions DEC-021..041 present
D = {r['decision_id'] for r in data['decisions'][3]}
check(all(f'DEC-{i:03d}' in D for i in range(1, 42)), 'decision IDs DEC-001..041 not all present')
# BOM
bf, base_bom = rd('prototype_bom.csv')
_, bom = rd('bom_0.4/procurement_bom.csv')
bid = ids(bom, 'item_id')
check(len(set(bid)) == len(bid), 'procurement_bom: duplicate item_id')
for b in ids(base_bom, 'item_id'):
    check(any(x == b or re.fullmatch(b + '[a-z]', x) for x in bid), f'procurement_bom: baseline item {b} missing')
# cited paths exist
pat = re.compile(r'(?<![\w/.-])((?:analysis|docs|electronics|firmware|interface|mechanical|planning|ros2_ws|software|examples|reference|cad|tools)/[\w./*{}-]+\.(?:md|csv|yaml|yml|py|c|json|docx|pdf|h))')
missing = set()
for fn in ['decisions_0.4.csv', 'requirements_0.4.csv', 'verification_0.4.csv', 'risks_0.4.csv', 'bom_0.4/procurement_bom.csv', 'Detector_Head_RFQ_0.4.md', 'README_0.4.md']:
    text = open(os.path.join(PL, fn), encoding='utf-8-sig').read()
    for m in pat.findall(text):
        if '*' in m or '{' in m: continue
        p = os.path.join(ROOT, m)
        if not os.path.exists(p) and not os.path.exists(os.path.join(PL, m)):
            missing.add((fn, m))
for fn, m in sorted(missing): fails.append(f'{fn}: cited path not found: {m}')
print('cited paths checked; missing:', len(missing))
print('FAIL' if fails else 'ALL CHECKS PASS')
for f in fails: print('  -', f)
sys.exit(1 if fails else 0)
