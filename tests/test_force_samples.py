"""自然 Moving Force（移動軍隊）樣本登錄器測試。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from force_samples import record_sample


def test_record_and_reload(tmp_path, monkeypatch):
    import force_samples
    monkeypatch.setattr(force_samples, "STORE", tmp_path / "natural")
    dest = force_samples.record_sample(
        match_id="m9", evidence_path="shot-001.jpg",
        visible_color="ENEMY", approx_source=17498401,
        approx_target=17498404, path_kind="road",
        timestamp=123.456)
    assert dest.exists()
    rows = force_samples.load_all()
    assert len(rows) == 1
    assert rows[0]["sample_id"] == "natural-001"
    assert rows[0]["match_id"] == "m9"
    assert rows[0]["visible_color"] == "ENEMY"
    assert rows[0]["approx_source"] == 17498401
    assert rows[0]["sent_actions_context"] == 0


def test_unknown_fields_stay_none(tmp_path, monkeypatch):
    import force_samples
    monkeypatch.setattr(force_samples, "STORE", tmp_path / "natural")
    force_samples.record_sample("m9", "shot-002.jpg", "UNKNOWN")
    rows = force_samples.load_all()
    assert rows[-1]["approx_source"] is None
    assert rows[-1]["runtime_candidate"] is None
