"""Pure argv placeholder expansion."""


def substitute(argv, **values):
    out = []
    for argument in argv:
        for key, value in values.items():
            argument = argument.replace("{" + key + "}", value)
        out.append(argument)
    return out


def file_argv(argv, path):
    if any("{file}" in argument for argument in argv):
        return [argument.replace("{file}", path) for argument in argv]
    return [*argv, path]
