"""從本機 WASM 反組譯輸出指定函式；只讀檔案，不連線遊戲。"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OBJDUMP = ROOT / "runtime/research/source-map/toolchain/wabt-1.0.42/bin/wasm-objdump.exe"
HEADER = re.compile(r"^\s*[0-9a-f]+ func\[(\d+)\]")


def extract(wasm: Path, indices: set[int]):
    process = subprocess.Popen([str(OBJDUMP), "-d", str(wasm)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf8", errors="replace")
    selected = None
    results = {i: [] for i in indices}
    for line in process.stdout:
        match = HEADER.match(line)
        if match:
            index = int(match.group(1))
            selected = index if index in indices else None
        if selected is not None:
            results[selected].append(line.rstrip() + "\n")
    error = process.stderr.read()
    if process.wait() != 0:
        raise RuntimeError(error)
    if any(not lines for lines in results.values()):
        raise ValueError(f"找不到函式：{[i for i,v in results.items() if not v]}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wasm", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("indices", type=int, nargs="+")
    args = parser.parse_args()
    digest = hashlib.sha256(args.wasm.read_bytes()).hexdigest()
    if args.wasm.name == "production-client_bg.wasm" and digest != \
            "fae13d1d0a7683726db520ec5c687d67d701c874a5708aeb9bff6eaacf2f054c":
        raise ValueError("正式 WASM 版本不同，拒絕沿用函式索引")
    args.output.mkdir(parents=True, exist_ok=True)
    results = extract(args.wasm, set(args.indices))
    for index, lines in results.items():
        (args.output / f"func-{index}.txt").write_text("".join(lines), encoding="utf8")
    print({"sha256":digest,"functions":{i:len(lines) for i,lines in results.items()}})


if __name__ == "__main__":
    main()
