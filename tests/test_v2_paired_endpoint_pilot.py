from types import SimpleNamespace
from tools.v2_paired_endpoint_pilot import visible_output, mapping
from kiomet_ai.v2.observe.extractor import decode_units


def test_v2_paired_sanitizes_nonvisible_and_private_fields():
    row = {'visible': True, 'owner': 3, 'source': None, 'destination': 2,
           'units7': [0]*7, 'progress': 0, 'root_pointer': 12345,
           'hidden_destination': 9}
    actual = visible_output({'forces': [row, {'visible': False, 'owner': 9}]})
    assert len(actual) == 1
    assert 'root_pointer' not in actual[0] and 'hidden_destination' not in actual[0]
    assert actual[0]['source'] is None


def test_v2_paired_duplicate_owner_vector_progress_is_ambiguous():
    rows = [{'owner': 3, 'units7': [0]*7, 'progress': 1}]*2
    fact = lambda x: SimpleNamespace(value=x)
    force = SimpleNamespace(owner=fact(3), units=fact(decode_units([0]*7)), progress=fact(1))
    state = SimpleNamespace(forces=fact((force, force)))
    assert all(r['status'] == 'AMBIGUOUS' and r['canonical_index'] is None
               for r in mapping(rows, state))
