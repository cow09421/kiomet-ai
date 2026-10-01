"""Strict restoration of previously recorded canonical player-visible state."""
from dataclasses import fields
from .state import Fact, Force, GameState, Knowledge, Tower, Units


def freeze(value):
    if isinstance(value,list): return tuple(freeze(v) for v in value)
    if isinstance(value,dict):
        if set(value)=={'counts'}: return Units(freeze(value['counts']))
        raise ValueError('unexpected object inside canonical fact')
    return value


def fact_from_dict(row, transform=freeze):
    return Fact(transform(row['value']),Knowledge(row['knowledge']),row['source'],row['observed_at_ms'])


def entity_from_dict(kind,row):
    expected={f.name for f in fields(kind)}
    if set(row)-expected: raise ValueError('unsupported recorded entity fields')
    return kind(**{key:(value if kind is Tower and key=='id' else fact_from_dict(value))
                   for key,value in row.items()})


def state_from_dict(row):
    expected={f.name for f in fields(GameState)}
    if set(row)-expected: raise ValueError('unsupported recorded state fields')
    values={}
    for key,value in row.items():
        if key=='towers': values[key]=tuple(entity_from_dict(Tower,t) for t in value)
        elif key=='forces':
            values[key]=fact_from_dict(value,lambda v:None if v is None else tuple(entity_from_dict(Force,f) for f in v))
        elif isinstance(value,dict): values[key]=fact_from_dict(value)
        else: values[key]=value
    return GameState(**values)
