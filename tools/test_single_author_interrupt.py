#!/usr/bin/env python3
"""An interrupted turn must not leave a nested CLI process alive."""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.tool_trace import _descendants  # noqa: E402
from tools.buildlib.single_author import AuthorSession  # noqa: E402


session = AuthorSession("interrupt-proof", "codex-cli", "test", "", "", "external")
session.child = subprocess.Popen(
    [sys.executable, "-c",
     "import subprocess,time; subprocess.Popen(['setsid','sleep','60'], "
     "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(60)"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
try:
    time.sleep(.25)
    descendants = _descendants(session.child.pid)
    assert len(descendants) >= 2, descendants
    session.interrupt()
    time.sleep(.15)
    assert not [pid for pid in descendants if os.path.exists(f"/proc/{pid}")]
finally:
    try:
        os.killpg(os.getpgid(session.child.pid), 9)
    except OSError:
        pass

print("single-author nested interrupt: OK")
