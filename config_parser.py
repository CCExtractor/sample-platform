from werkzeug.utils import import_string


def parse_config(obj):
    """
    Parses given config either from a file or from an object. Method borrowed
    from Flask.

    :param obj: The config to parse.
    :type obj: any
    :return: A dictionary containing the parsed Flask config
    :rtype: dict
    """
    config = {}
    if isinstance(obj, (str, unicode)):
        obj = import_string(obj)
    for key in dir(obj):
        if key.isupper():
            config[key] = getattr(obj, key)
    return config
