import sys
import io
import network
from . import config
import machine
import ubinascii

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan_scanlist: list[str] = ["wifi1", "wifi2", "wifi3"]

from micropysensorbase import logging, time

logger = logging.get_logger(__name__)
logger.setLevel(logging.DEBUG)

mac: str = ubinascii.hexlify(network.WLAN().config('mac'), ':').decode()  # type: ignore
mac_no_colon: str = mac.replace(':', '')
logger.info(f"MAC: {mac}")

# wlan.config(reconnects=5)

if "hostname" in config.data:
    wlan.config(hostname=config.data['hostname'])
elif "hostnameprefix" in config.data:
    wlan.config(hostname=f"{config.data['hostnameprefix']}{mac_no_colon}")
else:
    wlan.config(hostname=f"esp32_{mac_no_colon}")

boot_ssd_enabled: bool = False

if "boot_ssd" in config.data and config.get_config_data_bool(config.data, "boot_ssd"):
    try:
        import boot_ssd
        boot_ssd_enabled = True
    except Exception as ex:
        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())


def get_wifi_strength() -> object|None:
    global wlan
    try:
        return wlan.status('rssi')

    except Exception as ex:
        logger.exception(str(ex))
        return None

def get_wifi_scan() -> list[dict]|None:
    global wlan
    ret: list[dict] = []
    try:
        scaninfo = wlan.scan()
        for i in scaninfo:
            ssid, bssid, channel, RSSI, authmode, hidden = i
            bssid_s = ubinascii.hexlify(bssid)

            ret.append({"ssid": ssid, "bssid": bssid_s, "channel": channel, "rssi": RSSI})
            logger.info(f"{ssid=} bssid={bssid_s} {channel=} {RSSI=} {authmode=} {hidden=}")
    except Exception as ex:
        return None

    return ret

def get_wifi_config() -> dict:
    global wlan
    global mac
    ret: dict = {"mac": None, "ssid": None, "channel": None, "reconnects": None, "hostname": None}

    #logger.info(wlan.config())

    for k in ret.keys():
        if k == "mac":
            ret[k] = mac
        else:
            ret[k] = wlan.config(k)

    return ret

def ensure_wifi(watchdog: machine.WDT|None = None) -> tuple|None:
    # global data
    global wlan, wlan_scanlist, boot_ssd_enabled

    ret: tuple | None = None if not wlan.isconnected else wlan.ifconfig()

    if watchdog:
        watchdog.feed()

    while not wlan.isconnected():
        for w in wlan_scanlist:
            if wlan.isconnected():
                break

            if w not in config.data:
                continue

            _bssid = None
            _bestrssi = None
            scaninfo = wlan.scan()
            wanted_ssid: str = config.get_config_data_str(config.get_config_data_dict(config.data, w), "SSID")
            for i in scaninfo:
                ssid, bssid, channel, RSSI, authmode, hidden = i
                if ssid.decode('utf-8') == wanted_ssid:
                    if _bestrssi:
                        if _bestrssi < RSSI:
                            logger.info(f"BEST ONE SO FAR:: {ssid=} bssid={ubinascii.hexlify(bssid)} {channel=} {RSSI=} {authmode=} {hidden=}")
                            _bestrssi = RSSI
                            _bssid = bssid
                    else:
                        logger.info(f"INITIAL:: {ssid=} bssid={ubinascii.hexlify(bssid)} channel={channel} RSSI={RSSI} authmode={authmode} hidden={hidden}")
                        _bestrssi = RSSI
                        _bssid = bssid

            if _bssid is None:
                logger.info(
                    f'connecting to network {wanted_ssid} bssid=NONE...')  # or just scan and connect to best ?!
            else:
                logger.info(
                    f'connecting to network {wanted_ssid} bssid={ubinascii.hexlify(_bssid)}...')  # or just scan and connect to best ?!

            apssid = wanted_ssid  # config.data[w]["SSID"]

            try:
                if boot_ssd_enabled and boot_ssd.ssd:
                    boot_ssd.ssd.fill(0)
                    boot_ssd.ssd.text(f"Connecting WiFi", 0, 0, 1)
                    boot_ssd.ssd.text(f"SSID: {apssid}", 0, 9, 1)
                    boot_ssd.ssd.show()
            except Exception as exx:
                logger.error(str(exx))

            pw: str = config.get_config_data_str(config.get_config_data_dict(config.data, w), "password")
            retries: int = config.get_config_data_int(config.get_config_data_dict(config.data, w), "retries")

            wlan.connect(apssid, pw, bssid=_bssid)
            for _ in range(retries):
                if watchdog:
                    watchdog.feed()

                if wlan.isconnected():
                    ret = wlan.ifconfig()
                    logger.info(f'network config: wlan.ifconfig()={ret}')  # (ip, subnet, gateway, dns)
                    logger.info(f"WIFI-Strength: wlan.status('rssi')={wlan.status('rssi')}")
                    # wlan.status()
                    # ensureWEBREpl()

                    try:
                        if boot_ssd_enabled and boot_ssd.ssd:
                            boot_ssd.ssd.text(f"Connected.", 0, 18, 1)
                            boot_ssd.ssd.show()
                    except Exception as exx:
                        logger.error(str(exx))

                    break
                else:
                    time.sleep(1)  # type: ignore[attr-defined]
            else:
                logger.info("disonnecting WIFI")
                wlan.disconnect()

    return ret

def ensure_wifi_catch_reset(reset_if_wifi_fails: bool = True, watchdog: machine.WDT|None = None) -> tuple:
    try:
        ret: tuple|None = ensure_wifi(watchdog=watchdog)
        if ret is None:
            raise Exception("WIFI FAILED")
        return ret
    except Exception as ex:
        _timestring = time.getisotimenow()

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

        if reset_if_wifi_fails:
            logger.info("RESETTING... in 60s")
            if watchdog:
                logger.info("\tor earlier if watchdog kicks in...")
            time.sleep(60)  # type: ignore[attr-defined]
            machine.reset()

    return None, None, None, None, None

def start_web_repl() -> None:
    import webrepl
    webrepl.start(password=config.data["webrepl"]["password"])  #type: ignore

