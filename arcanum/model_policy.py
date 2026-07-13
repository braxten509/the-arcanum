"""Conservative role and effort policy for the Bindery's four authoring hands.

The provider census answers "what is selectable?".  This file answers the harder
question: "what is a realistic choice for this *entire bundled hand*?"  In
particular, Drafter also owns the whole-tome Phase 7 validation pass and Sections
may run unsplit.  A model is therefore not promoted just because it can generate
good prose, solve a coding benchmark, or author one short lesson.

The assessment is intentionally explicit for every live model.  New and rotating
ids fail closed (visible, but not advised) until they are researched here.
"""

ROLES = ("drafter", "writer", "sections", "reviewer")
ALL_ROLES = frozenset(ROLES)


def _entry(roles, basis):
    return {"roles": frozenset(roles), "basis": basis}


# Research snapshot: 2026-07-13.  ``basis`` is returned by /api/models for
# diagnostics and future audits; the compact UI intentionally shows only the
# requested gray state and "(not advised)" suffix.
MODEL_POLICY = {
    # Anthropic. Haiku is explicitly positioned for fast subagents and bounded
    # tasks; the other current models have the long-horizon intelligence needed
    # for every hand.
    "claude-haiku-4-5": _entry(
        ("drafter",),
        "Fast near-frontier subagent model; realistic for validator-backed support work, not a full course arc, unsplit section phase, or independent final audit.",
    ),
    "claude-sonnet-5": _entry(
        ALL_ROLES,
        "Current frontier Sonnet for planning, knowledge work, tool use, and long-running agents.",
    ),
    "claude-opus-4-7": _entry(
        ALL_ROLES,
        "Frontier intelligence for long-horizon and intelligence-sensitive agentic work.",
    ),
    "claude-opus-4-8": _entry(
        ALL_ROLES,
        "Frontier intelligence for complex agentic coding, research, and enterprise knowledge work.",
    ),
    "claude-fable-5": _entry(
        ALL_ROLES,
        "Anthropic's strongest generally available long-running-agent model; capable everywhere but rarely cost-optimal below the top tier.",
    ),

    # Google Antigravity exposes thinking level as part of the model name.  Low
    # is for fewer-step/latency-sensitive work; Medium is Google's general
    # default; whole-tome review retains High only.
    "Gemini 3.5 Flash (Low)": _entry(
        ("drafter",),
        "Low thinking is optimized for fewer-step, latency-sensitive work; keep it on the validator-backed hand.",
    ),
    "Gemini 3.5 Flash (Medium)": _entry(
        ("drafter", "writer", "sections"),
        "Google's recommended default for most complex agentic and writing work; final gap detection still merits High.",
    ),
    "Gemini 3.5 Flash (High)": _entry(
        ALL_ROLES,
        "Sustained frontier Flash with maximum tool use and reasoning for hard long-horizon work.",
    ),
    "Gemini 3.1 Pro (Low)": _entry(
        ("drafter",),
        "Strong base model, but Low explicitly minimizes reasoning depth and is not the realistic setting for the three authorship-critical hands.",
    ),
    "Gemini 3.1 Pro (High)": _entry(
        ALL_ROLES,
        "Advanced reasoning and agentic model at its default/deep thinking level.",
    ),
    "GPT-OSS 120B (Medium)": _entry(
        ("drafter",),
        "Capable tool-using open model near the o4-mini class, but not the conservative floor for general long-form pedagogy or final factual review.",
    ),

    # Installed Codex catalog. Sol and Terra cover the full workflow; Luna is
    # the fast high-volume hand and is not used as the independent final judge.
    "gpt-5.6-sol": _entry(
        ALL_ROLES,
        "Latest frontier agentic model for the hardest coding, research, and real-world workflows.",
    ),
    "gpt-5.6-terra": _entry(
        ALL_ROLES,
        "Strong balanced agentic model with enough depth for authoring and high-effort review.",
    ),
    "gpt-5.6-luna": _entry(
        ("drafter", "writer", "sections"),
        "Fast affordable current-generation agentic model; use a stronger independent reviewer.",
    ),
    "gpt-5.5": _entry(
        ALL_ROLES,
        "Frontier model explicitly positioned for complex coding, research, and real-world work.",
    ),
    "gpt-5.4": _entry(
        ALL_ROLES,
        "Strong full-size reasoning model; high effort is required for the cover-to-cover review hand.",
    ),
    "gpt-5.4-mini": _entry(
        ("drafter",),
        "Small model for simpler coding tasks; usable only on the validator-backed support hand and only at high effort.",
    ),

    # OpenCode Go.  Vendor claims about coding are not enough for Reviewer: only
    # models with strong general reasoning/research evidence receive that role.
    "opencode-go/deepseek-v4-flash": _entry(
        ("drafter",),
        "13B-active economical model; official guidance says it matches Pro on simple agents, not the long-horizon authorship hands.",
    ),
    "opencode-go/deepseek-v4-pro": _entry(
        ALL_ROLES,
        "1M-context flagship with frontier reasoning, broad world knowledge, tool use, and long outputs.",
    ),
    "opencode-go/glm-5.1": _entry(
        ALL_ROLES,
        "Flagship for eight-hour tasks, complex instruction following, research papers, and teaching materials.",
    ),
    "opencode-go/glm-5.2": _entry(
        ALL_ROLES,
        "Improved 1M-context long-horizon flagship with broad reasoning and agentic benchmark strength.",
    ),
    "opencode-go/kimi-k2.6": _entry(
        ALL_ROLES,
        "Versatile thinking model with strong research/search, knowledge, long-horizon, and document-delivery results.",
    ),
    "opencode-go/kimi-k2.7-code": _entry(
        ("drafter",),
        "Coding-focused derivative with strong software-agent evidence but no equally broad pedagogy or final-review evidence.",
    ),
    "opencode-go/mimo-v2.5": _entry(
        ("drafter",),
        "15B-active efficient agent model; not a conservative general course-authoring or reviewer floor.",
    ),
    "opencode-go/mimo-v2.5-pro": _entry(
        ("drafter", "writer", "sections"),
        "42B-active 1M-context Pro model with strong agentic and long-context results; final-review evidence is not broad enough.",
    ),
    "opencode-go/minimax-m2.7": _entry(
        ("drafter", "writer", "sections"),
        "Strong long-form office/document delivery and professional-task model; reserve final factual arbitration for a stronger research model.",
    ),
    "opencode-go/minimax-m3": _entry(
        ALL_ROLES,
        "1M-context frontier agent with long-horizon research reproduction and strong browsing/reasoning evidence.",
    ),
    "opencode-go/qwen3.6-plus": _entry(
        ("drafter", "writer", "sections"),
        "1M-context general content/document and agent model; Max-class reasoning remains the safer reviewer floor.",
    ),
    "opencode-go/qwen3.7-max": _entry(
        ALL_ROLES,
        "Qwen flagship for complex multi-step reasoning and agents, with 1M context.",
    ),
    "opencode-go/qwen3.7-plus": _entry(
        ("drafter", "writer", "sections"),
        "Current 1M-context performance/cost model for content, documents, tools, and productivity workflows; not the flagship reviewer.",
    ),

    # These are limited-time, data-collecting trial endpoints.  Some underlying
    # models are capable, but a complete multi-hour tome must not depend on a
    # promotional endpoint that can disappear or throttle without a durability
    # contract.  They stay visible for non-tome OpenCode use.
    "opencode/big-pickle": _entry(
        (),
        "Undisclosed rotating stealth model on a limited-time free endpoint; capability and durability cannot be audited.",
    ),
    "opencode/deepseek-v4-flash-free": _entry(
        (),
        "Capable underlying Flash model, but this is a limited-time data-collecting endpoint unsuitable for a dependable complete build.",
    ),
    "opencode/mimo-v2.5-free": _entry(
        (),
        "Capable underlying MiMo model, but this is a limited-time data-collecting endpoint unsuitable for a dependable complete build.",
    ),
    "opencode/north-mini-code-free": _entry(
        (),
        "3B-active code-specialist on a limited-time data-collecting endpoint; below the bundled tome-hand floor.",
    ),
    "opencode/nemotron-3-ultra-free": _entry(
        (),
        "Strong underlying frontier model, but OpenCode identifies this endpoint as trial-only and limited-time, without a complete-run durability contract.",
    ),

    # Exact local installations, not generic family claims.  The two Qwen3-32B
    # builds retain a narrow Drafter role; their configured 40,960-token context
    # and the older/specialized smaller models are not a safe authorship floor.
    "ollama/qwen3:32b-q8_0": _entry(
        ("drafter",),
        "Full 32B reasoning/tool model at Q8, but locally configured to 40,960 context; keep it on validator-backed support work.",
    ),
    "ollama/qwen3:32b": _entry(
        ("drafter",),
        "Full 32B reasoning/tool model at Q4, but locally configured to 40,960 context; keep it on validator-backed support work.",
    ),
    "ollama/qwen3-coder:30b": _entry(
        (),
        "Only 3B active parameters and code-specialized; not a dependable general pedagogy or whole-tome validation hand.",
    ),
    "ollama/devstral:latest": _entry(
        (),
        "Older 24B Q4 research-preview code specialist, not a general long-form course-authoring model.",
    ),
    "ollama/qwen2.5:14b": _entry(
        (),
        "Older 14B Q4 model with a locally configured 32K context; below the complete-tome hand floor.",
    ),
    "ollama/llama3.1:8b": _entry(
        (),
        "8B Q4 general model; useful locally, but too small for any bundled complete-tome hand.",
    ),
    "ollama/llama3.2:3b": _entry(
        (),
        "3B Q4 edge model intended for summarization and rewriting, not autonomous tome production.",
    ),
}

MODEL_ROLES = {model: policy["roles"] for model, policy in MODEL_POLICY.items()}


# Supported levels come from the live provider rows.  These profiles deliberately
# omit valid-but-unwise settings: low effort is gray for complex bundled phases;
# max/ultra is gray where the vendor describes it as unconstrained or eval-only
# spend.  A user still sees every supported level, but can select only these.
EFFORT_PROFILES = {
    "claude-fable-5": {
        "drafter": ("medium", "high"),
        "writer": ("high", "xhigh"),
        "sections": ("high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "claude-opus-4-8": {
        "drafter": ("high",),
        "writer": ("high", "xhigh"),
        "sections": ("high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "claude-opus-4-7": {
        "drafter": ("high",),
        "writer": ("high", "xhigh"),
        "sections": ("high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "claude-sonnet-5": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high", "xhigh"),
        "sections": ("medium", "high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.6-sol": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high", "xhigh"),
        "sections": ("medium", "high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.6-terra": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.6-luna": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
    },
    "gpt-5.5": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high", "xhigh"),
        "sections": ("medium", "high", "xhigh"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.4": {
        "drafter": ("medium", "high"),
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.4-mini": {"drafter": ("high", "xhigh")},
    "opencode-go/deepseek-v4-flash": {"drafter": ("high",)},
    "opencode-go/deepseek-v4-pro": {role: ("high",) for role in ROLES},
    "opencode-go/glm-5.2": {role: ("high",) for role in ROLES},
}


def model_guidance(model_id, effort_levels=()):
    """Return JSON-safe role suitability and recommended effort subsets."""
    policy = MODEL_POLICY.get(model_id)
    roles = policy["roles"] if policy else frozenset()
    supported = tuple(effort_levels or ())
    profile = EFFORT_PROFILES.get(model_id, {})
    return {
        "known": policy is not None,
        "basis": policy["basis"] if policy else "Unassessed model; fail closed until researched.",
        "advised": {role: role in roles for role in ROLES},
        "efforts": {
            role: [level for level in supported if level in profile.get(role, ())]
            if role in roles else []
            for role in ROLES
        },
    }


def guided_row(row):
    """Append guidance to a [id, label, tag, efforts] Bindery model row."""
    base = list(row[:4])
    while len(base) < 4:
        base.append([] if len(base) == 3 else "")
    base[3] = list(base[3] or [])
    return base + [model_guidance(base[0], base[3])]
