"""Finite pinned pure damage/field evaluation, offline static inputs only."""
import hashlib,json
from pathlib import Path
from v2_rule_research import OUT, SHA, evaluate, static_data

def main():
    wasm=(OUT/(SHA+'.wasm')).read_bytes()
    assert hashlib.sha256(wasm).hexdigest()==SHA
    memory=static_data(wasm)
    data=json.loads((OUT/'disassembly.json').read_text())
    lines=data['lines']
    def function(name):
        a=next(i for i,l in enumerate(lines) if l.startswith('  (func $'+name+' '))
        b=next(i for i in range(a+1,len(lines)) if lines[i].startswith('  (func '))
        return lines[a:b]
    damage=function('Unit::damage')
    field=function('Unit::field')
    values=[]
    for unit in (0,4,5,9):
        values.append({'unit':unit,'surface_damage':evaluate(damage,[unit,0,0],memory)[0],
                       'in_force_field':evaluate(field,[unit,0,1,0],memory)[0],
                       'in_tower_field':evaluate(field,[unit,0,0,0],memory)[0]})
    report={'question':'Does the pinned production pure damage/field rule support an ordinary ground-only model?',
            'status':'PASS_SCALAR_RULES_ONLY','client_sha256':SHA,'values':values,
            'source_offsets':{'damage':'0x126c57..0x126caa','field':'0x14178d..0x1417bc'},
            'limits':'Ground scalar rules only, not fight ordering/arrival/king elimination/live combat accuracy.',
            'tool_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'m2-ground-combat-rules.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))

if __name__=='__main__':main()
