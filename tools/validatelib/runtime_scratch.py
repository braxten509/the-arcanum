"""Validator adapter for the engine-owned trusted snippet runtime policy."""


def scratch_runtime_config(runtime_table):
    """Keep one compatibility import while sharing the server's core policy."""
    from runtimes import snippet_config
    return snippet_config(runtime_table)
