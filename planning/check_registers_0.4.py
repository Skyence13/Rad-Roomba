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
check(all(f'DEC-{i:03d}' in D for i in range(1, max(int(d[4:]) for d in D) + 1)), 'decision IDs are not contiguous from DEC-001')
check(all(f'DEC-{i:03d}' in D for i in range(1, 46)), 'decision IDs DEC-001..045 (lead rows) not all present')
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
for fn in ['decisions_0.4.csv', 'requirements_0.4.csv', 'verification_0.4.csv', 'risks_0.4.csv', 'bom_0.4/procurement_bom.csv', 'bom_0.4/body_prototype_bom.csv', 'bom_0.4/body_production_bom.csv', 'bom_0.4/head_mech_prototype_bom.csv', 'bom_0.4/head_mech_production_bom.csv', 'Detector_Head_RFQ_0.4.md', 'README_0.4.md']:
    text = open(os.path.join(PL, fn), encoding='utf-8-sig').read()
    for m in pat.findall(text):
        if '*' in m or '{' in m: continue
        p = os.path.join(ROOT, m)
        if not os.path.exists(p) and not os.path.exists(os.path.join(PL, m)):
            missing.add((fn, m))
for fn, m in sorted(missing): fails.append(f'{fn}: cited path not found: {m}')
print('cited paths checked; missing:', len(missing))

# ---------------------------------------------------------------- checks added 2026-11-27 (revision of the registers after the reviews)
Dm = {d['decision_id']: d for d in data['decisions'][3]}
Kk = {k['risk_id']: k for k in data['risks'][3]}
# (a) every test is still Planned / pending: nothing may read as done
for v, r in V.items():
    check(r['test_status'] == 'Planned', f'{v}: test_status is {r["test_status"]!r}, not Planned')
    check(r['evidence_class_now'] == 'pending', f'{v}: evidence_class_now is {r["evidence_class_now"]!r}, not pending')
    check(r['evidence_record_or_uri'] == '' and r['disposition_and_reviewer'] == '', f'{v}: has an evidence record or disposition')
for q, r in R.items():
    check(r['verification_status'] == 'Open — evidence pending', f'{q}: verification_status changed')
# (b) free-text references resolve (VT, RQ, DEC, RSK IDs, IB numbers against the backlog)
bl = open(os.path.join(ROOT, 'docs/architecture/INTEGRATION_BACKLOG.md'), encoding='utf-8').read()
ib_ids = set(re.findall(r'^\| (IB-\d+) \|', bl, re.M))
check(len(ib_ids) >= 69, f'backlog lists only {len(ib_ids)} IB items')
idsets = {'VT': set(V), 'RQ': set(R), 'DEC': set(Dm), 'RSK': set(Kk), 'IB': ib_ids}
bad = set()
for fn in ['decisions_0.4.csv', 'requirements_0.4.csv', 'verification_0.4.csv', 'risks_0.4.csv', 'bom_0.4/procurement_bom.csv', 'bom_0.4/body_prototype_bom.csv', 'bom_0.4/body_production_bom.csv', 'bom_0.4/head_mech_prototype_bom.csv', 'bom_0.4/head_mech_production_bom.csv', 'Detector_Head_RFQ_0.4.md', 'README_0.4.md']:
    text = open(os.path.join(PL, fn), encoding='utf-8-sig').read()
    for kind in idsets:
        for m in set(re.findall(r'\b' + kind + r'-\d{2,3}\b', text)):
            if m not in idsets[kind]: bad.add((fn, m))
for fn, m in sorted(bad): fails.append(f'{fn}: cited ID not found: {m}')
print('free-text ID references checked; unresolved:', len(bad))
# (c) decision <-> requirement links are two-way for DEC-021 and later
for d, r in Dm.items():
    if int(d[4:]) < 21: continue
    for q in split(r['requirement_ids']):
        check(q in R and d in [x.strip() for x in R[q]['source_decision_0_4'].split(';')], f'{d} lists {q} but {q} does not name {d} in source_decision_0_4')
for q, r in R.items():
    for d in [x.strip() for x in r['source_decision_0_4'].split(';') if x.strip()]:
        check(d in Dm, f'{q} cites missing decision {d}')
        if d in Dm and int(d[4:]) >= 21: check(q in split(Dm[d]['requirement_ids']), f'{q} names {d} but {d} does not list {q}')
for d in ['DEC-042', 'DEC-043', 'DEC-044', 'DEC-045']:
    check(Dm[d]['requirement_ids'] != '' and len(split(Dm[d]['requirement_ids'])) >= 2, f'{d}: cross-references incomplete')
# (d) every new or revised row cites a source file that exists, in the column that holds sources
src_col = {'requirements': 'design_response_0_4', 'verification': 'evidence_reference', 'risks': 'source_file_0_4', 'decisions': 'resolution_and_reference'}
key_of = {'requirements': 'requirement_id', 'verification': 'test_id', 'risks': 'risk_id', 'decisions': 'decision_id'}
for name, col in src_col.items():
    for r in data[name][3]:
        ch = r.get('changed_in_0_4', '')
        if ch.startswith('new in 0.4') or ch.startswith('REVISED'):
            paths = [m for m in pat.findall(r[col]) if '*' not in m and '{' not in m]
            check(len(paths) >= 1, f'{r[key_of[name]]}: no source path in {col}')
            check('2026-11-27' in ch or 'new in 0.4' == ch.strip() or 'cross-references' in ch or ch.startswith('new in 0.4'), f'{r[key_of[name]]}: changed_in_0_4 does not say what changed')
for name in ('requirements', 'verification', 'risks', 'decisions'):
    for r in data[name][3]:
        if r['changed_in_0_4'].startswith('REVISED'):
            check(len(r['changed_in_0_4']) > 40, f'{r[key_of[name]]}: REVISED without a reason')
# (e) new tests: purpose (title), method, pass criterion or an explicit "criterion not yet defined", evidence summary
for v, r in V.items():
    if int(v[3:]) > 48:
        check(len(r['procedure']) > 80 and len(r['prerequisites']) > 20, f'{v}: procedure or prerequisites missing')
        e = r['expected_result_and_evidence']
        check(re.search(r'\d', e) is not None or 'criterion not yet defined' in e, f'{v}: no pass criterion and no statement that it is undefined')
        check(r['supporting_analysis'] != '', f'{v}: empty supporting_analysis')
        check(len(split(r['requirement_ids'])) >= 1, f'{v}: no requirement')
# (f) new requirements: role, basis, evidence class words where numbers are given
classwords = re.compile(r'calculated|simulated|tool-checked|UNVERIFIED|assumed|ASSUMED|datasheet|measured|not yet defined|estimate|design value|handbook|recalled|synthetic', re.I)
for q, r in R.items():
    if int(q[3:]) > 83:
        check(r['accountable_role'] != '' and r['basis'] != '', f'{q}: role or basis missing')
        txt = r['requirement_and_acceptance_criterion']
        check(re.search(r'\d', txt) is None or classwords.search(txt) is not None, f'{q}: numbers without an evidence class word')
        check(len(split(r['verification_ids'])) >= 1, f'{q}: no verification')
# (g) new risks: cause, consequence, control, retiring test, rating, links
for k, r in Kk.items():
    if int(k[4:]) > 40 or r['changed_in_0_4'].startswith('REVISED'):
        for c in ('trigger_or_cause', 'consequence', 'proposed_control', 'residual_risk_evidence_needed', 'current_mitigation_0_4', 'source_file_0_4'):
            check(r[c] != '', f'{k}: empty {c}')
        check(r['residual_rating_0_4'].split(' ')[0] in ('High', 'Medium', 'Low'), f'{k}: residual_rating_0_4 not High/Medium/Low')
        check(len(split(r['verification_ids'])) >= 1 and len(split(r['requirement_ids'])) >= 1, f'{k}: no linked test or requirement')
# (h) BOM files: normalised verification classes and quantities
vocab = {'VERIFIED', 'PARTIAL', 'UNVERIFIED', 'STANDARD_ISO_DIN', 'IN_HOUSE', 'NOT_SELECTED', 'NOT_STATED'}
for fn in ['body_prototype_bom.csv', 'body_production_bom.csv', 'head_mech_prototype_bom.csv', 'head_mech_production_bom.csv']:
    _, rows_ = rd('bom_0.4/' + fn)
    check(len(rows_) > 50, f'{fn}: too few lines')
    for r in rows_:
        check(r['verification_class'] in vocab, f'{fn}: bad verification_class {r["verification_class"]}')
        check(re.fullmatch(r'\d+(\.\d+)?', r['qty'].strip()) is not None, f'{fn}: non-numeric qty {r["qty"]!r} for {r["item"]}')
_, bom_ = rd('bom_0.4/procurement_bom.csv')
for r in bom_:
    check(r.get('verification_class', '') in vocab | {'CUSTOM', 'NOT_APPLICABLE'}, f'procurement_bom {r["item_id"]}: bad verification_class')
for b in ('RR-CHS-MAIN', 'RR-HEAD-ACQ', 'RR-PANEL'):
    _, rows_ = rd(f'bom_0.4/{b}_bom.csv')
    out = {'RR-CHS-MAIN': 'chassis_main', 'RR-HEAD-ACQ': 'head_acq', 'RR-PANEL': 'panel'}[b]
    with open(os.path.join(ROOT, 'electronics', out, 'out', b + '-bom.csv'), encoding='utf-8-sig', newline='') as f:
        gen = {x for r in csv.DictReader(f) for x in r['Refs'].split()}
    mine = {x for r in rows_ if r['purchasable'] != 'FALSE' for x in r['refs'].split()}
    miss = gen - mine
    check(not miss, f'{b}_bom.csv lacks {len(miss)} refs of the generated fabrication BOM, e.g. {sorted(miss)[:5]}')
# (i) RFQ carries today's numbers
rfq = open(os.path.join(PL, 'Detector_Head_RFQ_0.4.md'), encoding='utf-8').read()
for needle in ('18 p.e.', '+5', '2.0 V', 'ZnS', 'time over threshold', 'Cl-36', 'Am-241', '-25'):
    check(needle in rfq, f'RFQ lacks {needle!r}')
print('extended checks done')

print('FAIL' if fails else 'ALL CHECKS PASS')
for f in fails: print('  -', f)
sys.exit(1 if fails else 0)
