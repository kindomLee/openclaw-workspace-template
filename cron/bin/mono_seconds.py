#!/usr/bin/env python3
"""Print system-wide monotonic seconds that exclude host sleep time.

Used by runner.sh to measure real job execution time without host sleep
inflating the number.

CPython's ``time.monotonic()`` on macOS subtracts a per-process baseline
from ``mach_absolute_time()``, so two fresh ``python3 -c 'print(time.monotonic())'``
invocations both return a value near 0 and cannot be compared across processes.
We therefore call ``clock_gettime(CLOCK_UPTIME_RAW)`` directly via ctypes.

Clock selection:

- **macOS (Darwin)**: ``CLOCK_UPTIME_RAW`` (id ``8``) — monotonic, does NOT
  advance while the system is asleep. Darwin's ``CLOCK_MONOTONIC`` is the
  opposite: it *does* advance during sleep, which is the bug we are
  avoiding.
- **Linux**: ``CLOCK_MONOTONIC`` (id ``1``) — already excludes suspend time
  from the caller's perspective in typical laptop configurations. We do
  not use ``CLOCK_BOOTTIME`` here because "active execution time" is what
  the runner wants, not elapsed wall time since boot.
"""
import ctypes
import ctypes.util
import platform
import sys


class _Timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]


def main() -> int:
    libc_path = ctypes.util.find_library("c")
    if not libc_path:
        print("0")
        return 1
    libc = ctypes.CDLL(libc_path, use_errno=True)
    libc.clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(_Timespec)]
    libc.clock_gettime.restype = ctypes.c_int

    if platform.system() == "Darwin":
        clock_id = 8  # CLOCK_UPTIME_RAW — monotonic, excludes sleep
    else:
        clock_id = 1  # CLOCK_MONOTONIC — Linux

    ts = _Timespec()
    if libc.clock_gettime(clock_id, ctypes.byref(ts)) != 0:
        errno = ctypes.get_errno()
        print(f"clock_gettime failed: errno={errno}", file=sys.stderr)
        print("0")
        return 1

    print(ts.tv_sec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
