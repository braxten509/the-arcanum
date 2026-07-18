"""Provider-neutral AI service errors surfaced to application callers."""


class ProviderConfigurationError(ValueError):
    """The selected provider or model cannot satisfy the requested invocation."""
