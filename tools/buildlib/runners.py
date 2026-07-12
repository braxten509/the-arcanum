"""Runner templates and selection: KIND:MODEL[@EFFORT] specs, harness.toml resolution,
fallback chains, and the blocking human runner-pick pause (TTY or Bindery handshake)."""
import json
import os
import sys
import time

from . import BUILD_DIR

def _codex_no_mcp():
    """Disable every personal MCP server by name (mirrors arcanum.config.codex_no_mcp_args —
    `-c mcp_servers={}` merges instead of clearing; codex-desktop's node_repl hangs headless)."""
    import tomllib
    try:
        with open(os.path.expanduser("~/.codex/config.toml"), "rb") as f:
            servers = tomllib.load(f).get("mcp_servers", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [a for n in servers for a in ("-c", f"mcp_servers.{n}.enabled=false")]


# Ready-made runner templates the web bindery's pickers map onto (--runner overrides).
# A build runner must wield tools and edit files, so only the agentic login CLIs
# qualify — ollama prints text; it cannot hold the quill.
CLI_RUNNERS = {
    "claude-cli": {"cmd": ["claude", "-p", "--permission-mode", "auto", "--model", "{model}"], "input": "arg",
                   "efforts": ("low", "medium", "high", "xhigh", "max"),
                   "effortArgs": ["--effort", "{effort}"]},
    # agy has no effort switch — its Gemini model names carry it (Low/Medium/High variants).
    # --print is a STRING flag whose value IS the prompt — it must come last so the appended
    # prompt lands as its value. A bare --print swallows the NEXT FLAG as the prompt (Gemini
    # then chats about that flag instead of working) and ignores stdin entirely.
    # --print-timeout defaults to 5m, far under a real phase.
    "antigravity-cli": {"cmd": ["agy", "--dangerously-skip-permissions", "--print-timeout", "4h",
                                "--model", "{model}", "--print"], "input": "arg"},
    # npm codex preferred: the Arch openai-codex package omits codex-code-mode-host (gpt-5.6 needs it)
    "codex-cli": {"cmd": [os.path.expanduser("~/.local/bin/codex") if os.access(os.path.expanduser("~/.local/bin/codex"), os.X_OK) else "codex",
                          "--search", "exec", "--skip-git-repo-check", "-s", "workspace-write", *_codex_no_mcp(), "-m", "{model}", "-"], "input": "stdin",
                  "efforts": ("minimal", "low", "medium", "high", "xhigh"),
                  "effortArgs": ["-c", "model_reasoning_effort={effort}"]},
    # opencode drives OpenCode Go / free models (opencode-go/*, opencode/*) AND local models
    # (ollama/* run THROUGH the opencode agent, which wields the tools the raw model can't).
    # --auto approves edits/bash so it can build headlessly. Split-section workers additionally
    # run inside the harness's read-only-repo mount sandbox. --variant is the effort knob — only some
    # models honour a given variant, so the picker offers it for OpenCode CLI (not Local) and
    # leaving it DEFAULT sends none.
    "opencode-cli": {"cmd": ["opencode", "run", "--auto", "-m", "{model}"], "input": "arg",
                     "efforts": ("none", "minimal", "low", "medium", "high", "max"),
                     "effortArgs": ["--variant", "{effort}"]},
}


def _spec_to_runner(spec, ctx):
    """'KIND:MODEL[@EFFORT]' → (display, cmd, input). `ctx` names the flag for errors.
    An optional @effort suffix sets reasoning effort on the CLIs that take one."""
    kind, _, model = spec.partition(":")
    model, _, effort = model.partition("@")
    t = CLI_RUNNERS.get(kind)
    if not (t and model):
        sys.exit(f"{ctx} wants <{'|'.join(CLI_RUNNERS)}>:<model>[@effort], got {spec!r}")
    cmd = [a.replace("{model}", model) for a in t["cmd"]]
    if effort:
        allowed = t.get("efforts", ())
        if effort not in allowed:
            sys.exit(f"{ctx}: {kind} takes no effort {effort!r}"
                     + (f" (allowed: {', '.join(allowed)})" if allowed
                        else " — its effort is chosen by the model name"))
        extra = [a.replace("{effort}", effort) for a in t["effortArgs"]]
        pos = len(cmd) - 1 if cmd[-1] == "-" else len(cmd)  # codex: before the stdin marker
        cmd[pos:pos] = extra
    return (f"{kind} {model}" + (f" @{effort}" if effort else ""), cmd, t["input"])


def parse_runner_flags(flags):
    """--runner default=claude-cli:claude-opus-4-8@high / --runner 8=codex-cli:gpt-5.5 →
    {key: (display, cmd, input)}. These beat harness.toml; a phase key beats default."""
    out = {}
    for f in flags or []:
        key, _, spec = f.partition("=")
        if "=" not in f or not key:
            sys.exit(f"--runner wants <default|phase-number>=<{'|'.join(CLI_RUNNERS)}>:<model>[@effort], got {f!r}")
        out[key] = _spec_to_runner(spec, "--runner")
    return out


def parse_fallbacks(flags):
    """--fallback opencode-cli:opencode-go/deepseek-v4-flash (repeatable) → ordered
    [(display, cmd, input), ...]. Tried in order when a phase's primary worker DIES —
    crash, exhausted quota, or hang — each resuming from the tome already on disk."""
    return [_spec_to_runner(s, "--fallback") for s in (flags or [])]


def request_runner(build_id, phase_num, dead_name, reason, interactive, report=None):
    """Ask a HUMAN what to do next on a stuck phase and BLOCK until they answer. Two callers:
    a worker DIED with no --fallback left, or a phase EXHAUSTED its gate retries (pass the failing
    validator `report`, which flips this to the gate-failure pause — the Bindery box then also
    offers 'N more retries'). A TTY run prompts on the terminal; a server-launched run hands off
    via .tome-build/<id>.runner-{request,reply}.json, which the Bindery UI bridges (it polls the
    request via /api/buildtome/status and writes the reply via /api/buildtome/runner). Whatever
    they pick resumes the SAME phase from the tome already on disk. Returns
    (runner_or_None, extra_retries): a runner to switch to (None = keep the current model, or give
    up), and how many MORE gate retries to grant (0 for a death)."""
    gate = report is not None
    if interactive:
        if gate:
            print(f"\n  ⚠ phase {phase_num} still fails its gates ({reason}).")
            spec = input("  switch runner KIND:MODEL[@EFFORT] (blank = keep current model): ").strip()
            more = input("  how many MORE retries? (blank/0 = give up): ").strip()
            runner = _spec_to_runner(spec, "runner picker") if spec else None
            return runner, (int(more) if more.isdigit() else 0)
        print(f"\n  ⚠ runner {dead_name} died on phase {phase_num} ({reason}).")
        spec = input("  new runner KIND:MODEL[@EFFORT] (blank = give up): ").strip()
        return (_spec_to_runner(spec, "runner picker") if spec else None), 0
    req = os.path.join(BUILD_DIR, f"{build_id}.runner-request.json")
    reply = os.path.join(BUILD_DIR, f"{build_id}.runner-reply.json")
    with open(req, "w", encoding="utf-8") as f:
        json.dump({"phase": phase_num, "dead": dead_name, "reason": reason,
                   "gate": gate, "report": report or ""}, f)
    print(f"  ⏸ phase {phase_num} " + (f"failed its gates ({reason})" if gate
          else f"lost runner {dead_name} ({reason})") + " — waiting for the Bindery…")
    try:
        while not os.path.exists(reply):
            time.sleep(2)
        with open(reply, encoding="utf-8") as f:
            choice = json.load(f)
    finally:
        for p in (req, reply):
            try:
                os.remove(p)
            except OSError:
                pass
    kind, model, effort = (str(choice.get(k) or "") for k in ("kind", "model", "effort"))
    try:
        extra = max(0, int(choice.get("retries") or 0))
    except (TypeError, ValueError):
        extra = 0
    runner = (_spec_to_runner(f"{kind}:{model}" + (f"@{effort}" if effort else ""), "runner picker")
              if kind and model else None)  # empty runner: keep current model (or, for a death, give up)
    return runner, extra


def runner_for(cfg, phase_num, overrides=None):
    ov = (overrides or {}).get(str(phase_num)) or (overrides or {}).get("default")
    if ov:
        return ov
    name = cfg.get("phases", {}).get(str(phase_num)) or cfg.get("default")
    if not name:  # no browser pick, no --runner, and harness.toml carries no default
        sys.exit(f"no runner for phase {phase_num}: pick a model in the browser, pass "
                 f"--runner {phase_num}=<kind>:<model>, or set a `default` in harness.toml.")
    try:
        r = cfg["runners"][name]
    except KeyError:
        sys.exit(f"harness.toml: no [runners.{name}] defined (phase {phase_num}).")
    return name, list(r["cmd"]), r.get("input", "stdin")


def default_runner(cfg, overrides):
    """The 'default' runner (what a phase with no phase-specific override uses) — reused as
    the implicit fallback when --fallback isn't given. None when harness.toml sets no default
    (the browser-pick workflow), so there's simply nothing to fall back to unattended."""
    ov = (overrides or {}).get("default")
    if ov:
        return ov
    name = cfg.get("default")
    if not name or name not in (cfg.get("runners") or {}):
        return None
    r = cfg["runners"][name]
    return name, list(r["cmd"]), r.get("input", "stdin")


def _implicit_fallback(cfg, overrides, primary):
    """No explicit --fallback: fall back to the 'default' runner, unless there is none (the
    browser-pick workflow) or this phase already IS the default (switching changes nothing)."""
    d = default_runner(cfg, overrides)
    return [] if (d is None or d[1] == primary[1]) else [d]
