"""Save existing permitted observer boundaries around the bounded UI recorder.

No additional browser reads, private fields or input routes are introduced.
L0 is UNKNOWN. L1 is the decoded visible extractor output, not predecoder data.
"""
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from tools import v2_controlled_transition_capture as recorder
from kiomet_ai.v2.observe.extractor import ClientExtractor, decode_units
from kiomet_ai.v2.serialization import state_from_dict
from kiomet_ai.v2.sim.model import from_canonical, UnsupportedState
from kiomet_ai.v2.control import control_readiness_gaps

FORCE_FIELDS = ('visible', 'visibility_source', 'owner', 'relation', 'source',
                'destination', 'units7', 'progress', 'accelerated')


def visible_output(raw):
    return [{key: row.get(key) for key in FORCE_FIELDS}
            for row in raw.get('forces', []) if row.get('visible') is True]


def mapping(rows, state):
    """Unique owner/vector/progress in this exact scope/sample; IDs unused."""
    def key_raw(row):
        return (row['owner'], decode_units(row['units7']), row['progress'])
    def key_canonical(force):
        return (force.owner.value, force.units.value, force.progress.value)
    keys = [key_raw(row) for row in rows]
    canonical = list(state.forces.value or ())
    other = [key_canonical(force) for force in canonical]
    return [{'extractor_row': i, 'canonical_index': other.index(key) if
             keys.count(key) == 1 and other.count(key) == 1 else None,
             'status': 'UNIQUE_SAME_SAMPLE' if keys.count(key) == 1 and
             other.count(key) == 1 else 'AMBIGUOUS'} for i, key in enumerate(keys)]


def layer_record(state, raw):
    serialized = json.dumps(asdict(state), separators=(',', ':'))
    restored = state_from_dict(json.loads(serialized))
    decoded = visible_output(raw)
    try:
        simulated = {'status': 'PRESENT', 'state': asdict(from_canonical(restored))}
    except UnsupportedState as exc:
        simulated = {'status': 'REFUSED', 'reason': str(exc)}
    identity = {'document_id': state.document_id,
                'document_time_origin_ms': state.document_time_origin_ms.value,
                'match_id': state.match_id.value,
                'player_id': state.player_id.value, 'sequence': state.sequence,
                'tick': state.tick.value, 'host_monotonic_ms': int(time.monotonic()*1000)}
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    return {'snapshot_identity': identity, 'snapshot_sha256': digest,
            'L0': {'status': 'UNKNOWN', 'reason': 'preextractor boundary not retained; no private research'},
            'L1': {'status': 'PRESENT_DECODED_VISIBLE_EXTRACTOR_OUTPUT', 'forces': decoded},
            'L2': json.loads(serialized),
            'L3': {'status': 'ROUNDTRIP_EQUAL' if restored == state else 'MISMATCH',
                   'snapshot_sha256': digest}, 'L4': simulated,
            'L5': {'gaps': control_readiness_gaps(restored, restored.received_at_ms)},
            'cross_layer_force_mapping': mapping(decoded, state)}


async def main(args):
    path = ROOT / 'runtime/research/v2' / ('paired-layers-' + uuid4().hex[:12] + '.jsonl')
    original = ClientExtractor._normalize_world
    with path.open('w', encoding='utf8') as output:
        def capture(self, *inputs):
            state, raw = original(self, *inputs)
            output.write(json.dumps(layer_record(state, raw), separators=(',', ':')) + '\n')
            output.flush()
            return state, raw
        ClientExtractor._normalize_world = capture
        try:
            await recorder.bounded_main(args)
        finally:
            ClientExtractor._normalize_world = original
    print(json.dumps({'paired_layers': str(path.relative_to(ROOT))}), flush=True)


if __name__ == '__main__':
    args = recorder.parse_args()
    if args.input_entry_observer:
        raise SystemExit('paired pilot uses existing ordinary UI route only')
    asyncio.run(main(args))
