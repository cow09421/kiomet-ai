from tools.v2_semantic_checkpoint_metrics import outcomes, risk


def test_competing_risk_preserves_exact_until_first_semantic_censor():
    row = {'clean_ticks': 7, 'first_stop': {'offset': 8, 'kind': 'CENSORED_BY_UNKNOWN', 'reason': 'PRODUCTION_SUPPLY_LINE'}}
    result = outcomes(row)
    assert result['4'] == 'EXACT_SURVIVAL'
    assert result['8'] == result['16'] == result['20'] == 'SUPPLY_LINE_CENSOR'


def test_observed_input_loss_not_misreported_as_arrival_semantics():
    assert risk({'kind': 'CENSORED_BY_UNKNOWN', 'reason': 'OBSERVED_ENDPOINT:NOT_READY'}) == 'INPUT_UNKNOWN'
    assert risk({'kind': 'CENSORED_BY_UNKNOWN', 'reason': 'UNKNOWN_POST_ARRIVAL_PATH'}) == 'ARRIVAL_CENSOR'
    assert risk({'kind': 'RIGHT_CENSORED_RECORDING_END', 'reason': 'RECORDING_END'}) == 'RECORDING_END'
    assert risk({'kind': 'MISMATCH', 'reason': 'EXACT_OBSERVABLE_SIGNATURE_MISMATCH'}) == 'MISMATCH'
