import asyncio

class ActionGate:
    """同一事件迴圈內，停止與送出操作共用鎖；停止是不可逆的終止狀態。

    執行授權（authorized）獨立於運行狀態：dispatch_exec 要求
    RUNNING＋已授權＋單動作鎖三者同時成立。授權預設關閉，
    不從舊檔／舊日誌／環境殘留自動恢復。
    """
    def __init__(self):
        self.lock = asyncio.Lock()
        self.state = "PAUSED"
        self.stop_event = asyncio.Event()
        self.authorized = False
        self.authorization_provenance = None
        self.authorization_granted_at = None
        self._exec_lock = asyncio.Lock()

    async def command(self, command: str):
        async with self.lock:
            if self.state == "STOPPED":
                return self.state
            if command == "stop":
                self.state = "STOPPED"
                self.stop_event.set()
            elif command == "pause":
                self.state = "PAUSED"
            elif command == "resume":
                if self.state != "ERROR":
                    self.state = "RUNNING"
            elif command == "error":
                self.state = "ERROR"
            elif command == "recovered":
                # 復原成功後的受控離開 ERROR：進 PAUSED（不自動恢復派送，
                # 需顯式 resume＋授權）。STOPPED 不可逆，維持不動。
                if self.state != "STOPPED":
                    self.state = "PAUSED"
            else:
                raise ValueError("未知控制命令")
            return self.state

    def set_authorized(self, enabled: bool, provenance=None):
        """執行授權開關。只有顯式呼叫能開啟（啟動旗標＝當次授權鏈）。"""
        import time
        self.authorized = bool(enabled)
        if enabled:
            self.authorization_provenance = provenance
            self.authorization_granted_at = time.time()
        else:
            self.authorization_provenance = None
            self.authorization_granted_at = None
        return self.authorized

    async def dispatch_exec(self, operation):
        """單動作派送：RUNNING＋已授權＋同時只允許一個執行中動作。"""
        if self.state != "RUNNING" or not self.authorized:
            return None
        async with self._exec_lock:
            if self.state != "RUNNING" or not self.authorized:
                return None
            return await operation()

    async def dispatch(self, operation):
        async with self.lock:
            if self.state != "RUNNING":
                return None
            return await operation()
