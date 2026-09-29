"""Windows 原生程序啟動：明確傳遞獨立桌面，不依賴 subprocess 未支援的欄位。"""
import ctypes
from ctypes import wintypes as W
import subprocess

class StartupInfo(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
                ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
                ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
                ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
                ("wShowWindow", W.WORD), ("cbReserved2", W.WORD), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]

class ProcessInfo(ctypes.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]

class BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", W.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]

class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

class ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

class IsolatedProcess:
    def __init__(self, args, desktop, cwd):
        k = self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, W.BOOL,
                                    W.DWORD, ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
        k.CreateProcessW.restype = W.BOOL
        k.CloseHandle.argtypes = [W.HANDLE]
        k.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
        k.CreateJobObjectW.restype = W.HANDLE
        k.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        k.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
        k.ResumeThread.argtypes = [W.HANDLE]
        k.ResumeThread.restype = W.DWORD
        k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
        self.handle = self.job = None
        info, startup = ProcessInfo(), StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.lpDesktop = desktop
        startup.dwFlags, startup.wShowWindow = 1, 0
        self.job = k.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # 程式結束即清除專用瀏覽器程序樹。
        if not self.job or not k.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
        if not k.CreateProcessW(args[0], command, None, None, False, 0x4, None, str(cwd), ctypes.byref(startup), ctypes.byref(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error
        self.handle, self.pid = info.hProcess, info.dwProcessId
        try:
            if not k.AssignProcessToJobObject(self.job, self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            if k.ResumeThread(info.hThread) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            k.TerminateProcess(self.handle, 1)
            self.close()
            raise
        finally:
            k.CloseHandle(info.hThread)

    def poll(self):
        code = W.DWORD()
        if not self.handle or not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            return 1
        return None if code.value == 259 else code.value

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
