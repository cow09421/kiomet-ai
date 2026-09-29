"""研究工具的失敗條件與索引無關比對；不接觸正式頁面。"""
import copy
import importlib.util
from pathlib import Path

import pytest


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matcher = load_tool("wasm_function_matcher")
reporter = load_tool("wasm_anchor_report")


def test_objdump_call_edges_memory_and_constants():
    details = """ - type[0] (i32) -> i32
 - func[0] sig=0 <env.lookup> <- env.lookup
 - func[1] sig=0 <tower>
 - func[1] size=12
"""
    code = """000010 func[1] <tower>:
 000011: 20 00 | local.get 0
 000013: 28 02 24 | i32.load 2 36
 000016: 41 05 | i32.const 5
 000018: 10 00 | call 0 <env.lookup>
 00001a: 0b | end
"""
    parsed = matcher.parse_dump(details, code)["functions"]
    assert parsed[0]["callers"] == [1]
    assert parsed[1]["memory_ops"] == ["i32.load 2 36"]
    assert parsed[1]["constants"] == ["i32.const 5"]
    renamed = copy.deepcopy(parsed[1])
    renamed.update(index=890, name="unrelated-index", calls=[501])
    assert matcher.similarity(parsed[1], renamed)[0] == pytest.approx(1)
    with pytest.raises(ValueError, match="Missing disassembly"):
        matcher.parse_dump(details, "")


def evidence():
    samples = []
    for round_id in range(3):
        for x in (10, 11):
            samples.append(dict(round=round_id, packed_id=x | 20 << 16,
                                id=[x, 20], tower_ref=4096+x*48, position=[x*5, 100], owner="SELF"))
    game = {"state": "IN_MATCH", "match": {"id": "test-match"}}
    return dict(game_before=game, game_after=copy.deepcopy(game), samples=samples, sha256="fixture",
                graph=dict(directions=[[0,1],[1,1],[1,0],[1,-1],[0,-1],[-1,-1],[-1,0],[-1,1]],
                           nodes=[dict(id=10 | 20 << 16, mask=4), dict(id=11 | 20 << 16, mask=64)]),
                max_pause_seconds=.01, pause_seconds=[.01]*6)


def test_anchor_requires_repeatability_and_reciprocal_visible_edges():
    data = evidence()
    assert reporter.summarize(data)["undirected_edges"] == 1
    data["graph"]["nodes"][1]["mask"] = 0
    with pytest.raises(ValueError, match="雙向"):
        reporter.summarize(data)
    data = evidence()
    data["samples"][0]["tower_ref"] += 48
    with pytest.raises(ValueError, match="三輪"):
        reporter.summarize(data)


def test_anchor_rejects_cross_match_and_unobserved_data():
    data = evidence()
    data["game_after"]["match"]["id"] = "other-match"
    with pytest.raises(ValueError, match="換局"):
        reporter.summarize(data)
    data = evidence()
    data["graph"]["nodes"].append(dict(id=9 | 20 << 16, mask=4))
    with pytest.raises(ValueError, match="未觀察"):
        reporter.summarize(data)


def test_anchor_report_separates_allies_from_enemies_by_render_color():
    data = evidence()
    for sample in data["samples"]:
        sample["render_color"] = 2 if sample["id"][0] == 10 else 3
        sample["owner"] = "OTHER"

    report = reporter.summarize(data)

    assert report["owner_counts"] == {"ALLY": 1, "ENEMY": 1}
    assert {tower["id"][0]: tower["owner"] for tower in report["towers"]} == {
        10: "ALLY", 11: "ENEMY"}


def test_anchor_report_never_falls_back_from_unknown_supplied_color():
    data = evidence()
    for sample in data["samples"]:
        sample["render_color"] = 9
        sample["owner"] = "SELF"

    report = reporter.summarize(data)

    assert report["owner_counts"] == {"UNKNOWN": 2}
    assert all(tower["owner"] == "UNKNOWN" for tower in report["towers"])


def test_anchor_report_keeps_legacy_owner_only_when_color_is_absent():
    assert reporter.summarize(evidence())["owner_counts"] == {"SELF": 2}
    assert reporter.owner_from_sample({}) == "UNKNOWN"


def test_anchor_repeatability_includes_owner_color_identity():
    data = evidence()
    for sample in data["samples"]:
        sample["render_color"] = 2
        sample["owner"] = "OTHER"
    data["samples"][-1]["render_color"] = 3

    with pytest.raises(ValueError, match="三輪"):
        reporter.summarize(data)
