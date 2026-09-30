"""Small independent official DOM comparisons; selections only, no dispatch."""
import asyncio
import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.v2.observe.extractor import ClientExtractor, decode_units, connect_dedicated
from kiomet_ai.camera import world_to_page
from kiomet_ai.observe import TOWER_TYPES,TOWER_TYPE_ZH
from kiomet_ai.v2.observe import rules
from kiomet_ai.ui_parse import UNIT_ZH
from playwright.async_api import async_playwright

UNIT_NAMES = ("Shield", "Fighter", "Chopper", "Bomber", "Tank", "Soldier", "Shell", "Emp", "Nuke", "Ruler")


async def main(args):
    out = ROOT / "runtime/research/v2"
    rows = []
    errors=[]
    async with async_playwright() as pw:
        browser = await connect_dedicated(pw, ROOT)
        page = next(p for p in browser.contexts[0].pages if p.url == "https://kiomet.com/")
        ex = ClientExtractor(page)
        async def sample_ready():
            deadline=time.monotonic()+2
            while True:
                try:
                    return await ex.sample()
                except ValueError as e:
                    if str(e)!='current visibility cache pending' or time.monotonic()>=deadline:
                        raise
                    await asyncio.sleep(.01)
        try:
            await ex.attach()
            first_state, first = await sample_ready()
            view = await page.evaluate("""() => {const c=document.querySelector('canvas');
              const r=c.getBoundingClientRect();return {w:c.width,h:c.height,dpr:devicePixelRatio,
                left:r.left,top:r.top,cw:r.width,ch:r.height}}""")
            if view["dpr"] != 1 or view["left"] != 0 or view["top"] != 0:
                raise ValueError("only previously validated full-canvas DPR=1 projection allowed")
            cam = first["camera_candidate"]
            if not all(isinstance(v, (int, float)) for v in cam) or not 2 < cam[2] < 150:
                raise ValueError("camera candidate invalid")
            for round_index in range(args.rounds):
                if round_index:
                    await asyncio.sleep(.2)
                    _, first = await sample_ready()
                cam = first['camera_candidate']
                projected = []
                for tower in first["towers"]:
                    x, y = world_to_page(*tower["position"], *cam, view["w"], view["h"], 1)
                    if 80 < x < view["cw"] - 160 and 90 < y < view["ch"] - 110:
                        projected.append((tower, x, y))
                # Stratify limited diagnostic comparisons by owner; no PASS claim.
                chosen = []
                for relation in ("SELF", "NEUTRAL", "ENEMY", "ALLY", None):
                    candidates=[t for t in projected if t[0]["relation"] == relation]
                    candidates.sort(key=lambda t:t[0]['units7'][0]!=1)
                    if candidates:
                        start=round_index*5%len(candidates)
                        chosen += [candidates[(start+i)%len(candidates)] for i in range(min(5,len(candidates)))]
                for initial, _, _ in chosen:
                    before_state, before = await sample_ready()
                    if before_state.match_id.value!=first_state.match_id.value:
                        raise ValueError('observed match epoch changed; comparison cohort ended')
                    if before["document_time_origin"] != first["document_time_origin"] or before["player_id"] != first["player_id"]:
                        raise ValueError("document/player changed")
                    current = next((t for t in before["towers"] if t["id"] == initial["id"]), None)
                    if current is None:
                        continue
                    x, y = world_to_page(*current["position"], *before["camera_candidate"], view["w"], view["h"], 1)
                    clear = await page.evaluate("([x,y])=>document.elementFromPoint(x,y)?.tagName==='CANVAS'", [x, y])
                    if not clear:
                        continue
                    await page.mouse.click(x, y)
                    await asyncio.sleep(.15)
                    _, after = await sample_ready()
                    dom = await page.evaluate("""() => {const img=document.querySelector('h2 img');let svg='';
                      if(img?.src.startsWith('data:image/svg+xml;base64,'))svg=atob(img.src.split(',')[1]);
                      else if(img?.src.startsWith('data:image/svg+xml'))svg=decodeURIComponent(img.src.split(',').slice(1).join(','));
                      return {headings:[...document.querySelectorAll('h2')].map(e=>e.innerText),
                      heading_fill:svg.match(/fill=['\"]([^'\"]+)['\"]/)?.[1]??null,
                      rows:[...document.querySelectorAll('p[title]')].map(e=>({unit:e.title,text:e.innerText})),
                      upgrade_buttons:[...document.querySelectorAll('div[title]')]
                        .filter(e=>/^(Upgrade|Downgrade) to /.test(e.title)&&e.getBoundingClientRect().width>0)
                        .map(e=>({title:e.title,cursor:getComputedStyle(e).cursor,filter:getComputedStyle(e).filter,
                          lock_glyph:e.innerText.includes('🔒'),
                          icon_visibility:[...e.querySelectorAll('img')].map(i=>getComputedStyle(i).visibility)})),
                      titles:[...document.querySelectorAll('[title]')].filter(e=>e.getBoundingClientRect().width>0)
                        .map(e=>({tag:e.tagName,title:e.title,text:e.innerText})).slice(0,80)}}""")
                    _, bracket_end=await sample_ready()
                    target = next((t for t in after["towers"] if t["id"] == current["id"]), None)
                    end_target=next((t for t in bracket_end['towers'] if t['id']==current['id']),None)
                    selected = after["selected_tower"] == current["id"] == bracket_end['selected_tower']
                    stable=target is not None and end_target is not None and all(
                        target.get(k)==end_target.get(k) for k in ('units7','type','owner','relation','morale','delay_ticks'))
                    counts_stable=after.get('own_tower_counts')==bracket_end.get('own_tower_counts')
                    units = decode_units(target["units7"]) if target else None
                    counts = dict(units.counts) if units else None
                    expected_fill={'SELF':'#74b9ffff','NEUTRAL':'none','ENEMY':'#c0392bff','ALLY':'#8644fcff'}.get(target['relation']) if target else None
                    relation_check={'ui_fill':dom['heading_fill'],'expected_fill':expected_fill,
                        'coherent':selected and stable,'match':selected and stable and expected_fill is not None and dom['heading_fill']==expected_fill}
                    comparisons = []
                    prerequisite_comparisons=[]
                    upgrade_ui_comparisons=[]
                    for row in dom["rows"]:
                        name = UNIT_ZH.get(row["unit"], row["unit"])
                        if name in UNIT_NAMES and counts is not None and '/' in row['text']:
                            unit = UNIT_NAMES.index(name)
                            expected_capacity=dict(rules.capacity(target['type'],target['morale']).counts)[unit]
                            comparisons.append({"unit": row["unit"], "ui": int(row["text"].split('/')[0]),
                                                "memory": counts[unit],
                                                "capacity_ui":int(row['text'].split('/')[1]),
                                                "capacity_memory":expected_capacity,
                                                "capacity_match":selected and stable and int(row['text'].split('/')[1])==expected_capacity,
                                                "coherent":selected and stable,
                                                "match": selected and stable and int(row["text"].split('/')[0]) == counts[unit]})
                        elif row['unit'] in TOWER_TYPE_ZH and '/' in row['text'] and target and target['relation']=='SELF':
                            kind=TOWER_TYPES.index(TOWER_TYPE_ZH[row['unit']])
                            own_counts=after.get('own_tower_counts')
                            have,need=map(int,row['text'].split('/'))
                            expected_needs={rules.PREREQUISITES[t][kind] for t,p in enumerate(rules.DOWNGRADE)
                                            if p==target['type'] and rules.PREREQUISITES[t][kind]}
                            coherent=selected and stable and counts_stable and own_counts is not None
                            prerequisite_comparisons.append({'type':kind,'ui_have':have,'ui_need':need,
                                'observed_have':own_counts[kind] if own_counts else None,
                                'coherent':coherent,'count_match':coherent and have==own_counts[kind],
                                'requirement_match':coherent and need in expected_needs})
                    for button in dom['upgrade_buttons']:
                        label=button['title'].split(' to ',1)[1]
                        name=TOWER_TYPE_ZH.get(label,label)
                        if name not in TOWER_TYPES or target is None or target['relation']!='SELF':
                            continue
                        kind=TOWER_TYPES.index(name)
                        dimmed=button['filter']=='brightness(0.7)'
                        disabled=True if dimmed and button['cursor']=='auto' else False if not dimmed and button['cursor']=='pointer' else None
                        visible_icons=button['icon_visibility']
                        locked=True if button['lock_glyph'] and 'hidden' in visible_icons else False if not button['lock_glyph'] and visible_icons and all(v=='visible' for v in visible_icons) else None
                        own_counts=after.get('own_tower_counts')
                        expected=all(have>=need for have,need in zip(own_counts,rules.PREREQUISITES[kind])) if own_counts is not None else None
                        coherent=selected and stable and counts_stable and own_counts is not None and disabled is not None
                        upgrade_ui_comparisons.append({'target_type':kind,'ui_disabled':disabled,
                            'ui_locked':locked,'prerequisites_met':expected,'coherent':coherent,
                            'disabled_match':coherent and disabled==(not expected),
                            'command_eligibility':'UNKNOWN'})
                    rows.append({"id": current["id"], "selected_id": after["selected_tower"],
                        "selection_confirmed": selected, "relation": current["relation"],
                        "type": TOWER_TYPES[target["type"]] if target else None,
                        "type_id":target['type'] if target else None,
                        "units7":target['units7'] if target else None,
                        "morale":target['morale'] if target else None,
                        "delay_ticks":target['delay_ticks'] if target else None,
                        "tick_bracket":[after['tick'],bracket_end['tick']],
                        "sample_bracket":[after['sampled_at_ms'],bracket_end['sampled_at_ms']],
                        "relation_check":relation_check,
                        "own_tower_counts":after.get('own_tower_counts'),
                        "prerequisite_comparisons":prerequisite_comparisons,
                        'upgrade_ui_comparisons':upgrade_ui_comparisons,
                        'document_time_origin':after['document_time_origin'],
                        'player_id':after['player_id'],'client_sha256':before_state.client_sha256,
                        "ui": dom, "comparisons": comparisons})
                    rows[-1]['match_epoch']=first_state.match_id.value
                    rows[-1]['round']=round_index
                    rows[-1]['source_mode']=after['transport_mode']
                    rows[-1]['units_kind']='SINGLE' if target and target['units7'][0]==1 else 'MANY'
                    print(json.dumps({'round':round_index,'tower_id':current['id'],'relation':current['relation'],
                        'unit_fields':len(comparisons),'coherent':selected and stable}),flush=True)
        except Exception as error:
            errors.append(str(error)[:300])
        finally:
            await ex.close()
    # Count independently reread DOM fields once per tower/source revision.
    # Stable values across later revisions remain separate fresh observations.
    unique_fields = {}
    strata = {}
    for row in rows:
        base = (row['match_epoch'], row['id'], row['tick_bracket'][0])
        group = f"{row['relation']}:{row['units_kind']}"
        stratum = strata.setdefault(group, {'selections': 0, 'unit_fields': 0,
            'matched_unit_fields': 0, 'tower_ids': set(), 'tower_types': set()})
        stratum['selections'] += int(row['selection_confirmed'])
        stratum['tower_ids'].add(row['id'])
        stratum['tower_types'].add(row['type'])
        for comparison in row['comparisons']:
            key = (*base, 'unit_count', comparison['unit'])
            if comparison['coherent'] and key not in unique_fields:
                unique_fields[key] = bool(comparison['match'])
                stratum['unit_fields'] += 1
                stratum['matched_unit_fields'] += int(comparison['match'])
    for stratum in strata.values():
        stratum['tower_ids'] = sorted(stratum['tower_ids'])
        stratum['tower_types'] = sorted(t for t in stratum['tower_types'] if t is not None)
    report = {"status": "PARTIAL", "timestamp": time.time(), "rows": rows,
        'unique_unit_fields':len(unique_fields),
        'unique_matched_unit_fields':sum(unique_fields.values()), 'strata':strata,
        "requested_rounds":args.rounds,"errors":errors,
        "compared_fields": sum(len(r["comparisons"]) for r in rows),
        "matched_fields": sum(c["match"] for r in rows for c in r["comparisons"]),
        "coherent_fields":sum(c['coherent'] for r in rows for c in r['comparisons']),
        "relation_fields":sum(r['relation_check']['coherent'] for r in rows),
        "matched_relations":sum(r['relation_check']['match'] for r in rows),
        "coherent_capacity_fields":sum(c['coherent'] for r in rows for c in r['comparisons']),
        "matched_capacity_fields":sum(c['capacity_match'] for r in rows for c in r['comparisons']),
        "coherent_prerequisite_fields":sum(c['coherent'] for r in rows for c in r['prerequisite_comparisons']),
        "matched_prerequisite_counts":sum(c['count_match'] for r in rows for c in r['prerequisite_comparisons']),
        "matched_prerequisite_requirements":sum(c['requirement_match'] for r in rows for c in r['prerequisite_comparisons']),
        'coherent_upgrade_ui_fields':sum(c['coherent'] for r in rows for c in r['upgrade_ui_comparisons']),
        'matched_upgrade_ui_fields':sum(c['disabled_match'] for r in rows for c in r['upgrade_ui_comparisons']),
        'observed_upgrade_lock_fields':sum(c['ui_locked'] is not None and c['coherent'] for r in rows for c in r['upgrade_ui_comparisons']),
        "tactical_commands": 0, "limits": "limited selections, candidate camera, not M1 gate evidence"}
    (out / "ui-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    (out / f"ui-comparison-{uuid4().hex[:12]}.json").write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.rounds<=50:parser.error('rounds must be 1..50')
    asyncio.run(main(args))
