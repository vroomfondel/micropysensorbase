import time
import sys
import io
import network
import config
import machine
import ubinascii

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan_scanlist: list[str] = ["wifi1", "wifi2", "wifi3"]

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

mac = ubinascii.hexlify(network.WLAN().config('mac'), ':').decode()
mac_no_colon: str = mac.replace(':', '')
logger.info(f"MAC: {mac}")

# wlan.config(reconnects=5)

if "hostname" in config.data:
    wlan.config(hostname=config.data['hostname'])
elif "hostnameprefix" in config.data:
    wlan.config(hostname=f"{config.data['hostnameprefix']}{mac_no_colon}")
else:
    wlan.config(hostname=f"esp32_{mac_no_colon}")

try:
    import boot_ssd
except Exception as ex:
    _out = io.StringIO()
    sys.print_exception(ex)
    sys.print_exception(ex, _out)

    logger.error(_out.getvalue())


def get_wifi_strength():
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

def ensure_wifi() -> tuple|None:
    # global data
    global wlan, wlan_scanlist

    ret: tuple | None = None if not wlan.isconnected else wlan.ifconfig()

    while not wlan.isconnected():
        for w in wlan_scanlist:
            if wlan.isconnected():
                break

            if w not in config.data:
                continue

            _bssid = None
            _bestrssi = None
            scaninfo = wlan.scan()
            for i in scaninfo:
                ssid, bssid, channel, RSSI, authmode, hidden = i
                if ssid.decode('utf-8') == config.data[w]["SSID"]:
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
                    f'connecting to network {config.data[w]["SSID"]} bssid=NONE...')  # or just scan and connect to best ?!
            else:
                logger.info(
                    f'connecting to network {config.data[w]["SSID"]} bssid={ubinascii.hexlify(_bssid)}...')  # or just scan and connect to best ?!

            apssid = config.data[w]["SSID"]

            try:
                if boot_ssd.ssd:
                    boot_ssd.ssd.fill(0)
                    boot_ssd.ssd.text(f"Connecting WiFi", 0, 0, 1)
                    boot_ssd.ssd.text(f"SSID: {apssid}", 0, 9, 1)
                    boot_ssd.ssd.show()
            except Exception as exx:
                logger.error(str(exx))

            wlan.connect(apssid, config.data[w]["password"], bssid=_bssid)
            for _ in range(config.data[w]["retries"]):
                if wlan.isconnected():
                    ret = wlan.ifconfig()
                    logger.info(f'network config: wlan.ifconfig()={ret}')  # (ip, subnet, gateway, dns)
                    logger.info(f"WIFI-Strength: wlan.status('rssi')={wlan.status('rssi')}")
                    # wlan.status()
                    # ensureWEBREpl()

                    try:
                        if boot_ssd.ssd:
                            boot_ssd.ssd.text(f"Connected.", 0, 18, 1)
                            boot_ssd.ssd.show()
                    except Exception as exx:
                        logger.error(str(exx))

                    break
                else:
                    time.sleep(1)
            else:
                logger.info("disonnecting WIFI")
                wlan.disconnect()

    return ret

def ensure_wifi_catch_reset(reset_if_wifi_fails: bool = True) -> tuple:
    try:
        return ensure_wifi()
    except Exception as ex:
        _timestring = time.getisotimenow()

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

        if reset_if_wifi_fails:
            logger.info("RESETTING... in 30s")
            time.sleep(30)
            machine.reset()

def start_web_repl():
    import webrepl
    webrepl.start(password=config.data["webrepl"]["password"])  #type: ignore

