"""Conservative observed-force tracking; not a world simulator."""
from math import isqrt
from uuid import uuid4
from ..state import Fact, Force, Knowledge, Relation


def motion(units,source_position,destination_position,accelerated,progress):
    """Pinned Force::speed/progress_required; nominal current-leg ETA only."""
    if units is None:
        return None
    counts = dict(units.counts)
    active = [i for i,n in units.counts if n]
    if not active:
        raise ValueError("empty moving force")
    if counts[2]:
        carry = 4 * counts[2]
        speed = 3 if 2*counts[4]+counts[5] <= carry else 2 if 2*counts[4] <= carry else 1
    else:
        speed = min(1 if i in (4,8) else 3 if i in (0,1,2,3,6) else 2 for i in active)
    if source_position is None or destination_position is None:
        return speed,None,None
    dx = source_position[0]-destination_position[0]
    dy = source_position[1]-destination_position[1]
    required = min(255,isqrt(dx*dx+dy*dy)*180//10)
    if accelerated:
        required = max(1,required*4//5)
    if required < 1:
        raise ValueError("zero length force segment")
    ticks = max(0,(required-progress+speed-1)//speed)
    return speed,required,ticks*250


def known(value,source,at,knowledge=Knowledge.OBSERVED):
    return Fact(value,knowledge,source,at) if value is not None else Fact()


class ForceTracker:
    """Only unique continuations get a DERIVED ID. Ambiguous tracks stay unknown."""
    def __init__(self):
        self.scope = None
        self.previous = []
        self.last_tick = None
        self.last_at = None

    def clear(self):
        self.scope = self.last_tick = self.last_at = None
        self.previous = []

    def update(self,rows,towers,match_identity,tick,at,decode_units):
        if match_identity is None or tick is None:
            self.clear()
        if match_identity != self.scope or self.last_at is not None and not 0<=at-self.last_at<=1000:
            self.clear()
        self.scope = match_identity
        positions = {t.id:t.position.value for t in towers}
        delta = (tick-self.last_tick)&65535 if self.last_tick is not None and tick is not None else None
        current = []
        for row in rows:
            if row.get('visible') is not True or not row.get('visibility_source'):
                raise ValueError('force lacks current visibility evidence')
            for endpoint in ('source','destination'):
                if row.get(endpoint) is not None and row[endpoint] not in positions:
                    raise ValueError('hidden force endpoint')
            units = decode_units(row['units7'])
            signature = (row['owner'],row['source'],row['destination'],units)
            model = motion(units,positions.get(row['source']),positions.get(row['destination']),
                           row['accelerated'],row['progress'])
            current.append(dict(row=row,units=units,signature=signature,model=model,candidates=[]))
        for c in current:
            for i,p in enumerate(self.previous):
                if p['signature'] != c['signature'] or p['id'] is None or delta is None or delta>16:
                    continue
                progress = c['row']['progress']-p['progress']
                # No guessing by vector index, raw pointer or nearest progress.
                if (c['model'] and progress == c['model'][0]*delta) or (delta==0 and progress==0):
                    c['candidates'].append(i)
        uses = {}
        for c in current:
            for i in c['candidates']:
                uses[i] = uses.get(i,0)+1
        new_previous,forces = [],[]
        for c in current:
            row = c['row']
            duplicate = sum(x['signature']==c['signature'] and x['row']['progress']==row['progress'] for x in current)>1
            if len(c['candidates'])==1 and uses[c['candidates'][0]]==1 and not duplicate:
                p=self.previous[c['candidates'][0]]
                identity,first_seen,confidence = p['id'],p['first_seen'],'UNIQUE_CONTINUATION'
            elif c['candidates'] or duplicate or match_identity is None:
                identity,first_seen,confidence = None,None,'AMBIGUOUS'
            else:
                identity,first_seen,confidence = f'{match_identity}:f:{uuid4().hex}',at,'NEW_TRACK'
            new_previous.append(dict(signature=c['signature'],progress=row['progress'],id=identity,first_seen=first_seen))
            relation=Relation(row['relation']) if row['relation'] is not None else None
            force=Force(
                known(identity,'unique observation continuation; document/match scoped',at,Knowledge.DERIVED),
                known(True,row['visibility_source'],at),
                owner=known(row['owner'],'visible Force.owner+12',at),
                relation=known(relation,'pinned normal visible force Color::new owner/alliance query',at,
                    Knowledge.DERIVED if relation in (Relation.ALLY,Relation.ENEMY) else Knowledge.OBSERVED),
                source=known(row['source'],'current segment endpoint intersect current observed towers',at),
                destination=known(row['destination'],'current segment endpoint intersect current observed towers',at),
                units=known(c['units'],'visible Force.units+14',at),
                unit_count=known(sum(n for _,n in c['units'].counts),
                    'sum of complete visible typed force vector',at,Knowledge.DERIVED),
                progress=known(row['progress'],'visible Force.path_progress+22',at),
                accelerated=known(bool(row['accelerated']),'visible Force.accelerated+21; normal renderer',at),
                first_seen_ms=known(first_seen,'first observation in this unique track; not launch time',at),
                confidence=known(confidence,'conservative unique tick/progress continuation',at,Knowledge.DERIVED),
                eta_ms=known(c['model'][2] if c['model'] else None,
                    'pinned current-leg remaining simulation ticks at 4 Hz; nominal duration, not a clock',at,Knowledge.DERIVED))
            forces.append(force)
        self.previous = new_previous if match_identity is not None else []
        self.last_tick,self.last_at=tick,at
        return tuple(forces)
