"""Build harness configuration and preset resolution."""
import os
import sys
import tomllib

from . import CONFIG


def load_config(preset=None):
    if not os.path.exists(CONFIG):
        sys.exit(f"missing {CONFIG} — see the sample in the repo.")
    with open(CONFIG, "rb") as handle:
        config = tomllib.load(handle)
    preset = preset or config.get("preset")
    if preset:
        selected = (config.get("presets") or {}).get(preset)
        if not selected:
            sys.exit(f"harness.toml: preset {preset!r} requested but no "
                     f"[presets.{preset}] table")
        config["default"] = selected.get("default", config.get("default"))
        config["phases"] = dict(selected.get("phases") or {})
        print(f"  · preset {preset!r}: default={config['default']}, "
              f"phase overrides={config['phases'] or '(none)'}")
    return config
