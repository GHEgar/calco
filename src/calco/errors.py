class CalcoError(Exception):
    pass


class InvalidModel(CalcoError, ValueError):
    pass


class ParseError(CalcoError):
    pass


class NotRecognized(CalcoError):
    pass
