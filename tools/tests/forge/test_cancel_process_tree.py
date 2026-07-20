#!/usr/bin/env python3
"""Abandoning a build must reap the groups a single killpg leaves behind."""
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from arcanum.jobs.processes import ProcessStore, _running, descendants

# worker -> setsid child -> setsid grandchild: three distinct process groups, the
# same shape as build worker -> bwrap sandbox -> author CLI.
INNER = ("import subprocess,time;"
         "subprocess.Popen(['setsid','sleep','300']);time.sleep(300)")
OUTER = (f"import subprocess,time;subprocess.Popen("
         f"['setsid',{sys.executable!r},'-c',{INNER!r}]);time.sleep(300)")


def spawn():
    worker = subprocess.Popen([sys.executable, "-c", OUTER], start_new_session=True,
                              stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.1)
        pids = descendants(worker.pid)
        if len({os.getpgid(pid) for pid in pids if _running(pid)}) >= 3:
            return worker, pids
    raise AssertionError(f"nested session tree never appeared: {descendants(worker.pid)}")


def alive(pids):
    return [pid for pid in pids if _running(pid)]


# Signalling only the worker's own group orphans everything below it.
worker, pids = spawn()
os.killpg(os.getpgid(worker.pid), signal.SIGKILL)
worker.wait(timeout=10)
time.sleep(0.3)
orphans = alive(pids)
assert orphans, "expected a single-group kill to leave survivors"
for pid in orphans:
    ProcessStore.terminate_tree(pid, grace=(0.2, 0.2, 0.0))

# One terminate_tree call reaps the whole tree.
worker, pids = spawn()
assert ProcessStore.terminate_tree(worker.pid, grace=(2.0, 2.0, 0.0))
worker.wait(timeout=10)
assert not alive(pids), f"still alive: {alive(pids)}"

print("forge cancel process tree: OK")
