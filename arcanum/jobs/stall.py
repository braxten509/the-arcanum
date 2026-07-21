"""Detect an AI CLI that has stopped doing anything at all.

A slow provider and a wedged process look identical from the outside if you only watch
stdout: a model can think for 20 seconds before its first token, and a shell tool can
run for a minute without the CLI printing a byte.  Both of those are *busy* underneath —
the tree burns CPU, or it holds an established connection to the provider.  A wedged CLI
holds neither, which is what makes this a state test rather than a timeout.

Measured against this repo's own opencode runs: a healthy turn showed +14..+50 CPU ticks
per 2s and 2 established sockets straight through a 19-second silent window, while a
process that had taken a streaming error sat at 0 ticks and 0 sockets indefinitely.
"""
from __future__ import annotations

import os
import time

from .processes import descendants


def tree_ticks(pid: int) -> int:
    """Return total user+system CPU ticks consumed by a process and its descendants."""
    total = 0
    for value in descendants(pid):
        try:
            with open(f"/proc/{value}/stat", encoding="utf-8") as handle:
                fields = handle.read().rpartition(")")[2].split()
            total += int(fields[11]) + int(fields[12])
        except (OSError, IndexError, ValueError):
            continue
    return total


def _socket_inodes(pid: int) -> set[str]:
    inodes: set[str] = set()
    for value in descendants(pid):
        try:
            entries = os.listdir(f"/proc/{value}/fd")
        except OSError:
            continue
        for entry in entries:
            try:
                link = os.readlink(f"/proc/{value}/fd/{entry}")
            except OSError:
                continue
            if link.startswith("socket:["):
                inodes.add(link[8:-1])
    return inodes


def established(pid: int) -> int:
    """Count ESTABLISHED TCP connections owned anywhere in a process tree."""
    inodes = _socket_inodes(pid)
    if not inodes:
        return 0
    count = 0
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, encoding="utf-8") as handle:
                rows = handle.readlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            # state 01 is ESTABLISHED; field 9 is the socket inode.
            if len(fields) > 9 and fields[3] == "01" and fields[9] in inodes:
                count += 1
    return count


class StallWatch:
    """Report when a process tree has been provably idle for ``seconds``.

    Idle means all three of: no CPU consumed, no established connection, and no output
    delivered since the last check.  Any one of those resets the clock.
    """

    def __init__(self, pid: int, seconds: float = 10.0):
        self.pid = int(pid)
        self.seconds = float(seconds)
        self._ticks: int | None = None
        self._since = time.monotonic()
        # ponytail: /proc is the only source here, so a non-Linux host simply never
        # reports a stall rather than growing a second implementation.
        self._usable = os.path.isdir("/proc/self")

    def poke(self) -> None:
        """Record that the process produced output; it is demonstrably alive."""
        self._since = time.monotonic()

    def idle_for(self) -> float:
        """Seconds the tree has been idle, refreshing the CPU and socket samples."""
        if not self._usable:
            return 0.0
        ticks = tree_ticks(self.pid)
        moved = ticks != self._ticks
        self._ticks = ticks
        if moved or established(self.pid):
            self._since = time.monotonic()
            return 0.0
        return time.monotonic() - self._since

    def wedged(self) -> bool:
        """True once the tree has shown no CPU, no connection, and no output."""
        return self.idle_for() >= self.seconds


class StalledProcess(RuntimeError):
    """An AI CLI stopped computing and stopped talking to its provider."""

    def __init__(self, seconds: float, output: str = ""):
        super().__init__(f"AI process went idle for {seconds:.0f}s "
                         "with no CPU and no provider connection")
        self.output = output


def run_watched(command, *, cwd=None, stdin_text=None, seconds=10.0, timeout=900.0,
                on_tick=None):
    """Run a CLI, killing it once its tree goes provably idle.

    Returns ``(returncode, output, stalled)``.  A CLI that stalls *after* producing its
    answer is common enough to matter: this repo's opencode build hangs on completion
    instead of exiting, so the caller gets the output and the flag, not an exception.

    ``on_tick(cpu_percent, output_so_far)`` runs about once a second for callers that
    report progress.  It is advisory: a raising callback must never kill the run it is
    only describing, so its exceptions are swallowed.
    """
    import subprocess
    import threading

    process = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)
    chunks: list[str] = []
    watch = StallWatch(process.pid, seconds)

    def drain():
        assert process.stdout is not None
        for line in process.stdout:
            chunks.append(line)
            watch.poke()

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    if stdin_text is not None and process.stdin:
        try:
            process.stdin.write(stdin_text)
        finally:
            process.stdin.close()

    deadline = time.monotonic() + float(timeout)
    stalled = False
    ticks, sampled_at = tree_ticks(process.pid), time.monotonic()
    hertz = os.sysconf("SC_CLK_TCK") or 100
    while process.poll() is None:
        if watch.wedged():
            stalled = True
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(1.0)
        if on_tick is not None:
            now, moved = time.monotonic(), tree_ticks(process.pid)
            span = now - sampled_at
            cpu = (moved - ticks) / hertz / span * 100 if span > 0 else 0.0
            ticks, sampled_at = moved, now
            try:
                on_tick(cpu, "".join(chunks))
            except Exception:
                pass
    if process.poll() is None:
        from .processes import ProcessStore
        ProcessStore.terminate_tree(process.pid)
    reader.join(timeout=5.0)
    return process.poll(), "".join(chunks), stalled


def demo() -> None:
    """Self-check: a busy tree is never wedged, an idle one becomes wedged."""
    import subprocess

    busy = subprocess.Popen(["sh", "-c", "while :; do :; done"])
    try:
        watch = StallWatch(busy.pid, seconds=0.5)
        watch.idle_for()
        time.sleep(1.0)
        assert not watch.wedged(), "a CPU-burning tree must never look wedged"
    finally:
        busy.kill()
        busy.wait()

    idle = subprocess.Popen(["sleep", "30"])
    try:
        watch = StallWatch(idle.pid, seconds=0.5)
        watch.idle_for()
        time.sleep(1.0)
        assert watch.wedged(), "an idle tree with no connection must look wedged"
    finally:
        idle.kill()
        idle.wait()

    # A CLI that prints its answer and then refuses to exit is the exact shape of the
    # opencode hang this was written for: keep the output, report the stall.
    rc, output, stalled = run_watched(
        ["sh", "-c", "echo done; sleep 30"], seconds=2.0)
    assert stalled, "a hang after output must be reported as a stall"
    assert output.strip() == "done", output
    assert rc != 0, rc

    rc, output, stalled = run_watched(["sh", "-c", "echo quick"], seconds=5.0)
    assert (rc, output.strip(), stalled) == (0, "quick", False), (rc, output, stalled)

    # on_tick reports live CPU and the output so far, and a raising callback must not
    # take the run down with it: it only describes work it does not own.
    # The burner must not fork per iteration: ticks of a reaped child land in cutime,
    # which tree_ticks does not read, so a `date`-driven loop would look idle.
    ticks = []
    rc, output, _ = run_watched(
        ["sh", "-c", "echo one; timeout 3 sh -c 'while :; do :; done'; exit 0"],
        seconds=30.0, on_tick=lambda cpu, text: ticks.append((cpu, text)))
    assert rc == 0 and ticks, (rc, ticks)
    assert max(cpu for cpu, _ in ticks) > 50, ticks
    assert ticks[-1][1].strip() == "one", ticks[-1]

    def explode(cpu, text):
        raise RuntimeError("an advisory callback must never kill the run")

    rc, output, _ = run_watched(
        ["sh", "-c", "sleep 2; echo survived"], seconds=30.0, on_tick=explode)
    assert (rc, output.strip()) == (0, "survived"), (rc, output)

    print("stall watch: OK")


if __name__ == "__main__":
    demo()
