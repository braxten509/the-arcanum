"""Stateless API-equivalent estimates for CLI-reported token usage."""

from .pricing import MODEL_PRICES, PRICING_SOURCE, PRICING_VERSION

USAGE_KEYS = (
    "inputTokens", "freshInputTokens", "cachedInputTokens",
    "cacheWriteTokens", "cacheWrite1hTokens",
    "outputTokens", "reasoningTokens", "totalTokens",
)


def cache_write_cost(usage, rates):
    """Price both cache-write buckets. ``cacheWrite1hTokens`` is a subset of the total.

    Clamped rather than trusted: a provider that reports a 1-hour bucket larger than
    the write total would otherwise bill negative tokens at the 5-minute rate.
    """
    extended = min(usage["cacheWrite1hTokens"], usage["cacheWriteTokens"])
    return ((usage["cacheWriteTokens"] - extended) * rates["cacheWriteInput"]
            + extended * rates["cacheWrite1hInput"])


def normalize_usage(value):
    if not isinstance(value, dict):
        return None
    normalized = {
        key: max(0, int(value.get(key) or 0)) for key in USAGE_KEYS
    }
    if not value.get("freshInputTokens") and normalized["inputTokens"]:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized["cachedInputTokens"]
            - normalized["cacheWriteTokens"])
    if not normalized["totalTokens"]:
        normalized["totalTokens"] = (
            normalized["inputTokens"] + normalized["outputTokens"])
    return normalized


def usage_cost(model, usage):
    rates = MODEL_PRICES.get(str(model or ""))
    if not usage or not rates:
        return None, rates
    amount = (
        usage["freshInputTokens"] * rates["freshInput"]
        + usage["cachedInputTokens"] * rates["cachedInput"]
        + cache_write_cost(usage, rates)
        + usage["outputTokens"] * rates["output"]
    ) / 1_000_000
    return round(amount, 9), rates


def estimate_api_equivalent_cost(model, usage):
    """Price CLI usage as if it used the matching public API."""
    normalized = normalize_usage(usage)
    amount, rates = usage_cost(model, normalized)
    if amount is None:
        return None
    return {
        "model": str(model or ""),
        "usd": amount,
        "usage": normalized,
        "rates": dict(rates),
        "pricingVersion": PRICING_VERSION,
        "pricingSource": PRICING_SOURCE,
    }
