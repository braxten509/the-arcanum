"""Resolve process-visible bind-mount paths to their exact host sources."""
import os
import re


_MOUNT_ESCAPE_RE = re.compile(r"\\([0-7]{3})")


def _mount_value(value):
    return _MOUNT_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 8)), value)


def _mount_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) >= 6:
                    rows.append((fields[2], _mount_value(fields[3]),
                                 _mount_value(fields[4])))
    except OSError:
        pass
    return rows


def _relative_to(path, root):
    path, root = os.path.normpath(path), os.path.normpath(root)
    if path == root:
        return ""
    prefix = root.rstrip(os.sep) + os.sep
    return path[len(prefix):] if path.startswith(prefix) else None


def host_mount_path(pdir, target, proc_root):
    """Translate one process-visible path to the same mounted file on the host."""
    process_matches = [
        (len(mountpoint), device, root, inside)
        for device, root, mountpoint in _mount_rows(os.path.join(pdir, "mountinfo"))
        for inside in (_relative_to(target, mountpoint),)
        if inside is not None
    ]
    if not process_matches:
        return ""
    _length, device, root, inside = max(process_matches)
    filesystem_path = os.path.join(root, inside)
    host_mountinfo = ("/proc/self/mountinfo" if os.path.realpath(proc_root) == "/proc"
                      else os.path.join(proc_root, "self", "mountinfo"))
    host_matches = [
        (len(host_root), host_mountpoint, remainder)
        for host_device, host_root, host_mountpoint in _mount_rows(host_mountinfo)
        for remainder in (_relative_to(filesystem_path, host_root),)
        if host_device == device and remainder is not None
    ]
    if not host_matches:
        return ""
    _length, host_mountpoint, remainder = max(host_matches)
    return os.path.join(host_mountpoint, remainder)
