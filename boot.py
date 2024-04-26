# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
import time

# battery-voltage-check
# https://www.youtube.com/watch?v=5JIJO1swQPE
# https://www.xtronical.com/

# https://docs.micropython.org/en/latest/library/machine.html
# machine.reset()
#Resets the device in a manner similar to pushing the external RESET button.

#machine.soft_reset()
#Performs a soft reset of the interpreter, deleting all Python objects and resetting the Python heap. It tries to retain the method by which the user is connected to the MicroPython REPL (eg #serial, USB, Wifi).

# CHECK: https://github.com/micropython/micropython-lib?tab=readme-ov-file

# replace time.localtime() system-wide:
# https://github.com/orgs/micropython/discussions/11173
# https://docs.micropython.org/en/latest/library/index.html#extending-built-in-libraries-from-python

# mip install modules!
# https://github.com/micropython/micropython-lib

import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


import config

if "boot_ssd" in config.data and config.data["boot_ssd"]:
    try:
        import boot_ssd
        boot_ssd.setup()
    except Exception as ex:
        import sys
        import io

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())
        time.sleep(2)



if "disable_inet" not in config.data or not config.data["disable_inet"]:
    import wifi
    wifi.ensure_wifi()
    wifi.start_web_repl()

    import ntptime
    for i in range(10):
        try:
            ntptime.settime()
            time.set_had_proper_time_set(True)
            break
        except Exception as ex:
            import sys
            import io

            _out = io.StringIO()
            sys.print_exception(ex)
            sys.print_exception(ex, _out)

            logger.error(_out.getvalue())
            time.sleep(2)
else:
    logger.info("INET DISABLED... NO NTPTIME ETC...")

import meminfo
meminfo.main()

# https://forum.micropython.org/viewtopic.php?f=2&t=4034
# # Micropython esp8266
# # This code returns the Central European Time (CET) including daylight saving
# # Winter (CET) is UTC+1H Summer (CEST) is UTC+2H
# # Changes happen last Sundays of March (CEST) and October (CET) at 01:00 UTC
# # Ref. formulas : http://www.webexhibits.org/daylightsaving/i.html
# #                 Since 1996, valid through 2099
#
# import utime

# def get_cet_timeoffset() -> int:
#     year = utime.localtime()[0]       #get current year
#     HHMarch   = utime.mktime((year, 3, (31-(int(5*year/4+4)) % 7), 1, 0, 0, 0, 0)) #Time of March change to CEST  # (year, month, mday, hour, minute, second, weekday, yearday)
#     HHOctober = utime.mktime((year, 10, (31-(int(5*year/4+1)) % 7), 2, 0, 0, 0, 0)) #Time of October change to CET # (year, month, mday, hour, minute, second, weekday, yearday)
#     now = utime.time()
#     if now < HHMarch:               # we are before last sunday of march
#         return 3600  # CET:  UTC+1H
#     elif now < HHOctober:           # we are before last sunday of october
#         return 7200  # CEST: UTC+2H
#     else:                            # we are after last sunday of october
#         return 3600  # CET:  UTC+1H
#
# # https://github.com/micropython/micropython-lib
#
# cettimeoffsetseconds = get_cet_timeoffset()
#
# print(f"{cettimeoffsetseconds=}")

# ntptime.NTP_DELTA -= cettimeoffsetseconds
# ntptime.settime()  # reset with correct timezone | needed first call to detect month

# boottime = utime.time()
# print("boot.py :: local_boottime: ", utime.localtime(boottime))
# print("boot.py :: utime.time(): ", boottime)

import machine
rc = machine.reset_cause()

if rc == machine.PWRON_RESET:
    logger.info("RESET CAUSE :: PWRON_RESET")

if rc == machine.HARD_RESET:
    logger.info("RESET CAUSE :: HARD_RESET")

if rc == machine.WDT_RESET:
    logger.info("RESET CAUSE :: WDT_RESET")

if rc == machine.DEEPSLEEP_RESET:
    logger.info("RESET CAUSE :: DEEPSLEEP_RESET")

if rc == machine.SOFT_RESET:
    logger.info("RESET CAUSE :: SOFT_RESET")

logger.info("BOOT DONE")
