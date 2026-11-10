"""Dependency injection into handlers by argument name."""

import inspect


def inject(callback, data, skip=0):
    """Pass a handler only the arguments it declares.

    ``skip`` is the number of leading positional arguments the dispatcher
    passes itself (the event or the error).
    """
    try:
        parameters = list(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError):
        return {}

    result = {}
    for index, parameter in enumerate(parameters):
        if index < skip:
            continue
        if parameter.kind not in (
            parameter.POSITIONAL_OR_KEYWORD,
            parameter.KEYWORD_ONLY,
        ):
            continue
        if parameter.name in data:
            result[parameter.name] = data[parameter.name]
    return result
