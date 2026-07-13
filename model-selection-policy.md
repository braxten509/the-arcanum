# Bindery model-selection policy

Research snapshot: **2026-07-13**. The executable source of truth is
`arcanum/model_policy.py`; this page records why the current 42 live choices are
or are not advised.

## The bar

An advised model must be realistic for the **entire hand**, not merely able to
answer one representative prompt:

- **Drafter** owns the skeleton, runtime setup, economy, cosmetics, and the
  whole-tome Phase 7 validation/repair pass. It is validator-backed, but not
  purely mechanical.
- **Writer** owns the backward-designed course arc and the minigame banks. A bad
  arc compromises every later phase.
- **Sections** may own all teaching prose, worked examples, exercises, and
  cumulative project changes in one unsplit run. Splitting improves cost and
  reliability; it does not lower this recommendation bar.
- **Reviewer** rereads every authored artifact, reconstructs the learner journey,
  executes real milestones, finds semantic gaps, and independently repairs them.

These recommendations cannot guarantee factual perfection—no current model can.
The accuracy strategy is a capable author, web/repository evidence, executable
validation, and a different strong reviewer. Provider benchmark claims below are
treated as directional evidence, not as independent guarantees.

Legend: **D** Drafter, **W** Writer, **S** Sections, **R** Reviewer. A dash means
the option remains visible but is gray and marked `(not advised)` for that hand.
Efforts listed are the only selectable efforts for the applicable advised hands;
other provider-supported efforts remain visible but gray.

## Claude CLI

| Live model | D | W | S | R | Recommended effort by hand | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|---|
| `claude-haiku-4-5` | yes | — | — | — | fixed; Haiku has no effort control | Near-frontier speed and coding do make it useful for bounded, checked work. Anthropic positions it for rapid/subagent use, not ownership of a complete course phase. |
| `claude-sonnet-5` | yes | yes | yes | yes | D medium/high; W/S medium/high/xhigh; R high/xhigh | Current frontier Sonnet with broad knowledge work and long-running agent evidence. |
| `claude-opus-4-7` | yes | yes | yes | yes | D high; W/S/R high/xhigh | Anthropic recommends high as the intelligence-sensitive floor and xhigh for long-horizon agentic work. |
| `claude-opus-4-8` | yes | yes | yes | yes | D high; W/S/R high/xhigh | Same effort guidance as 4.7; a strong top-tier author or reviewer. |
| `claude-fable-5` | yes | yes | yes | yes | D medium/high; W/S/R high/xhigh | Strongest widely released Claude for long-running agents, but usually unnecessary outside the highest quality tier. |

## Antigravity CLI

Antigravity embeds effort in the displayed model name, so it has no separate
effort box.

| Live model/variant | D | W | S | R | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|
| `Gemini 3.5 Flash (Low)` | yes | — | — | — | Low is explicitly the fewer-step, lower-latency setting. |
| `Gemini 3.5 Flash (Medium)` | yes | yes | yes | — | Google's default and recommendation for most complex work; use High for independent final review. |
| `Gemini 3.5 Flash (High)` | yes | yes | yes | yes | Sustained frontier Flash with maximum reasoning/tool behavior. |
| `Gemini 3.1 Pro (Low)` | yes | — | — | — | Strong base model, but Low minimizes depth on the exact long-horizon work these hands perform. |
| `Gemini 3.1 Pro (High)` | yes | yes | yes | yes | Advanced reasoning/agentic model at its default deep setting. |
| `GPT-OSS 120B (Medium)` | yes | — | — | — | Strong tool use and roughly o4-mini-class open-model performance, but not the general pedagogy/reviewer floor. |

## Codex CLI

The installed `codex debug models` catalog is read live. It currently describes
Sol as frontier, Terra as balanced, Luna as fast/affordable, GPT-5.5 as suitable
for complex coding/research, GPT-5.4 as a strong full model, and Mini as intended
for simpler tasks.

| Live model | D | W | S | R | Recommended effort by hand |
|---|:---:|:---:|:---:|:---:|---|
| `gpt-5.6-sol` | yes | yes | yes | yes | D medium/high; W/S medium/high/xhigh; R high/xhigh |
| `gpt-5.6-terra` | yes | yes | yes | yes | D/W/S medium/high; R high/xhigh |
| `gpt-5.6-luna` | yes | yes | yes | — | D/W/S medium/high |
| `gpt-5.5` | yes | yes | yes | yes | D medium/high; W/S medium/high/xhigh; R high/xhigh |
| `gpt-5.4` | yes | yes | yes | yes | D/W/S medium/high; R high/xhigh |
| `gpt-5.4-mini` | yes | — | — | — | D high/xhigh |

`low`, `max`, and `ultra` are not recommended for these bundled hands: Low
unnecessarily risks shallow execution, while Max/Ultra spend is not justified by
the tome workflow without a model-specific evaluation showing a measurable gain.

## OpenCode Go

OpenCode says Go's model/provider combinations are tested for coding-agent use.
That establishes serving quality, but coding-agent suitability alone is not enough
for Writer or Reviewer; the underlying vendor evidence determines those roles.

| Live model | D | W | S | R | Effort | Conservative conclusion |
|---|:---:|:---:|:---:|:---:|---|---|
| `opencode-go/deepseek-v4-flash` | yes | — | — | — | high | 13B active; official claim is Pro-like simple-agent performance, not equivalent long-horizon ownership. |
| `opencode-go/deepseek-v4-pro` | yes | yes | yes | yes | high | 1M context, broad world knowledge, frontier reasoning, tool use, and long outputs. |
| `opencode-go/glm-5.1` | yes | yes | yes | yes | fixed | Explicitly built for eight-hour tasks and positioned for long documents, teaching materials, and research papers. |
| `opencode-go/glm-5.2` | yes | yes | yes | yes | high | Improved 1M-context flagship with broad reasoning and long-horizon evidence. |
| `opencode-go/kimi-k2.6` | yes | yes | yes | yes | fixed | Strong research/search, knowledge, document delivery, and long-running agent results—not merely coding. |
| `opencode-go/kimi-k2.7-code` | yes | — | — | — | fixed | Coding-focused derivative; its public evidence is much narrower than K2.6's general/research evidence. |
| `opencode-go/mimo-v2.5` | yes | — | — | — | fixed | Efficient 15B-active agent model; too small for the three critical authorship hands. |
| `opencode-go/mimo-v2.5-pro` | yes | yes | yes | — | fixed | 42B-active, 1M-context Pro model with strong long-context/agent results, but insufficient final-review evidence. |
| `opencode-go/minimax-m2.7` | yes | yes | yes | — | fixed | Strong professional document and office-delivery model; not the independent factual arbiter. |
| `opencode-go/minimax-m3` | yes | yes | yes | yes | fixed | 1M-context frontier agent with browsing, reasoning, and autonomous research-reproduction evidence. |
| `opencode-go/qwen3.6-plus` | yes | yes | yes | — | fixed | 1M-context content/document and agent model; Max remains the conservative reviewer tier. |
| `opencode-go/qwen3.7-max` | yes | yes | yes | yes | fixed | Qwen flagship for complex multi-step reasoning and agents. |
| `opencode-go/qwen3.7-plus` | yes | yes | yes | — | fixed | Current performance/cost model for content, documents, coding, and productivity workflows. |

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

- Anthropic: [model selection](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model), [effort guidance](https://platform.claude.com/docs/en/build-with-claude/effort), and [Haiku 4.5 positioning](https://www.anthropic.com/news/claude-haiku-4-5).
- Google: [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models) and [Gemini 3.5 Flash levels and long-horizon guidance](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5).
- OpenAI: [latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) and [gpt-oss-120b model page](https://developers.openai.com/api/docs/models/gpt-oss-120b).
- OpenCode: [Go models, prices, and limits](https://opencode.ai/docs/go/) and [Zen free-endpoint terms](https://opencode.ai/docs/zen/).
- DeepSeek: [V4 release and Pro/Flash positioning](https://api-docs.deepseek.com/news/news260424/) and [model details](https://api-docs.deepseek.com/quick_start/pricing).
- Z.ai: [GLM-5.1 long-horizon and document guidance](https://docs.z.ai/guides/llm/glm-5.1) and [GLM-5.2 official model card](https://huggingface.co/zai-org/GLM-5.2).
- Moonshot AI: [Kimi K2.6 official model card](https://huggingface.co/moonshotai/Kimi-K2.6), [Kimi model catalog](https://platform.kimi.ai/docs/models), and [Kimi K2.7 Code model card](https://huggingface.co/moonshotai/Kimi-K2.7-Code).
- Xiaomi MiMo: [MiMo-V2.5/Pro official model card](https://huggingface.co/XiaomiMiMo/MiMo-V2.5).
- MiniMax: [M2.7 professional-work evidence](https://www.minimax.io/news/minimax-m27-en) and [M3 long-horizon evidence](https://www.minimax.io/models/text/m3).
- Alibaba/Qwen: [recommended model classes](https://www.alibabacloud.com/help/en/model-studio/what-is-model-studio), [Qwen text/content guidance](https://www.alibabacloud.com/help/en/model-studio/text-generation-model), and [Qwen3.7/3.6 release notes](https://www.alibabacloud.com/help/en/model-studio/newly-released-models).
- Local-family model cards: [Qwen3](https://qwenlm.github.io/blog/qwen3/), [Qwen3-Coder](https://qwenlm.github.io/blog/qwen3-coder/), [Qwen2.5](https://qwenlm.github.io/blog/qwen2.5-llm/), [Devstral](https://mistral.ai/news/devstral/), [Llama 3.1](https://ai.meta.com/blog/meta-llama-3-1/), and [Llama 3.2](https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/).
- Free-endpoint underlying models: [North Mini Code official model card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) and [NVIDIA Nemotron 3 Ultra official model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4).
