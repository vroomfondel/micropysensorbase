import os
import sys
import json

import gc

IS_MICROPYTHON: bool = sys.implementation.name == "micropython"

mac: str = "UNDEFINED"

if IS_MICROPYTHON:
    import network
    import ubinascii

    mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config('mac'), ':').decode()
    del ubinascii
else:
    pass

mac_no_colon: str = mac.replace(':', '')

from micropysensorbase import logging

logger = logging.get_logger(__name__)
logger.setLevel(logging.INFO)

logger.info(f"DETECTED IMPLEMENTATION {sys.implementation.name=} => {IS_MICROPYTHON=}")
INTVERSION = sys.implementation.version[0]*100 + sys.implementation.version[1]
logger.info(f"DETECTED VERSION {sys.implementation.version=} => {INTVERSION}")


# if __name__ in config.get_config_data_dict(config.data, "loglevel"):
#     melv: int|None = logging.get_log_level_by_name(config.get_config_data_str(config.get_config_data_dict(config.data, "loglevel"), "config"))
#     if melv is not None:
#         logger.setLevel(melv)

DISABLE_INET: bool = False
ENABLE_WATCHDOG: bool = True
ENABLE_LOCK: bool = True

# may either be both False or exactly one may be True
UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS: bool = True
REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS: bool = False

logger.debug(f"{UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS=} {REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS=}")



# data_orig: dict | None = None
# ndata: dict | None = None

data: dict[str, str|float|int|bool|dict[str, str|float|int|bool]] = {}
# data_local: dict[str, str|float|int|bool|dict[str, str|float|int|bool]] = {}

class DummyLock:
    def __init__(self, name: str, loglevel: int = logging.INFO):
        self.name = name

        self.logger = logging.get_logger(f"DummyLock::{name}")
        self.logger.setLevel(loglevel)

        self.logger.debug(f"DummyLock::{self.name}.init")

    def __enter__(self) -> None:
        self.logger.debug(f"DummyLock::{self.name}.enter")

    def __exit__(self, type: object, value: object, traceback: BaseException) -> None:
        self.logger.debug(f"DummyLock::{self.name}.exit::{type=} {value=} {traceback=}")

    def locked(self) -> bool:
        self.logger.debug(f"DummyLock::{self.name}.locked()")
        return True

    def acquire(self, *args: object, **kwargs: object) -> bool:
        self.logger.debug(f"DummyLock::{self.name}.acquire()")
        return True

    def release(self, *args: object, **kwargs: object) -> None:
        self.logger.debug(f"DummyLock::{self.name}.release()")
        return

def _pprint_format(mydata: dict) -> str:
    # item-sep, key-sep
    return json.dumps(mydata, separators=(",\n", ": "))

# https://forum.micropython.org/viewtopic.php?t=8112
# © Dave Hylands
def dir_exists(filename: str) -> bool:
    try:
        return (os.stat(filename)[0] & 0x4000) != 0
    except OSError:
        return False

# https://forum.micropython.org/viewtopic.php?t=8112
# © Dave Hylands
def file_exists(filename: str) -> bool:
    try:
        return (os.stat(filename)[0] & 0x4000) == 0
    except OSError:
        return False

def update_deep(base: dict|list, u: dict|list) -> dict|list:
    if isinstance(u, dict):
        for k, v in u.items():
            if isinstance(v, dict):
                if isinstance(base, dict):
                    base[k] = update_deep(base.get(k, {}), v)
                else:
                    raise Exception(f"unknown 1 {type(base)=} vs. {type(v)=}")
            elif isinstance(v, list):
                raise Exception(f"unknown 2 {type(base)=} vs. {type(v)=}")
                # liste durchgehen?!
                # base[k] = update_deep(base.get(k, {}), v)
            elif isinstance(base, dict):
                base[k] = v
            else:
                raise Exception(f"unknown 3 {type(base)=} vs. {type(v)=}")
    elif isinstance(u, list):
        if isinstance(u, list):
            base = u
        else:
            raise Exception(f"unknown 4 {type(base)=} vs. {type(u)=}")

    return base


try:
    with open("esp32config.json") as fp:
        data = json.load(fp)
except Exception as ex:
    import sys
    import io

    _out = io.StringIO()
    sys.print_exception(ex)
    sys.print_exception(ex, _out)

    logger.error(_out.getvalue())

for lf in ["/esp32config.local.json", "../esp32config.local.json", "esp32config.local.json"]:
    if file_exists(lf):
        logger.info(f"Loading {lf}")
        try:
            with open(lf) as fp:
                data_local = json.load(fp)

                if REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS:
                    data = data_local
                elif UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS and data is not None:
                    data = update_deep(data, data_local)  # type: ignore

                del data_local


        except Exception as ex:
            import sys
            import io

            _out = io.StringIO()
            sys.print_exception(ex)
            sys.print_exception(ex, _out)

            logger.error(_out.getvalue())

        break



logger.debug(f"{mac_no_colon=}")

# mpremote connect /dev/ttyUSB0 mip install pprint
# import mip
# mip.install("pprint")


if data is None:
    data = {}

if mac_no_colon in data:
    logger.info(f"{mac_no_colon=} FOUND in config-data")
    ndata = data[mac_no_colon]  # type: ignore
    # logger.debug("**************\n" + _pprint_format(data) + "\n***")

    # data_orig = json.loads(json.dumps(data))

    update_deep(data, ndata)  # type: ignore

    #logger.debug("***\n"+_pprint_format(data)+"\n**************")
else:
    logger.info(f"{mac_no_colon=} not found in config-data")

logger.debug("**************\n" + _pprint_format(data) + "\n**************")


if "disable_inet" in data and data["disable_inet"]:
    DISABLE_INET = True

if "enable_watchdog" in data and not data["enable_watchdog"]:
    ENABLE_WATCHDOG = False

if "enable_lock" in data and not data["enable_lock"]:
    ENABLE_LOCK = False

logger.info(f"config.{ENABLE_LOCK=}")

dlogger = logging.get_logger("config_get_config")
dlogger.setLevel(logging.INFO)
def get_config_data_str(_data: dict[str, str|float|int|bool]|dict[str, str|float|int|bool|dict[str, str|float|int|bool]], name: str) -> str:
    dlogger.debug(f"config.py::get_config_data_str({name=}) from {_data}")
    assert _data is not None and name in _data, f"FAIL::config.py::get_config_data_str({name=}) from {_data}"
    ret: object = _data[name]
    assert isinstance(ret, str)
    return ret

def get_config_data_dict(_data: dict[str, str|float|int|bool|dict[str, str|float|int|bool]], name: str) -> dict[str, str|float|int|bool]:
    dlogger.debug(f"config.py::get_config_data_dict({name=}) from {_data}")
    assert _data is not None and name in _data, f"FAIL::config.py::get_config_data_dict({name=}) from {_data}"
    ret: object = _data[name]
    assert isinstance(ret, dict)
    return ret

def get_config_data_float(_data: dict[str, str|float|int|bool]|dict[str, str|float|int|bool|dict[str, str|float|int|bool]], name: str) -> float:
    dlogger.debug(f"config.py::get_config_data_float({name=}) from {_data}")
    assert _data is not None and name in _data, f"FAIL::config.py::get_config_data_float({name=}) from {_data}"
    ret: object = _data[name]
    assert isinstance(ret, float)
    return ret

def get_config_data_int(_data: dict[str, str|float|int|bool]|dict[str, str|float|int|bool|dict[str, str|float|int|bool]], name: str) -> int:
    dlogger.debug(f"config.py::get_config_data_int({name=}) from {_data}")
    assert _data is not None and name in _data, f"FAIL::config.py::get_config_data_int({name=}) from {_data}"
    ret: object = _data[name]
    assert isinstance(ret, int)
    return ret

def get_config_data_bool(_data: dict[str, str|float|int|bool]|dict[str, str|float|int|bool|dict[str, str|float|int|bool]], name: str) -> bool:
    dlogger.debug(f"config.py::get_config_data_bool({name=}) from {_data}")
    assert _data is not None and name in _data, f"FAIL::config.py::get_config_data_bool({name=}) from {_data}"
    ret: object = _data[name]
    assert isinstance(ret, bool)
    return ret

# TODO: check for stored config-variables on chip ?!
# TODO: improvement fetch (further) config from url with mac/chip-id as parameter ?!

gc.collect()

if __name__ == "__main__":
    logger.info(__package__)
    logger.info("__main__")