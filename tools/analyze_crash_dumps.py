"""唯讀解析 Chromium Crashpad minidump（迷你傾印）的例外與模組。"""
import glob
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def parse(path):
    b = path.read_bytes()
    if b[:4] != b"MDMP":
        raise ValueError("不是 Minidump")
    count, directory = struct.unpack_from("<II", b, 8)
    streams = {kind: (size, rva) for kind, size, rva in
               (struct.unpack_from("<III", b, directory + i * 12) for i in range(count))}
    exception = streams[6][1]
    thread, code, flags, address = struct.unpack_from("<I4xII8xQ", b, exception)
    nparams = struct.unpack_from("<I", b, exception + 32)[0]
    exception_info = list(struct.unpack_from("<" + "Q" * min(nparams, 15), b, exception + 40))
    context_size, context_rva = struct.unpack_from("<II", b, exception + 160)
    registers = {name: f"0x{struct.unpack_from('<Q', b, context_rva + offset)[0]:X}"
                 for name, offset in {"rax": 0x78, "rcx": 0x80, "rdx": 0x88,
                                      "rsp": 0x98, "rbp": 0xA0, "rip": 0xF8}.items()}
    size, misc = streams[15]
    misc_flags, process = struct.unpack_from("<II", b, misc + 4)
    modules_rva = streams[4][1]
    nmodules = struct.unpack_from("<I", b, modules_rva)[0]
    modules = []
    for i in range(nmodules):
        offset = modules_rva + 4 + i * 108
        base, length, name_rva = struct.unpack_from("<QI8xI", b, offset)
        name_length = struct.unpack_from("<I", b, name_rva)[0]
        name = b[name_rva + 4:name_rva + 4 + name_length].decode("utf-16le", "replace")
        modules.append({"base": base, "size": length, "name": name})
    matching = [m for m in modules if m["base"] <= address < m["base"] + m["size"]]
    stack_candidates = []
    threads_rva = streams[3][1]
    nthreads = struct.unpack_from("<I", b, threads_rva)[0]
    for i in range(nthreads):
        thread_rva = threads_rva + 4 + i * 48
        tid = struct.unpack_from("<I", b, thread_rva)[0]
        if tid != thread:
            continue
        stack_base, stack_size, stack_rva = struct.unpack_from("<QII", b, thread_rva + 24)
        rsp = int(registers["rsp"], 16)
        if stack_base <= rsp < stack_base + stack_size:
            offset = stack_rva + rsp - stack_base
            for j in range(0, min(1024, stack_base + stack_size - rsp), 8):
                pointer = struct.unpack_from("<Q", b, offset + j)[0]
                owner = next((m for m in modules if m["base"] <= pointer < m["base"] + m["size"]), None)
                if owner:
                    stack_candidates.append({"stack_offset": j, "module": Path(owner["name"]).name,
                                             "module_offset": f"0x{pointer-owner['base']:X}"})
        break
    memory_regions = []
    if 16 in streams and len(exception_info) > 1:
        info_rva = streams[16][1]
        header_size, entry_size, entries = struct.unpack_from("<IIQ", b, info_rva)
        fault = exception_info[1]
        for i in range(entries):
            o = info_rva + header_size + i * entry_size
            base, alloc, alloc_protect, region_size, state, protect, region_type = struct.unpack_from(
                "<QQI4xQIII", b, o)
            if base <= fault < base + region_size or abs(base - fault) < 0x20000:
                memory_regions.append({"base": f"0x{base:X}", "size": f"0x{region_size:X}",
                                       "state": f"0x{state:X}", "protect": f"0x{protect:X}",
                                       "type": f"0x{region_type:X}"})
    return {"file": path.name, "bytes": len(b), "process_id": process if misc_flags & 1 else None,
            "renderer_marker": b.find("--type=renderer".encode("utf-16le")) >= 0,
            "gpu_marker": b.find("--type=gpu-process".encode("utf-16le")) >= 0,
            "thread_id": thread, "exception_code": f"0x{code:08X}", "exception_flags": flags,
            "exception_address": f"0x{address:016X}", "exception_info": [f"0x{x:X}" for x in exception_info],
            "registers": registers,
            "module": matching[0]["name"] if matching else None,
            "module_offset": f"0x{address-matching[0]['base']:X}" if matching else None,
            "fault_regions": memory_regions,
            "stack_code_pointers": stack_candidates[:30],
            "streams": sorted(streams), "module_count": nmodules}


if __name__ == "__main__":
    reports = ROOT / "runtime/browser-profile/Crashpad/reports"
    result = [parse(path) for path in sorted(reports.glob("*.dmp"), key=lambda p: p.stat().st_mtime)]
    print(json.dumps(result, ensure_ascii=False, indent=2))
