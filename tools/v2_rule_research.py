"""Evaluate two pure pinned rule functions OFFLINE, never call live WASM."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/research/v2'
SHA='fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c'


def leb(data,p,signed=False):
    n=shift=0
    while True:
        byte=data[p];p+=1;n|=(byte&127)<<shift;shift+=7
        if not byte&128:
            if signed and byte&64:n-=1<<shift
            return n,p


def static_data(data):
    memory=bytearray(1400000)
    p=8
    while p<len(data):
        section=data[p];size,a=leb(data,p+1);p=a+size
        if section!=11:continue
        count,a=leb(data,a)
        for _ in range(count):
            flag,a=leb(data,a)
            if flag==2:_,a=leb(data,a)
            if flag not in (0,2):raise ValueError('unsupported passive data')
            assert data[a]==0x41
            offset,a=leb(data,a+1,True);assert data[a]==0x0b;a+=1
            size,a=leb(data,a);memory[offset:offset+size]=data[a:a+size];a+=size
    return memory


def evaluate(lines,args,memory):
    """Small whitelist for scalar constants/branches/static table loads only."""
    instructions=[l.strip() for l in lines[1:] if not l.strip().startswith('(local') and l.strip()!=')']
    ends={}
    for i,l in enumerate(instructions):
        if l.startswith('end '):ends[l.split()[1]]=i
    local={f'$var{i}':n for i,n in enumerate(args)}
    stack=[];writes={};pc=0
    def pop():return stack.pop()
    while pc<len(instructions):
        line=instructions[pc];pc+=1;parts=line.split();op=parts[0]
        if op in ('block','end'):continue
        if op=='local.get':stack.append(local.get(parts[1],0))
        elif op=='local.set':local[parts[1]]=pop()
        elif op=='local.tee':local[parts[1]]=stack[-1]
        elif op=='i32.const':stack.append(int(parts[1])&0xffffffff)
        elif op=='i32.eqz':stack.append(int(pop()==0))
        elif op in ('i32.and','i32.sub','i32.shl','i32.ne','i32.eq'):
            b,a=pop(),pop()
            stack.append({'i32.and':lambda:a&b,'i32.sub':lambda:(a-b)&0xffffffff,
                'i32.shl':lambda:(a<<(b&31))&0xffffffff,'i32.ne':lambda:int(a!=b),
                'i32.eq':lambda:int(a==b)}[op]())
        elif op=='br_table':
            index=pop();labels=parts[1:];pc=ends[labels[min(index,len(labels)-1)]]+1
        elif op=='br':pc=ends[parts[1]]+1
        elif op=='br_if':
            if pop():pc=ends[parts[1]]+1
        elif op=='return':return stack[-1],writes
        elif op=='i32.load':
            offset=int(parts[1].split('=')[1]);stack.append(struct.unpack_from('<I',memory,pop()+offset)[0])
        elif op=='i32.store16':
            offset=int(parts[1].split('=')[1]) if len(parts)>1 else 0
            value,address=pop(),pop();writes[address+offset]=value&65535
        else:raise ValueError('unsupported offline rule instruction: '+line)
    return stack[-1] if stack else None,writes


def main():
    data=(OUT/(SHA+'.wasm')).read_bytes()
    assert hashlib.sha256(data).hexdigest()==SHA
    dis=json.loads((OUT/'disassembly.json').read_text());L=dis['lines']
    def function(name):
        a=next(i for i,l in enumerate(L) if l.startswith('  (func $'+name+' '))
        b=next((i for i in range(a+1,len(L)) if L[i].startswith('  (func ')),len(L))
        return L[a:b]
    memory=static_data(data)
    capacity=function('TowerType::raw_unit_capacity')
    generation=function('TowerType::unit_generation')
    report={'client_sha256':SHA,'provenance':'offline evaluation of pinned pure scalar rule functions; static data only',
        'capacity':[],'generation_ticks':[]}
    for tower in range(27):
        report['capacity'].append([evaluate(capacity,[tower,u],memory)[0] for u in range(10)])
        row=[]
        for unit in range(10):
            _,w=evaluate(generation,[0,tower,unit],memory)
            row.append(w[2] if w[0] else None)
        report['generation_ticks'].append(row)
    path=OUT/'pinned-rules.json';path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':main()
