"""Verified vendor prices shared by runtime estimates and build accounting."""

PRICING_VERSION = "openai-anthropic-standard-2026-07-21"
PRICING_SOURCE = ("https://developers.openai.com/api/docs/pricing ; "
                  "https://www.anthropic.com/pricing")

# USD per one million tokens. Unknown models stay unpriced.
MODEL_PRICES = {
    "gpt-5.6-sol": {"freshInput": 5.0, "cachedInput": 0.5,
                    "cacheWriteInput": 6.25, "output": 30.0},
    "gpt-5.6-terra": {"freshInput": 2.5, "cachedInput": 0.25,
                      "cacheWriteInput": 3.125, "output": 15.0},
    "gpt-5.6-luna": {"freshInput": 1.0, "cachedInput": 0.1,
                     "cacheWriteInput": 1.25, "output": 6.0},
    "claude-haiku-4-5": {"freshInput": 1.0, "cachedInput": 0.1,
                         "cacheWriteInput": 1.25, "output": 5.0},
    "claude-sonnet-5": {"freshInput": 2.0, "cachedInput": 0.2,
                        "cacheWriteInput": 2.5, "output": 10.0},
    "claude-opus-4-7": {"freshInput": 5.0, "cachedInput": 0.5,
                        "cacheWriteInput": 6.25, "output": 25.0},
    "claude-opus-4-8": {"freshInput": 5.0, "cachedInput": 0.5,
                        "cacheWriteInput": 6.25, "output": 25.0},
    "claude-fable-5": {"freshInput": 10.0, "cachedInput": 1.0,
                       "cacheWriteInput": 12.5, "output": 50.0},
}
GPT_MODELS = frozenset(model for model in MODEL_PRICES
                       if model.startswith("gpt-"))
PRICED_MODELS = frozenset(MODEL_PRICES)
