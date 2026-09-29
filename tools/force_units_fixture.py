"""從已保存的官方介面配對建立離線可派兵力樣本，不連線遊戲。"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kiomet_ai.force_units import mirror_force_units
from kiomet_ai.observe import decode_tower_type, decode_tower_units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT / "runtime/research/units/units_ground_truth.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "runtime/research/force_units/fixtures.json")
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf8"))
    examples = []
    for round_index, round_ in enumerate(source["rounds"], 1):
        for sample in round_["towers"]:
            raw = sample["struct_bytes"]
            counts = decode_tower_units(raw, sample["tower_ref"])
            tower_type = decode_tower_type(raw)
            result = mirror_force_units(counts,tower_type)
            if result is None:
                raise ValueError(f"塔 {sample['packed_id']} 的輸入不完整")
            owner = {"OTHER":"ENEMY","UNKNOWN":"NEUTRAL"}.get(
                sample["owner_candidate"],sample["owner_candidate"])
            examples.append({"match_id":source["match_id"],"timestamp":round_["time"],
                             "round":round_index,"tower_id":sample["packed_id"],
                             "tower_ref":sample["tower_ref"],"owner":owner,"tower_type":tower_type,
                             "source_bytes_38_46":raw[38:47],"current_counts":asdict(counts),
                             "mirror":asdict(result),"ui":sample["info"]["rows"]})
    report = {"status":"OFFLINE_DERIVED_NOT_RUNTIME_VALIDATED",
              "production_sha256":"fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c",
              "sample_count":len(examples),"examples":examples}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"sample_count":len(examples),
                      "owners":sorted({x["owner"] for x in examples}),
                      "tower_types":sorted({x["tower_type"] for x in examples})},ensure_ascii=False))


if __name__ == "__main__":
    main()
