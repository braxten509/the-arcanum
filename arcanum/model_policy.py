"""Conservative role and effort policy for the Bindery's four authoring hands.

The provider census answers "what is selectable?".  This file answers the harder
question: "what is a realistic, cost-justified choice for this *entire bundled
hand*?"  In particular, Drafter also owns the whole-tome Phase 7 validation pass
and Sections may run unsplit.  A model is therefore not promoted just because it
can generate good prose, solve a coding benchmark, or author one short lesson;
nor is a premium model promoted when a materially cheaper model clears the same
hand's bar.

The assessment is intentionally explicit for every live model.  New and rotating
ids fail closed (visible, but insufficient) until they are researched here.
"""

ROLES = ("drafter", "writer", "sections", "reviewer")


def _entry(roles, basis):
    return {"roles": frozenset(roles), "basis": basis}


# Research snapshot: 2026-07-13.  ``basis`` is returned by /api/models for
# diagnostics and future audits; the compact UI shows power for selectable
# choices and the concise "(insufficient)" or "(wasteful)" exclusion reason.
MODEL_POLICY = {
    # Anthropic.  The combined capability + cost bar produces a clean ladder:
    # Haiku for checked support, Sonnet for bulk authorship, Opus for the arc or
    # final audit, and Fable only where its 2x-Opus price can plausibly pay back.
    "claude-haiku-4-5": _entry(
        ("drafter",),
        "Fast near-frontier subagent model; realistic for validator-backed support work, not a full course arc, unsplit section phase, or independent final audit.",
    ),
    "claude-sonnet-5": _entry(
        ("writer", "sections", "reviewer"),
        "Current frontier Sonnet is the cost-effective Claude author; Haiku or Luna already clears the lower-cost Drafter hand.",
    ),
    "claude-opus-4-7": _entry(
        (),
        "Still capable, but it has the same $5/$25 per-MTok base price as the newer Opus 4.8 and its fast mode is being retired; every tome hand has a better-value successor.",
    ),
    "claude-opus-4-8": _entry(
        ("writer", "reviewer"),
        "At $5/$25 per MTok, Opus is justified for the course arc or independent final audit, not the checked Drafter or high-output Sections hand.",
    ),
    "claude-fable-5": _entry(
        ("reviewer",),
        "Anthropic's strongest widely released model costs $10/$50 per MTok—twice Opus 4.8—so only the accuracy-first final Reviewer can justify it.",
    ),

    # Google Antigravity exposes thinking level as part of the model name.  Low
    # is for fewer-step/latency-sensitive work; Medium is Google's general
    # default; High is still economical enough for every judgment-heavy hand.
    "Gemini 3.5 Flash (Low)": _entry(
        ("drafter",),
        "Low thinking is optimized for fewer-step, latency-sensitive work; keep it on the validator-backed hand.",
    ),
    "Gemini 3.5 Flash (Medium)": _entry(
        ("writer", "sections"),
        "Google's recommended default for most complex agentic and writing work; Low is the more economical Drafter and final gap detection merits High.",
    ),
    "Gemini 3.5 Flash (High)": _entry(
        ("writer", "sections", "reviewer"),
        "Frontier Flash at maximum reasoning is justified for course architecture, the largest authorship phase, or independent review; it remains cheaper than the premium Writer alternatives.",
    ),
    "Gemini 3.1 Pro (Low)": _entry(
        (),
        "Low suppresses the reasoning that would justify paying the Pro premium, while Flash Low is the cheaper Drafter; this variant has no cost-effective tome hand.",
    ),
    "Gemini 3.1 Pro (High)": _entry(
        ("writer", "reviewer"),
        "At $2/$12 per MTok, Pro High is a defensible quality-first course architect or independent reviewer; Flash remains the better bulk-output value.",
    ),
    "GPT-OSS 120B (Medium)": _entry(
        ("drafter",),
        "Capable tool-using open model near the o4-mini class, but not the conservative floor for general long-form pedagogy or final factual review.",
    ),

    # Installed Codex catalog and current credit card.  Luna covers efficient
    # volume, Terra the authorship core, and Sol only the two highest-judgment
    # hands.  GPT-5.5 and 5.4 are same-price predecessors to Sol and Terra.
    "gpt-5.6-sol": _entry(
        ("writer", "reviewer"),
        "Latest frontier model at 125/12.5/750 Codex credits per MTok; justified for the course arc or final audit, not support or bulk prose.",
    ),
    "gpt-5.6-terra": _entry(
        ("writer", "sections", "reviewer"),
        "Balanced model at half Sol's credit rate; appropriate for authorship and review, while Luna already clears the Drafter hand.",
    ),
    "gpt-5.6-luna": _entry(
        ("drafter", "writer", "sections"),
        "Fast affordable current-generation agentic model; use a stronger independent reviewer.",
    ),
    "gpt-5.5": _entry(
        (),
        "Same 125/12.5/750 Codex credit rate as newer GPT-5.6 Sol; current guidance says 5.6 improves quality and efficiency, so 5.5 is dominated here.",
    ),
    "gpt-5.4": _entry(
        (),
        "Same 62.5/6.25/375 Codex credit rate as newer GPT-5.6 Terra; the current balanced successor is the cost-justified choice.",
    ),
    "gpt-5.4-mini": _entry(
        ("drafter",),
        "Small model for simpler coding tasks; usable only on the validator-backed support hand and only at high effort.",
    ),

    # OpenCode Go.  The published per-token rates and request allowances make
    # same-price predecessors and flagship-overkill visible, not hypothetical.
    "opencode-go/deepseek-v4-flash": _entry(
        ("drafter",),
        "13B-active economical model; official guidance says it matches Pro on simple agents, not the long-horizon authorship hands.",
    ),
    "opencode-go/deepseek-v4-pro": _entry(
        ("writer", "sections", "reviewer"),
        "1M-context flagship with broad reasoning and a $1.74/$3.48 rate; its quality is useful for authorship/review, but Flash is about 12x cheaper for Drafter.",
    ),
    "opencode-go/glm-5.1": _entry(
        (),
        "Capable long-horizon model, but it has the same $1.40/$4.40 price and lower current capability than GLM-5.2, so it is a dominated tome choice.",
    ),
    "opencode-go/glm-5.2": _entry(
        ("writer", "reviewer"),
        "Improved long-horizon flagship at $1.40/$4.40; reserve it for planning or review rather than checked support or the bulk-output Sections phase.",
    ),
    "opencode-go/kimi-k2.6": _entry(
        ("writer", "reviewer"),
        "Strong research and long-horizon model at $0.95/$4.00; useful for planning/review, but cheaper proven models cover support and bulk section output.",
    ),
    "opencode-go/kimi-k2.7-code": _entry(
        (),
        "Coding-focused derivative at $0.95/$4.00; too narrow for the authorship hands and far more expensive than Flash/MiMo for Drafter.",
    ),
    "opencode-go/mimo-v2.5": _entry(
        ("drafter",),
        "15B-active efficient agent model; not a conservative general course-authoring or reviewer floor.",
    ),
    "opencode-go/mimo-v2.5-pro": _entry(
        (),
        "Capable 42B-active model, but at the same $1.74/$3.48 rate as broader DeepSeek V4 Pro it is not the cost-justified choice for any bundled hand.",
    ),
    "opencode-go/minimax-m2.7": _entry(
        (),
        "Strong document model, but newer MiniMax M3 has the same $0.30/$1.20 rate and broader research/review evidence, making M2.7 dominated.",
    ),
    "opencode-go/minimax-m3": _entry(
        ("writer", "sections", "reviewer"),
        "At $0.30/$1.20, M3 is a cost-effective author/reviewer; $0.14/$0.28 Flash or MiMo remains the sensible Drafter.",
    ),
    "opencode-go/qwen3.6-plus": _entry(
        (),
        "Older Plus costs $0.50/$3.00 at <=256K while Qwen3.7 Plus is newer and $0.40/$1.60, so 3.6 is dominated for tome work.",
    ),
    "opencode-go/qwen3.7-max": _entry(
        ("writer", "reviewer"),
        "Qwen's $2.50/$7.50 flagship is justified for the high-leverage course arc or independent final arbitration; Plus is the economical bulk author.",
    ),
    "opencode-go/qwen3.7-plus": _entry(
        ("writer", "sections"),
        "Current $0.40/$1.60 performance/cost model for content and documents; cheaper Flash/MiMo cover Drafter and Max-class models cover review.",
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

# A compact, ordinal estimate of raw tome-authoring capability, independent of
# price and role fit.  It is intentionally not a synthetic benchmark average:
# 10 = strongest current frontier; 9 = frontier authors/reviewers; 8 = strong
# complete authors with some tradeoffs; 7 = dependable checked/support agents;
# 6 and below = constrained local, older, or narrow specialists.  The Custom UI
# shows this only when the model is advised for the selected hand.
MODEL_POWER = {
    "claude-haiku-4-5": 7,
    "claude-sonnet-5": 9,
    "claude-opus-4-7": 9,
    "claude-opus-4-8": 9,
    "claude-fable-5": 10,
    "Gemini 3.5 Flash (Low)": 7,
    "Gemini 3.5 Flash (Medium)": 8,
    "Gemini 3.5 Flash (High)": 9,
    "Gemini 3.1 Pro (Low)": 8,
    "Gemini 3.1 Pro (High)": 9,
    "GPT-OSS 120B (Medium)": 7,
    "gpt-5.6-sol": 10,
    "gpt-5.6-terra": 9,
    "gpt-5.6-luna": 8,
    "gpt-5.5": 9,
    "gpt-5.4": 9,
    "gpt-5.4-mini": 7,
    "opencode-go/deepseek-v4-flash": 7,
    "opencode-go/deepseek-v4-pro": 8,
    "opencode-go/glm-5.1": 8,
    "opencode-go/glm-5.2": 9,
    "opencode-go/kimi-k2.6": 8,
    "opencode-go/kimi-k2.7-code": 8,
    "opencode-go/mimo-v2.5": 7,
    "opencode-go/mimo-v2.5-pro": 8,
    "opencode-go/minimax-m2.7": 8,
    "opencode-go/minimax-m3": 8,
    "opencode-go/qwen3.6-plus": 8,
    "opencode-go/qwen3.7-max": 9,
    "opencode-go/qwen3.7-plus": 8,
    "opencode/big-pickle": None,
    "opencode/deepseek-v4-flash-free": 7,
    "opencode/mimo-v2.5-free": 7,
    "opencode/north-mini-code-free": 5,
    "opencode/nemotron-3-ultra-free": 9,
    "ollama/qwen3:32b-q8_0": 6,
    "ollama/qwen3:32b": 6,
    "ollama/qwen3-coder:30b": 5,
    "ollama/devstral:latest": 5,
    "ollama/qwen2.5:14b": 4,
    "ollama/llama3.1:8b": 3,
    "ollama/llama3.2:3b": 2,
}

# A non-advised choice defaults to ``insufficient``.  Only list roles here when
# the model is capable but fails the other half of the recommendation band: it
# costs too much for that hand or is dominated by a better same-price choice.
WASTEFUL_ROLES = {
    "claude-sonnet-5": frozenset(("drafter",)),
    "claude-opus-4-7": frozenset(ROLES),
    "claude-opus-4-8": frozenset(("drafter", "sections")),
    "claude-fable-5": frozenset(("drafter", "writer", "sections")),
    "Gemini 3.5 Flash (Medium)": frozenset(("drafter",)),
    "Gemini 3.5 Flash (High)": frozenset(("drafter",)),
    "Gemini 3.1 Pro (Low)": frozenset(("drafter",)),
    "Gemini 3.1 Pro (High)": frozenset(("drafter", "sections")),
    "gpt-5.6-sol": frozenset(("drafter", "sections")),
    "gpt-5.6-terra": frozenset(("drafter",)),
    "gpt-5.5": frozenset(ROLES),
    "gpt-5.4": frozenset(ROLES),
    "opencode-go/deepseek-v4-pro": frozenset(("drafter",)),
    "opencode-go/glm-5.1": frozenset(ROLES),
    "opencode-go/glm-5.2": frozenset(("drafter", "sections")),
    "opencode-go/kimi-k2.6": frozenset(("drafter", "sections")),
    "opencode-go/kimi-k2.7-code": frozenset(("drafter",)),
    "opencode-go/mimo-v2.5-pro": frozenset(ROLES),
    "opencode-go/minimax-m2.7": frozenset(ROLES),
    "opencode-go/minimax-m3": frozenset(("drafter",)),
    "opencode-go/qwen3.6-plus": frozenset(ROLES),
    "opencode-go/qwen3.7-max": frozenset(("drafter", "sections")),
    "opencode-go/qwen3.7-plus": frozenset(("drafter",)),
}

MODEL_ROLES = {model: policy["roles"] for model, policy in MODEL_POLICY.items()}


# Supported levels come from the live provider rows.  These profiles deliberately
# omit valid-but-unwise settings at both ends: low effort is gray for complex
# bundled phases, while unnecessarily high effort and max/ultra are gray when a
# lower setting clears the hand's bar.  Every supported level remains visible.
EFFORT_PROFILES = {
    "claude-fable-5": {"reviewer": ("high",)},
    "claude-opus-4-8": {
        "writer": ("high",),
        "reviewer": ("high", "xhigh"),
    },
    "claude-sonnet-5": {
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
        "reviewer": ("high",),
    },
    "gpt-5.6-sol": {
        "writer": ("medium", "high"),
        "reviewer": ("high", "xhigh"),
    },
    "gpt-5.6-terra": {
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
        "reviewer": ("high",),
    },
    "gpt-5.6-luna": {
        "drafter": ("medium",),
        "writer": ("medium", "high"),
        "sections": ("medium", "high"),
    },
    "gpt-5.4-mini": {"drafter": ("high",)},
    "opencode-go/deepseek-v4-flash": {"drafter": ("high",)},
    "opencode-go/deepseek-v4-pro": {
        role: ("high",) for role in ("writer", "sections", "reviewer")
    },
    "opencode-go/glm-5.2": {
        role: ("high",) for role in ("writer", "reviewer")
    },
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
        "power": MODEL_POWER.get(model_id),
        "advised": {role: role in roles for role in ROLES},
        "reason": {
            role: None if role in roles else
            ("wasteful" if role in WASTEFUL_ROLES.get(model_id, ()) else "insufficient")
            for role in ROLES
        },
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
