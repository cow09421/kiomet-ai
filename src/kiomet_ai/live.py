"""只在記憶體保留最新的遊戲分頁畫面；擷取不派發遊戲輸入。"""
from collections import deque
from pathlib import Path
import json
import threading
import time

class LiveView:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()
        self.latest = b""
        self.sequence = 0
        self.captured_at = None
        self.capture_ms = 0.0
        self.high_until = 0.0
        self.times = deque(maxlen=240)
        self.error = None
        self.diagnostics_written = 0

    @property
    def target_fps(self):
        return 4 if time.monotonic() < self.high_until else 1

    def set_high(self, enabled):
        self.high_until = time.monotonic()+60 if enabled else 0.0

    def put(self, image: bytes, elapsed_ms: float):
        if not image.startswith(b"\xff\xd8"):
            raise ValueError("觀戰畫面不是有效的 JPEG 開頭")
        with self.lock:
            self.latest = image
            self.sequence += 1
            self.captured_at = time.time()
            self.capture_ms = elapsed_ms
            self.times.append(time.monotonic())
            self.error = None

    def frame(self):
        with self.lock:
            return self.latest, self.sequence, self.captured_at

    def stats(self):
        now = time.monotonic()
        with self.lock:
            samples = [t for t in self.times if t >= now-10]
            rate = (len(samples)-1)/(samples[-1]-samples[0]) if len(samples)>1 and samples[-1]>samples[0] else 0.0
            return {"sequence":self.sequence,"captured_at":self.captured_at,"capture_ms":round(self.capture_ms,2),
                    "frame_bytes":len(self.latest),"target_fps":self.target_fps,"actual_fps":round(rate,2),
                    "high_seconds_remaining":max(0,round(self.high_until-now)),"error":self.error,
                    "storage":"memory-latest-frame","diagnostics_written":self.diagnostics_written}

    def save_diagnostic(self, reason):
        image, sequence, captured = self.frame()
        if not image:
            return None
        directory = self.root / "runtime/screenshots/diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        # 十個固定槽位，只覆寫本功能建立的固定診斷槽，不累积逐幀檔案。
        slot = self.diagnostics_written % 10
        image_path = directory / f"slot-{slot:02}.jpg"
        image_path.write_bytes(image)
        image_path.with_suffix(".json").write_text(json.dumps({"reason":str(reason),"sequence":sequence,
            "captured_at":captured,"saved_at":time.time()},ensure_ascii=False,indent=2),encoding="utf-8")
        self.diagnostics_written += 1
        return str(image_path.relative_to(self.root))
