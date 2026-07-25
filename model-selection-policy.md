# Bindery model-selection policy

Research snapshot: **2026-07-14**. The executable source of truth is
`arcanum/model_policy.py`; this page records why the current 43 live choices are
selectable, insufficient, or wasteful for each hand.

## The bar

An advised model must fall inside a **two-sided recommendation band** for the
entire hand, not merely be able to answer one representative prompt:

1. **Capability floor:** it must realistically complete every phase bundled into
   that hand.
2. **Cost ceiling:** it must offer a plausible quality/reliability gain over the
   cheapest model that already clears that hand. Same-price predecessors and
   premium bulk-output choices with no role-specific payoff are gray too.

- **Drafter** owns the skeleton, runtime setup, economy, cosmetics, and the
  whole-tome Phase 7 validation/repair pass. It is validator-backed, but not
  purely mechanical.
- **Writer** owns the backward-designed course arc and the minigame banks. A bad
  arc compromises every later phase.
- **Sections** may own all teaching prose, worked examples, exercises, and
  cumulative project changes in one unsplit run. Splitting improves cost and
  reliability; it does not lower this recommendation bar.
- **Reviewer** rereads every authored artifact and the persisted reconstructed learner
  project, examines actual command/output evidence, finds semantic gaps, and repairs them.
  A clean claim or authored repair must be verified by a different configured model command.
  Primary qualification is binary and requires two consecutive passes of the authored-source
  repair/replay suite plus complete discovery in the frozen real HollowCrawl false-pass case;
  diagnostic subcheck counts are never partial approval. A model that clears repair/replay but
  misses a latent real blocker may remain an independent verifier, never the primary reviewer.

  The selectable Reviewer choice is now threefold: **Sol at high** (fully
  qualified), **Fable 5 at high** (operator-designated premium audit hand,
  untrialed on v3 — the deterministic launch/acceptance/verification gates carry
  the qualification burden), or **Kimi K2.6** (economy primary, legal only with
  Sol or Fable explicitly pinned behind it — the Bindery's escalation box on
  browser builds, the `[autonomy]."8"` chain on unattended CLI builds).

These recommendations cannot guarantee factual perfection—no current model can.
The accuracy strategy is a capable author, web/repository evidence, executable
validation, and a different strong reviewer. Provider benchmark claims below are
treated as directional evidence, not as independent guarantees.

Published API prices, Codex credit rates, and OpenCode Go usage allowances are
used as relative cost evidence. Login plans may hide the per-token bill, but an
expensive choice still consumes more quota/credits and reduces the number of
complete runs available.

Legend: **D** Drafter, **W** Writer, **S** Sections, **R** Reviewer. A dash means
the option remains visible but gray. The Custom picker says `(insufficient)`
when capability, evidence, context, or endpoint durability is below that hand's
complete-task bar; it says `(wasteful)` when the model is capable but overpriced
for that hand or dominated by a better-value choice.
Efforts listed are the only selectable efforts for the applicable advised hands;
other provider-supported efforts remain visible but gray.

Every selectable model also shows `power X/10`. This is an ordinal
**effective tome-authoring capability in this harness** estimate, independent of cost and
including observed false-pass reliability: 10 is the strongest
current frontier; 9 is frontier author/reviewer class; 8 is a strong complete
author with some tradeoffs; 7 is a dependable checked/support agent; 6 and below
indicates a constrained local, older, or narrow specialist. It is a researched
workflow aid, not a claim that cross-provider benchmark scores are scientifically
interchangeable. Gray models omit the number because the exclusion reason is the
actionable fact for that hand.

## Claude CLI

| Live model | D | W | S | R | Recommended effort by hand | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|---|
| `claude-haiku-4-5` | yes | — | — | — | fixed; Haiku has no effort control | Near-frontier speed and coding do make it useful for bounded, checked work. Anthropic positions it for rapid/subagent use, not ownership of a complete course phase. |
| `claude-sonnet-5` | — | yes | yes | — | W/S medium or high | $2/$10 per MTok through August 2026. It remains a cost-effective author, but its Reviewer v3 run exhausted the test budget before repair closure. |
| `claude-opus-4-7` | — | — | — | — | all efforts gray | Same $5/$25 base rate as newer Opus 4.8, with its fast mode being retired. It is a same-price predecessor. |
| `claude-opus-4-8` | — | yes | — | — | W high | $5/$25. It remains useful for course architecture, but exhausted the Reviewer v3 budget with most critical gates open. |
| `claude-opus-5` | yes | yes | yes | yes | every effort, every hand | $5/$25 — the Opus rate card is unchanged, and public results put it within a point of Fable 5 on SWE-bench Pro at half the price. Operator-designated 2026-07-24 for every hand at every effort with no restriction. It ran no harness role trial; the deterministic launch/acceptance/independent-verification gates carry the qualification burden, as they do for Fable 5. |
| `claude-fable-5` | — | — | — | yes | R high only | $10/$50, operator-designated as a premium final-audit hand at high effort. Untrialed on Reviewer v3; the deterministic launch/acceptance/independent-verification gates carry the qualification burden. Authoring hands remain wasteful. |

Sonnet's and Opus 4.7/4.8's reviewer runs remain inconclusive (budget-exhausted)
and fail closed; they may still author in their proven hands. Opus 5 is the
operator-designated exception and is not limited on any hand.

## Antigravity CLI — measured, not preset

Antigravity embeds effort in the displayed model name, so it has no separate
effort box.

| Live model/variant | D | W | S | R | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|
| `Gemini 3.5 Flash (Low)` | — | — | — | — | No dependable complete-tome evidence in this harness. |
| `Gemini 3.5 Flash (Medium)` | — | — | — | — | Repeated local runs missed executable and teaching defects. |
| `Gemini 3.5 Flash (High)` | — | yes | yes | — | Passed compact Writer and executable Sections. Reviewer remains denied: its original full-tome Phase 8 certified a crashing project, and the blind replay still stopped at 2/3 root causes. |
| `Gemini 3.1 Pro (Low)` | — | — | — | — | No successful complete-tome evidence; Low is not a safe long-horizon setting. |
| `Gemini 3.1 Pro (High)` | yes | yes | yes | — | Retains its earlier authoring passes, but returned from Reviewer v3 with twelve mandatory gates open. |
| `GPT-OSS 120B (Medium)` | yes | — | — | — | Strong tool use and roughly o4-mini-class open-model performance, but not the general pedagogy/reviewer floor. |

The role trials are bounded and deterministic; their binary results are recorded in the
`basis` string of each model's entry in `arcanum/authoring/model_policy.py`, which is what
actually assigns the hands and is returned by `/api/models`. Reviewer v3
requires authored repairs, replay, ordinary launch, authentic negative controls, truthful evidence,
and a preserved clean control twice in fresh workspaces. The additional blind HollowCrawl case
requires looking behind the first crash; only Sol found the float viewport bounds, the missing
`draw_inventory` import, and the constant PASS receipt. Flash completed one compact v3 run, but
the stronger real evidence still bars it. Gemini Pro did not complete v3 and is also barred.

## Codex CLI

The installed `codex debug models` catalog is read live. It currently describes
Sol as frontier, Terra as balanced, Luna as fast/affordable, and Mini as intended
for simpler tasks. The current Codex rate card makes the replacements unusually
clear: GPT-5.5 costs exactly the same as Sol, and GPT-5.4 exactly the same as
Terra, while OpenAI says GPT-5.6 improves both quality and efficiency.

| Live model | D | W | S | R | Recommended effort by hand |
|---|:---:|:---:|:---:|:---:|---|
| `gpt-5.6-sol` | — | yes | — | yes | W medium/high; R high/xhigh |
| `gpt-5.6-terra` | — | yes | yes | — | W/S medium/high; verification/general-backup high |
| `gpt-5.6-luna` | yes | yes | yes | — | D medium only; W/S medium/high |
| `gpt-5.5` | — | — | — | — | all efforts gray; same credit rate as newer Sol |
| `gpt-5.4` | — | — | — | — | all efforts gray; same credit rate as newer Terra |
| `gpt-5.4-mini` | yes | — | — | — | D high only |

`low`, `max`, and `ultra` remain gray. High and xhigh are now role-scoped too:
Luna Drafter and Mini Drafter expose only their cheapest adequate setting. Sol is the only
fully qualified primary final reviewer (Fable 5 and chained Kimi are the two graded
exceptions above); Terra remains the distinct verification/general-recovery hand
because it passed repair/replay twice but missed the blind case's latent second launch blocker.

## OpenCode Go

OpenCode says Go's model/provider combinations are tested for coding-agent use.
That establishes serving quality, but coding-agent suitability alone is not enough
for Writer or Reviewer; the underlying vendor evidence determines those roles.

| Live model | D | W | S | R | Effort | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|---|
| `opencode-go/deepseek-v4-flash` | yes | — | — | — | high | 13B active; official claim is Pro-like simple-agent performance, not equivalent long-horizon ownership. |
| `opencode-go/deepseek-v4-pro` | — | yes | — | — | high | Its compact Sections run repaired the code but returned a placebo acceptance receipt instead of exercising it; Sections and Reviewer are disabled. |
| `opencode-go/glm-5.1` | — | — | — | — | all gray | Same $1.40/$4.40 rate as newer GLM-5.2; dominated. |
| `opencode-go/glm-5.2` | — | yes | — | — | high | $1.40/$4.40. Passed Reviewer v3 twice but missed HollowCrawl's guaranteed next-frame `NameError`; primary review is disabled. |
| `opencode-go/kimi-k2.6` | — | yes | — | yes | fixed | $0.95/$4.00. Passed Reviewer v3 twice; missed the latent real blocker in the blind audit. Approved as the economy primary reviewer only with a pinned Sol/Fable escalation hand. |
| `opencode-go/kimi-k2.7-code` | — | — | — | — | fixed | Same output price as K2.6, narrower evidence, and far more costly than Drafter-class models. |
| `opencode-go/mimo-v2.5` | yes | — | — | — | fixed | Efficient 15B-active agent model; too small for the three critical authorship hands. |
| `opencode-go/mimo-v2.5-pro` | — | — | — | — | fixed | Same $1.74/$3.48 rate as broader DeepSeek V4 Pro; dominated for this workflow. |
| `opencode-go/minimax-m2.7` | — | — | — | — | fixed | Same $0.30/$1.20 rate as newer, broader MiniMax M3; dominated. |
| `opencode-go/minimax-m3` | — | yes | yes | — | fixed | Passed Writer and Sections cheaply. Its Reviewer run emitted five findings for three root causes, including one false blocker, so it cannot independently approve a tome. |
| `opencode-go/qwen3.6-plus` | — | — | — | — | fixed | Costs $0.50/$3.00 at <=256K versus newer 3.7 Plus at $0.40/$1.60; dominated. |
| `opencode-go/qwen3.7-max` | — | yes | — | — | fixed | $2.50/$7.50 flagship for course architecture; its Reviewer v3 run timed out with eight critical gates open. |
| `opencode-go/qwen3.7-plus` | — | yes | — | — | fixed | Suitable for planning, but an observed long-course section run was incomplete and non-replayable; Sections and Reviewer are disabled. |

## OpenCode Maple AI

A separate OpenCode provider gateway (`mapleai/*`), surfaced alongside the Go
models in the OpenCode CLI picker. Even when the underlying family matches, Reviewer
qualification is endpoint-specific; models.dev carries no effort variants for this gateway.

| Live model | D | W | S | R | Effort | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|---|
| `mapleai/glm-5-2` | — | yes | — | — | fixed | Same model family, but this endpoint has not independently passed Reviewer v3 twice. |

## OpenCode limited-time free endpoints

| Live endpoint | D | W | S | R | Why every hand is gray |
|---|:---:|:---:|:---:|:---:|---|
| `opencode/big-pickle` | — | — | — | — | Limited-time stealth model; the underlying model is undisclosed and can change. |
| `opencode/deepseek-v4-flash-free` | — | — | — | — | Capable underlying model, but a limited-time data-collecting endpoint is not a durable dependency for a multi-hour complete build. |
| `opencode/mimo-v2.5-free` | — | — | — | — | Same operational limitation as the free Flash endpoint. |
| `opencode/north-mini-code-free` | — | — | — | — | Limited-time endpoint plus a 30B-total/3B-active code-only model. |
| `opencode/nemotron-3-ultra-free` | — | — | — | — | The underlying model is powerful, but OpenCode/NVIDIA describe this endpoint as limited-time and trial-only. |

This is an operational recommendation, not a claim that DeepSeek Flash or
Nemotron Ultra suddenly become less intelligent when priced at zero. The stable Go
versions are used by presets; promotional endpoints stay available elsewhere in
OpenCode.

## Exact local Ollama installations

These decisions use the installed artifacts, not the best possible version of a
model family. `ollama show --verbose` reports both Qwen3-32B builds at only 40,960
runtime context, Qwen2.5 at 32,768, and the listed quantizations below.

| Live model | Installed form | D | W | S | R | Conservative conclusion |
|---|---|:---:|:---:|:---:|:---:|---|
| `ollama/qwen3:32b-q8_0` | 32.8B Q8, thinking/tools, 40,960 context | yes | — | — | — | Strong enough for checked support work; context and generation age rule out full authorship. |
| `ollama/qwen3:32b` | 32.8B Q4, thinking/tools, 40,960 context | yes | — | — | — | Same narrow role, with more quantization risk. |
| `ollama/qwen3-coder:30b` | 30.5B-total/3B-active Q4, 262K | — | — | — | — | Code-specialized and too little active capacity for a general bundled hand. |
| `ollama/devstral:latest` | Devstral Small 2505, 23.6B Q4, 131K | — | — | — | — | Older research-preview software-engineering specialist, not a general course model. |
| `ollama/qwen2.5:14b` | 14.8B Q4, 32K | — | — | — | — | Too old, small, and context-limited for a complete hand. |
| `ollama/llama3.1:8b` | 8B Q4, 131K | — | — | — | — | Useful local assistant, not an autonomous tome worker. |
| `ollama/llama3.2:3b` | 3.2B Q4, 131K | — | — | — | — | Meta positions this class for edge summarization, rewriting, and lightweight tool use. |

## Primary sources

- Anthropic: [model selection](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model), [current pricing](https://platform.claude.com/docs/en/about-claude/pricing), [effort guidance](https://platform.claude.com/docs/en/build-with-claude/effort), and [Haiku 4.5 positioning](https://www.anthropic.com/news/claude-haiku-4-5).
- Google: [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models), [current pricing](https://ai.google.dev/gemini-api/docs/pricing), and [Gemini 3.5 Flash levels and long-horizon guidance](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5).
- OpenAI: [latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), [current Codex credit rate card](https://learn.chatgpt.com/docs/pricing#what-are-tokens-and-credits), and [gpt-oss-120b model page](https://developers.openai.com/api/docs/models/gpt-oss-120b).
- OpenCode: [Go models, prices, and limits](https://opencode.ai/docs/go/) and [Zen free-endpoint terms](https://opencode.ai/docs/zen/).
- DeepSeek: [V4 release and Pro/Flash positioning](https://api-docs.deepseek.com/news/news260424/) and [model details](https://api-docs.deepseek.com/quick_start/pricing).
- Z.ai: [GLM-5.1 long-horizon and document guidance](https://docs.z.ai/guides/llm/glm-5.1) and [GLM-5.2 official model card](https://huggingface.co/zai-org/GLM-5.2).
- Moonshot AI: [Kimi K2.6 official model card](https://huggingface.co/moonshotai/Kimi-K2.6), [Kimi model catalog](https://platform.kimi.ai/docs/models), and [Kimi K2.7 Code model card](https://huggingface.co/moonshotai/Kimi-K2.7-Code).
- Xiaomi MiMo: [MiMo-V2.5/Pro official model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.5).
- MiniMax: [M2.7 professional-work evidence](https://www.minimax.io/news/minimax-m27-en) and [M3 long-horizon evidence](https://www.minimax.io/models/text/m3).
- Alibaba/Qwen: [recommended model classes](https://www.alibabacloud.com/help/en/model-studio/what-is-model-studio), [Qwen text/content guidance](https://www.alibabacloud.com/help/en/model-studio/text-generation-model), and [Qwen3.7/3.6 release notes](https://www.alibabacloud.com/help/en/model-studio/newly-released-models).
- Local-family model cards: [Qwen3](https://qwenlm.github.io/blog/qwen3/), [Qwen3-Coder](https://qwenlm.github.io/blog/qwen3-coder/), [Qwen2.5](https://qwenlm.github.io/blog/qwen2.5-llm/), [Devstral](https://mistral.ai/news/devstral/), [Llama 3.1](https://ai.meta.com/blog/meta-llama-3-1/), and [Llama 3.2](https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/).
- Free-endpoint underlying models: [North Mini Code official model card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) and [NVIDIA Nemotron 3 Ultra official model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4).
