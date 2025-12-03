# https://github.com/micropython/micropython-lib/blob/master/python-stdlib/logging/logging.py

import io
import sys

if sys.implementation.name != 'micropython':
    from typing import TypeAlias
    StrPath: TypeAlias = str | bytes
    # MaybeNone: TypeAlias = None | object
    def const(indata: int) -> int:
        return indata
else:
    from micropython import const  # type: ignore


import time

CRITICAL = const(50)
ERROR = const(40)
WARNING = const(30)
INFO = const(20)
DEBUG = const(10)
NOTSET = const(0)

_DEFAULT_LEVEL = const(WARNING)

_level_dict: dict[int, str] = {
    CRITICAL: "CRITICAL",
    ERROR: "ERROR",
    WARNING: "WARNING",
    INFO: "INFO",
    DEBUG: "DEBUG",
    NOTSET: "NOTSET",
}

_loggers: dict[str, "Logger"] = {}
_stream: io.TextIOBase | MaybeNone = sys.stderr  #type: ignore
_default_fmt = "%(levelname)s:%(name)s:%(message)s"
_default_datefmt = "%Y-%m-%d %H:%M:%S"

def get_log_level_by_name(loglevelname: str) -> int|None:
    for k, v in _level_dict.items():
        if v == loglevelname:
            return k

    return None


class LogRecord:
    def set(self, name: str, level: int, message: object) -> None:
        self.name: str = name
        self.levelno: int = level
        self.levelname: str = _level_dict[level]
        self.message = message
        self.ct: float = time.time()  # type: ignore[attr-defined]
        self.msecs: int = int((self.ct - int(self.ct)) * 1000)
        self.asctime: str|None = None


class Handler:
    def __init__(self, level: int=NOTSET) -> None:
        self.level: int = level
        self.formatter: Formatter|None = None

    def close(self) -> None:
        pass

    def setLevel(self, level: int) -> None:
        self.level = level

    def set_formatter(self, formatter: "Formatter") -> None:
        self.formatter = formatter

    def format(self, record: LogRecord) -> str:
        assert self.formatter is not None
        return self.formatter.format(record)


class StreamHandler(Handler):
    def __init__(self, stream: io.TextIOBase|None=None) -> None:
        super().__init__()
        self.stream: io.TextIOBase = _stream if stream is None else stream
        self.terminator: str = "\n"

    def close(self) -> None:
        if hasattr(self.stream, "flush"):
            self.stream.flush()

    def emit(self, record: LogRecord) -> None:
        if record.levelno >= self.level:
            self.stream.write(self.format(record) + self.terminator)


class FileHandler(StreamHandler):
    def __init__(self, filename: StrPath, mode: str="a", encoding: str="UTF-8"):
        super().__init__(stream=io.open(filename, mode=mode, encoding=encoding))

    def close(self) -> None:
        super().close()
        self.stream.close()


class Formatter:
    def __init__(self, fmt: str|None=None, datefmt: str|None=None):
        super().__init__()
        self.fmt = _default_fmt if fmt is None else fmt
        self.datefmt = _default_datefmt if datefmt is None else datefmt

    def uses_time(self) -> bool:
        return "asctime" in self.fmt

    def format_time(self, datefmt: str, record: LogRecord) -> str|None:
        if hasattr(time, "strftime"):
            return time.strftime(datefmt, time.localtime(record.ct)) # type: ignore
        return None

    def format(self, record: LogRecord) -> str:
        if self.uses_time():
            record.asctime = self.format_time(self.datefmt, record)
        return self.fmt % {
            "name": record.name,
            "message": record.message,
            "msecs": record.msecs,
            "asctime": record.asctime,
            "levelname": record.levelname,
        }


class Logger:
    def __init__(self, name: str, level: int=NOTSET):
        self.name: str = name
        self.level: int = level
        self.handlers: list[Handler] = []
        self.record: LogRecord = LogRecord()

    def setLevel(self, level: int) -> None:
        self.level = level

    def is_enabled_for(self, level: int) -> bool:
        return level >= self.get_effective_level()

    def get_effective_level(self) -> int:
        return self.level or get_logger().level or _DEFAULT_LEVEL

    def log(self, level: int, msg: str, *args: list[object]|None) -> None:
        if self.is_enabled_for(level):
            if args:
                if isinstance(args[0], dict):
                    args = args[0]
                msg = msg % args
            self.record.set(self.name, level, msg)
            handlers = self.handlers
            if not handlers:
                handlers = get_logger().handlers
            for h in handlers:
                if hasattr(h, "emit"):
                    h.emit(self.record)

    def debug(self, msg: str, *args: None|list[object]) -> None:
        self.log(DEBUG, msg, *args)

    def info(self, msg: str, *args: None|list[object]) -> None:
        self.log(INFO, msg, *args)

    def warning(self, msg: str, *args: None|list[object]) -> None:
        self.log(WARNING, msg, *args)

    def error(self, msg: str, *args: None|list[object]) -> None:
        self.log(ERROR, msg, *args)

    def critical(self, msg: str, *args: None|list[object]) -> None:
        self.log(CRITICAL, msg, *args)

    def exception(self, msg: str, *args: None|list[object], exc_info: BaseException|None=None) -> None:
        self.log(ERROR, msg, *args)
        tb = None
        if isinstance(exc_info, BaseException):
            tb = exc_info
        elif hasattr(sys, "exc_info"):
            tb = sys.exc_info()[1]
        if tb:
            buf = io.StringIO()
            sys.print_exception(tb, buf)
            self.log(ERROR, buf.getvalue())

    def add_handler(self, handler: Handler) -> None:
        self.handlers.append(handler)

    def has_handlers(self) -> bool:
        return len(self.handlers) > 0


def get_logger(name: str|None = None) -> Logger:
    if name is None:
        name = "root"
    if name not in _loggers:
        _loggers[name] = Logger(name)
        if name == "root":
            basic_config()
    return _loggers[name]


def log(level: int, msg: str, *args: None|list[object]) -> None:
    get_logger().log(level, msg, *args)


def debug(msg: str, *args: None|list[object]) -> None:
    get_logger().debug(msg, *args)


def info(msg: str, *args: None|list[object]) -> None:
    get_logger().info(msg, *args)


def warning(msg: str, *args: None|list[object]) -> None:
    get_logger().warning(msg, *args)


def error(msg: str, *args: None|list[object]) -> None:
    get_logger().error(msg, *args)


def critical(msg: str, *args: None|list[object]) -> None:
    get_logger().critical(msg, *args)


def exception(msg: str, *args: None|list[object]) -> None:
    get_logger().exception(msg, *args)


def shutdown() -> None:
    for k, logger in _loggers.items():
        for h in logger.handlers:
            h.close()

        # _loggers.pop(logger, None)
        _loggers.pop(k, None)


def add_level_name(level: int, name: str) -> None:
    _level_dict[level] = name


def basic_config(
    filename: str|None=None,
    filemode: str="a",
    format: str|None=None,
    datefmt: str|None=None,
    level: int=WARNING,
    stream: io.TextIOWrapper|io.IOBase|None=None,
    encoding: str="UTF-8",
    force: bool=False,
) -> None:
    if "root" not in _loggers:
        _loggers["root"] = Logger("root")

    logger = _loggers["root"]

    if force or not logger.handlers:
        for h in logger.handlers:
            h.close()
        logger.handlers = []

        if filename is None:
            handler = StreamHandler(stream)
        else:
            handler = FileHandler(filename, filemode, encoding)

        handler.setLevel(level)
        handler.set_formatter(Formatter(format, datefmt))

        logger.setLevel(level)
        logger.add_handler(handler)


if hasattr(sys, "atexit"):
    sys.atexit(shutdown)