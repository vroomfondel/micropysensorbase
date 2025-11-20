import network
import os
import ubinascii
import logging

try:
    import ujson
except Exception as ex:
    import json as ujson

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DISABLE_INET: bool = False
ENABLE_WATCHDOG: bool = True

# may either be both False or exactly one may be True
UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS: bool = False
REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS: bool = True

logger.debug(f"{UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS=} {REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS=}")

data_orig: dict | None = None
ndata: dict | None = None

data: dict | None = None
data_local: dict | None = None

def save_config():
    ...

def save_local_config():
    ...


def _pprint_format(data) -> str:
    return ujson.dumps(data)


# https://forum.micropython.org/viewtopic.php?t=8112
# © Dave Hylands
def dir_exists(filename):
    try:
        return (os.stat(filename)[0] & 0x4000) != 0
    except OSError:
        return False

# https://forum.micropython.org/viewtopic.php?t=8112
# © Dave Hylands
def file_exists(filename):
    try:
        return (os.stat(filename)[0] & 0x4000) == 0
    except OSError:
        return False

def update_deep(base: dict, u: dict|list|object):
    for k, v in u.items():
        if isinstance(v, dict) or isinstance(v, list):
            base[k] = update_deep(base.get(k, {}), v)
        else:
            base[k] = v
    return base


try:
    with open("esp32config.json") as fp:
        data = ujson.load(fp)
except Exception as ex:
    import sys
    import io

    _out = io.StringIO()
    sys.print_exception(ex)
    sys.print_exception(ex, _out)

    logger.error(_out.getvalue())

if file_exists("esp32config.local.json"):
    try:
        with open("esp32config.local.json") as fp:
            data_local = ujson.load(fp)

            if REPLACE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS:
                data = data_local
            elif UPDATE_CONFIG_WITH_LOCAL_CONFIG_IF_EXISTS:
                update_deep(data, data_local)
    except Exception as ex:
        import sys
        import io

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

mac = ubinascii.hexlify(network.WLAN(network.STA_IF).config('mac'), ':').decode()
mac_no_colon: str = mac.replace(':', '')
logger.debug(f"{mac_no_colon=}")

# mpremote connect /dev/ttyUSB0 mip install pprint
# import mip
# mip.install("pprint")



if mac_no_colon in data:
    logger.info(f"{mac_no_colon=} FOUND in config-data")
    ndata = data[mac_no_colon]
    logger.debug("**************\n" + _pprint_format(data) + "\n***")

    data_orig = ujson.loads(ujson.dumps(data))

    update_deep(data, ndata)

    logger.debug("***\n"+_pprint_format(data)+"\n**************")
else:
    logger.info(f"{mac_no_colon=} not found in config-data")
    logger.debug("**************\n" + _pprint_format(data) + "\n**************")

if "disable_inet" in data and data["disable_inet"]:
    DISABLE_INET = True

if "enable_watchdog" in data and not data["enable_watchdog"]:
    ENABLE_WATCHDOG = False


# TODO: check for stored config-variables on chip ?!
# TODO: improvement fetch (further) config from url with mac/chip-id as parameter ?!

