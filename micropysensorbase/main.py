import gc
import io
import sys

from micropysensorbase import logging, time
from micropysensorbase.time import sleep  # type: ignore[attr-defined]
from machine import Timer, WDT
import machine

import mqttwrap
import wifi
import config

import _thread

DISABLED_AUTO_SETUP: bool = False

logger = logging.get_logger(__name__)
logger.setLevel(logging.INFO)

if __name__ in config.get_config_data_dict(config.data, "loglevel"):
    melv: int|None = logging.get_log_level_by_name(
        config.get_config_data_str(config.get_config_data_dict(config.data, "loglevel"), "main"))
    if melv is not None:
        logger.setLevel(melv)

mainc: int = 0
logger.debug(f"main.py::{mainc}::STARTING")
mainc += 1


DISABLE_INET: bool = False

if "disable_inet" in config.data and config.get_config_data_bool(config.data, "disable_inet"):
    DISABLE_INET = True

if "disable_autosetup" in config.data:
    if config.get_config_data_bool(config.data, "disable_autosetup"):
        DISABLED_AUTO_SETUP = True
        logger.info(f"{DISABLED_AUTO_SETUP=} ENABLED")
    else:
        logger.info(f"{DISABLED_AUTO_SETUP=}")
else:
    logger.info(f"{DISABLED_AUTO_SETUP=} since not found in config")


msgtimer: Timer = Timer(0)
measuretimer: Timer = Timer(1)
reboottimer: Timer = Timer(2)
# esp32: four hardware-timers available

lock: _thread.LockType | config.DummyLock = config.DummyLock(name="main", loglevel=logging.INFO)
WATCHDOG: WDT|None = None

def reboot_callback(_: object=None) -> None:
    micropython.schedule(reboot_trigger, None)


def reboot_trigger(_: object=None) -> None:
    timestring: str = time.getisotimenow()
    logger.info(f"{timestring}::rebooting...")
    if mqttwrap is not None:
        mqttwrap.publish_one(
            topic=mqttwrap.get_feed("loggingfeed"),
            msg=f"rebooting at {timestring}",
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )
    machine.reset()


def check_msgs(_: object=None) -> None:
    global lock, DISABLE_INET, WATCHDOG

    if WATCHDOG:
        WATCHDOG.feed()

    if DISABLE_INET:
        return

    logger.debug("check_msgs")

    if lock.locked():
        logger.debug("main.py()::check:msgs::already LOCKED...")
        return

    acquired: bool = False
    try:
        acquired = lock.acquire()
        # timeout not implemented https://github.com/micropython/micropython/issues/3332
    except Exception as ex:
        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

    gc.collect()

    if acquired:
        logger.debug("main.py()::check:msgs::lock acquired...")
        try:
            #with lock:
            logger.debug("main.py()::check:msgs::LOCK acquired...")
            wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True, watchdog=WATCHDOG)
            if WATCHDOG:
                WATCHDOG.feed()

            logger.debug("main.py()::check:msgs::ensuring mqtt_connect...")
            mqttwrap.ensure_mqtt_catch_reset(reset_if_mqtt_fails=True, watchdog=WATCHDOG)
            if WATCHDOG:
                WATCHDOG.feed()

            logger.debug("main.py()::check:msgs::check_msgs called...")
            mqttwrap.check_msgs(reset_if_mqtt_fails=True, watchdog=WATCHDOG)  # check for connect-error!
            if WATCHDOG:
                WATCHDOG.feed()

            ts_cmd_arg: tuple[int, str, str | None] | None

            while True:
                logger.debug("main.py()::check:msgs::while...")
                ts_cmd_arg = mqttwrap.pop_cmd_received()
                if ts_cmd_arg is None:
                    break

                cmd: str = ts_cmd_arg[1]
                if cmd == "reboot" or cmd == "reset":
                    logger.info("reboot command received...")
                    reboot_trigger()
                elif cmd == "switchap":
                    logger.info("switchap command received...")
                elif cmd == "rescanwifi":
                    logger.info("rescanwifi command received...")
                else:
                    logger.warning(f"unknown command: {cmd} arg={ts_cmd_arg[2]}")

        except Exception as ex:
            _out = io.StringIO()
            sys.print_exception(ex)
            sys.print_exception(ex, _out)

            logger.error(_out.getvalue())
    else:
        # not lock acquired
        logger.debug("main.py()::check:msgs::lock NOT acquired...")
        return

    lock.release()

    if WATCHDOG:
        WATCHDOG.feed()


def check_msgs_callback(_: object=None) -> None:
    global WATCHDOG
    # logger.debug(f"{type(trigger)=} {trigger=}")
    # DEBUG:__main__:type(trigger)=<class 'Timer'> trigger=Timer(0, mode=PERIODIC, period=3000)

    micropython.schedule(check_msgs, None)

    if WATCHDOG:
        WATCHDOG.feed()

############################# end of boilerplate #############################

logger.debug(f"main.py::{mainc}::After boilerplate")
mainc += 1

# MEASURE_TELE_PERIOD: int = 300
MEASURE_TELE_PERIOD_S: int = 60
CHCKMSGS_PERIOD_MS: int = 3_000
MEASURETIMER_PERIOD_MS: int = 10_000

if "measure_tele_period_s" in config.data:
    MEASURE_TELE_PERIOD_S = config.get_config_data_int(config.data, "measure_tele_period_s")
if "chckmsgs_period_ms" in config.data:
    CHCKMSGS_PERIOD_MS = config.get_config_data_int(config.data, "chckmsgs_period_ms")
if "measuretimer_period_ms" in config.data:
    MEASURETIMER_PERIOD_MS = config.get_config_data_int(config.data, "measuretimer_period_ms")

logger.debug(f"main.py::{mainc}::Before setup definition")
mainc += 1

def setup() -> None:
    global msgtimer, measuretimer, MEASURETIMER_PERIOD_MS, CHCKMSGS_PERIOD_MS
    global DISABLE_INET, WATCHDOG, lock

    if config.ENABLE_WATCHDOG:
        WATCHDOG = WDT(timeout=30_000)

    if config.ENABLE_LOCK:
        lock = _thread.allocate_lock()

    logger.debug("main::setup()")

    check_msgs()

    if WATCHDOG:
        WATCHDOG.feed()

    msgtimer.init(
        period=CHCKMSGS_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=check_msgs_callback
    )

    # better put that classes
    import measurements
    measurements.WATCHDOG = WATCHDOG
    if config.ENABLE_LOCK:
        measurements.lock = _thread.allocate_lock()

    measurements.DISABLE_INET = DISABLE_INET

    import micropython

    micropython.mem_info()
    measurements.setup_pins()
    micropython.mem_info()


    if WATCHDOG:
        WATCHDOG.feed()

    # measurement will be executed each MEASURETIMER_PERIOD_MS; MEASURE_TELE_PERIOD will be checked if "overdue";
    # also if threshold since last sent measurement is exceeeded
    # better put internals (ina etc. into method/class)
    if measurements.ina is not None or measurements.dht11 is not None or measurements.dht22 is not None:
        measuretimer.init(
            period=MEASURETIMER_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=measurements.measure_callback
        )


    if config.get_config_data_int(config.data, "forcerestart_after_running_seconds") > 0:
        reboottimer.init(
            period=config.get_config_data_int(config.data, "forcerestart_after_running_seconds") * 1_000,
            mode=machine.Timer.ONE_SHOT,
            callback=reboot_callback,
        )

    # tim2 = Timer(-1)
    # tim2.init(period=30000, mode=Timer.PERIODIC, callback=lambda t: mqttclient.ping())
    # tim.deinit()

    if WATCHDOG:
        WATCHDOG.feed()

def whoami() -> str:
    ret: str = wifi.wlan.config("hostname") + "\t" + mqttwrap.boottime_local_str
    logger.info(ret)
    return ret


def setup_wifi_and_mqtt(mqtt_connect_timeout_s: int| None=30) -> None:
    global mainc

    import meminfo

    if not DISABLE_INET:
        logger.debug(f"main.py::{mainc}::BEFORE wifi.ensure_wifi_catch_reset()")
        mainc += 1

        wifi.ensure_wifi_catch_reset()  # without WATCHDOG for the first run!

        meminfo.main()

        logger.debug(f"main.py::{mainc}::BEFORE mqttwrap.ensure_mqtt_catch_reset()")
        mainc += 1
        mqttwrap.ensure_mqtt_catch_reset(watchdog=None, mqtt_connect_timeout_s=mqtt_connect_timeout_s)  # without WATCHDOG for the first run!

    logger.debug(f"main.py::{mainc}::After INET_CHECK")
    mainc += 1

def main() -> None:
    logger.debug("START::main.py::main()")

    from measurements import main as measurements_main
    measurements_main()

    logger.debug("DONE::main::main()")


logger.debug(f"main.py::{mainc}::Before __name__ == \"__main__\"")
mainc += 1

if __name__ == "__main__":
    import micropython

    micropython.mem_info()
    setup_wifi_and_mqtt()
    micropython.mem_info()

    if DISABLED_AUTO_SETUP:
        logger.debug("DISABLED AUTO SETUP")
    else:
        logger.debug("main.py::calling setup()")
        setup()  # also calls setup_pins
        logger.debug("main.py::setup() done.")

        logger.debug("main.py::calling main()")
        main()
        logger.debug("main.py::main() done.")

