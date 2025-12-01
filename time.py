import sys


# Replace standard time.localtime()
#
# For more information about extending built in libraries, see:
# https://docs.micropython.org/en/latest/library/index.html#extending-built-in-libraries-from-python

_path = sys.path
sys.path = ()  # type: ignore

try:
    from time import *  # type: ignore
finally:
    sys.path = _path
    del _path

HAD_PROPER_TIME_SET: bool = False
CETTIMEOFFSETHOURS: int | None = None




# https://github.com/micropython/micropython-lib/blob/master/python-stdlib/time/time.py
# copied since logging checks hasattr(time, "strftime") to be abble to work with "%(asctime)" formatting
from micropython import const

_TS_YEAR = const(0)
_TS_MON = const(1)
_TS_MDAY = const(2)
_TS_HOUR = const(3)
_TS_MIN = const(4)
_TS_SEC = const(5)
_TS_WDAY = const(6)
_TS_YDAY = const(7)
_TS_ISDST = const(8)

_WDAY = const(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))
_MDAY = const(
    (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
)


def strftime(datefmt: str, ts: tuple) -> str:
    import io

    fmtsp: bool = False
    ftime: io.StringIO = io.StringIO()

    # assert hasattr(ftime, "write")

    for k in datefmt:
        if fmtsp:
            if k == "a":
                ftime.write(_WDAY[ts[_TS_WDAY]][0:3])
            elif k == "A":
                ftime.write(_WDAY[ts[_TS_WDAY]])
            elif k == "b":
                ftime.write(_MDAY[ts[_TS_MON] - 1][0:3])
            elif k == "B":
                ftime.write(_MDAY[ts[_TS_MON] - 1])
            elif k == "d":
                ftime.write("%02d" % ts[_TS_MDAY])
            elif k == "H":
                ftime.write("%02d" % ts[_TS_HOUR])
            elif k == "I":
                ftime.write("%02d" % (ts[_TS_HOUR] % 12))
            elif k == "j":
                ftime.write("%03d" % ts[_TS_YDAY])
            elif k == "m":
                ftime.write("%02d" % ts[_TS_MON])
            elif k == "M":
                ftime.write("%02d" % ts[_TS_MIN])
            elif k == "P":
                ftime.write("AM" if ts[_TS_HOUR] < 12 else "PM")
            elif k == "S":
                ftime.write("%02d" % ts[_TS_SEC])
            elif k == "w":
                ftime.write(str(ts[_TS_WDAY]))
            elif k == "y":
                ftime.write("%02d" % (ts[_TS_YEAR] % 100))
            elif k == "Y":
                ftime.write(str(ts[_TS_YEAR]))
            else:
                ftime.write(k)
            fmtsp = False
        elif k == "%":
            fmtsp = True
        else:
            ftime.write(k)
    val = ftime.getvalue()
    ftime.close()
    return val


_LAST_SUNDAY_CACHE: dict[tuple[int, int], int] = {}
def last_sunday(year: int, month: int, hour: int, minute: int) -> int:
    """Get the time of the last sunday of the month
    It returns an integer which is the number of seconds since Jan 1, 2000, just like mktime().
    """

    global _LAST_SUNDAY_CACHE
    keytuple: tuple[int, int] = (year, month)

    if keytuple in _LAST_SUNDAY_CACHE:
        return _LAST_SUNDAY_CACHE[keytuple]

    # Get the UTC time of the last day of the month
    seconds = mktime((year, month + 1, 0, hour, minute, 0, None, None))  # type: ignore

    # Calculate the offset to the last sunday of the month
    (year, month, mday, hour, minute, second, weekday, yearday) = gmtime(seconds)  # type: ignore
    offset = (weekday + 1) % 7

    ret: int = mktime((year, month, mday - offset, hour, minute, second, None, None))  # type: ignore
    _LAST_SUNDAY_CACHE[keytuple] = ret

    # Return the time of the last sunday of the month
    return ret


def get_offsethours(year: int, utc_secs: int) -> int:
    """Returns Swedish local time.

        According to [Wikipedia](https://en.wikipedia.org/wiki/Time_in_Sweden)
        does Sweden observe daylight saving time
        from: the last Sunday in March (02:00 CET)
        to:   the last Sunday in October (03:00 CEST)

        => which is also the same rule in Germany btw.
        """

    # Find start date for daylight saving, i.e. last Sunday in March (01:00 UTC)
    start_secs = last_sunday(year=year, month=3, hour=1, minute=0)  # prob. CACHED

    # Find stop date for daylight saving, i.e. last Sunday in October (01:00 UTC)
    stop_secs = last_sunday(year=year, month=10, hour=1, minute=0)  # prob. CACHED

    if utc_secs >= start_secs and utc_secs < stop_secs:
        delta_secs = 2 * 60 * 60  # Swedish summer time (CEST or UTC + 2h)
        mycettimeoffsethours = 2
    else:
        delta_secs = 1 * 60 * 60  # Swedish normal time (CET or UTC + 1h)
        mycettimeoffsethours = 1

    return mycettimeoffsethours

def localtime(secs: int | None = None) -> tuple[int, int, int, int, int, int, int, int, int]:
    """ last int: timeoffset """
    global CETTIMEOFFSETHOURS

    utc_time_tuple = gmtime(secs)  # type: ignore
    utc_secs = mktime(utc_time_tuple)  # type: ignore

    mycettimeoffsethours = get_offsethours(utc_time_tuple[0], utc_secs)

    if not CETTIMEOFFSETHOURS or not HAD_PROPER_TIME_SET:
        CETTIMEOFFSETHOURS = mycettimeoffsethours

    year, month, mday, hour, minute, second, weekday, yearday = gmtime(utc_secs + mycettimeoffsethours * 3600)  # type: ignore

    return year, month, mday, hour, minute, second, weekday, yearday, mycettimeoffsethours  # type: ignore

def getisotime(timestamp_secs: float) -> str:
    dd = localtime(timestamp_secs)  # type: ignore
    offsethours: int = dd[-1]
    return f"{dd[0]:02d}-{dd[1]:02d}-{dd[2]:02d}T{dd[3]:02d}:{dd[4]:02d}:{dd[5]:02d}+{offsethours:02d}:00"

def getisotimenow() -> str:
    dd: float = mktime(gmtime())  # type: ignore
    return getisotime(dd)

def set_had_proper_time_set(timesetproperly: bool = False) -> None:
    """ sets timesetproperly flag and also resets CETTIMEOFFSETHOURS
    in the next call to localtime() the CETTIMEOFFSETHOURS
    is re-calculated since it could be pre-calculated with wrong timeinfo...
    """
    global HAD_PROPER_TIME_SET, CETTIMEOFFSETHOURS
    HAD_PROPER_TIME_SET = timesetproperly
    CETTIMEOFFSETHOURS = None

def get_had_proper_time_set() -> bool:
    global HAD_PROPER_TIME_SET
    return HAD_PROPER_TIME_SET
