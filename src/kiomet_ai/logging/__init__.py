from collections import deque
from dataclasses import asdict, is_dataclass
from logging.handlers import RotatingFileHandler
import json
import logging
from pathlib import Path

class DecisionLogger:
    def __init__(self, path: Path, max_bytes=5*1024*1024, backups=5):
        self.recent = deque(maxlen=20)
        self.handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        self.handler.setFormatter(logging.Formatter("%(message)s"))

    def write(self, record):
        # 直接 handle 會由 logging 吞掉磁碟錯誤；改為自行寫入讓控制器安全停止。
        text = json.dumps(record, ensure_ascii=False, default=lambda x: asdict(x) if is_dataclass(x) else str(x))
        event = logging.makeLogRecord({"msg": text, "levelno": logging.INFO, "levelname": "INFO"})
        if self.handler.shouldRollover(event):
            self.handler.doRollover()
        self.handler.stream.write(text + "\n")
        self.handler.stream.flush()
        self.recent.append(record)

    def close(self):
        self.handler.close()
