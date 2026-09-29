"""唯讀解出 WASM 主動資料段指定線性記憶體地址的 bytes。"""
from pathlib import Path
import argparse


def uleb(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, pos
        shift += 7


def sleb(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7f) << shift
        shift += 7
        if byte < 0x80:
            if byte & 0x40:
                value -= 1 << shift
            return value, pos


def active_segments(wasm: bytes):
    if wasm[:8] != b"\0asm\x01\0\0\0":
        raise ValueError("invalid wasm header")
    pos = 8
    while pos < len(wasm):
        section = wasm[pos]
        pos += 1
        size, pos = uleb(wasm, pos)
        end = pos + size
        if section == 11:
            count, pos = uleb(wasm, pos)
            for _ in range(count):
                flags, pos = uleb(wasm, pos)
                if flags == 1:
                    n, pos = uleb(wasm, pos)
                    pos += n
                    continue
                if flags == 2:
                    _, pos = uleb(wasm, pos)  # memory index
                elif flags != 0:
                    raise ValueError(f"unsupported data flags {flags}")
                if wasm[pos] != 0x41:
                    raise ValueError("unsupported init expression")
                addr, pos = sleb(wasm, pos + 1)
                if wasm[pos] != 0x0b:
                    raise ValueError("invalid init expression")
                pos += 1
                n, pos = uleb(wasm, pos)
                yield addr, wasm[pos:pos+n]
                pos += n
            return
        pos = end


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wasm", type=Path)
    parser.add_argument("address", type=lambda x: int(x, 0))
    parser.add_argument("length", type=int)
    args = parser.parse_args()
    wasm = args.wasm.read_bytes()
    for start, payload in active_segments(wasm):
        if start <= args.address and args.address + args.length <= start + len(payload):
            result = payload[args.address-start:args.address-start+args.length]
            print({"segment_start": start, "segment_length": len(payload), "hex": result.hex(" ")})
            return
    raise SystemExit("address not in one static active segment")


if __name__ == "__main__":
    main()
