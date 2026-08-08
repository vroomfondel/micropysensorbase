"""One-shot migration of a device from the flat install to the mip package layout.

old:  all modules sit directly in /   (import config, import mqttwrap, ...)
new:  /lib/micropysensorbase/*  plus the two shims /boot.py and /main.py

deploy (serial, port free):
    mpremote fs cp migrate_flat_to_package.py :

deploy (device in the field, over WebREPL):
    python webrepl_cli.py -p <pw> migrate_flat_to_package.py <ip>:/migrate_flat_to_package.py

run it on the device:
    import migrate_flat_to_package

The script is idempotent enough to be restarted after an abort: as long as the
rescue boot.py is in place, the device comes back up with wifi and WebREPL.
"""

import json
import os
import sys

# ---------------------------------------------------------------- configuration

# The mipserver index comes from the config ("mip_index") so that no internal
# address has to be committed - the real value belongs into the gitignored
# esp32config.local.json. For a one-off run it can also be set here directly;
# in that case this value wins.
MIP_INDEX: str = ""
PACKAGE: str = "micropysensorbase"
SELF_PATH: str = "/migrate_flat_to_package.py"
WIFI_TIMEOUT_S: int = 30
RESET_WHEN_DONE: bool = True

# modules that must be present in /lib/<PACKAGE>/ after the mip install
REQUIRED: tuple = (
    "__init__",
    "boot",
    "main",
    "config",
    "wifi",
    "logging",
    "meminfo",
    "mqttwrap",
    "measurements",
    "time",
)

BOOT_SHIM: str = "import micropysensorbase.boot\n"

MAIN_SHIM: str = (
    "try:\n"
    "    import micropysensorbase.main\n"
    "    micropysensorbase.main.main()\n"
    "except Exception as ex:\n"
    "    print(ex)\n"
)

# Self-contained boot.py for the migration window: depends on no package at all,
# only brings up wifi and WebREPL so that an unplanned reset does not leave the
# device unreachable.
RESCUE_BOOT: str = '''# temporary rescue boot.py (migrate_flat_to_package.py)
print("RESCUE-BOOT active - migration incomplete")
try:
    import json
    import network
    import ubinascii

    def _merge(base, upd):
        for k in upd:
            v = upd[k]
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _merge(base[k], v)
            else:
                base[k] = v
        return base

    _cfg = {}
    for _fn in ("/esp32config.json", "/esp32config.local.json"):
        try:
            _fp = open(_fn)
            _merge(_cfg, json.load(_fp))
            _fp.close()
        except Exception:
            pass

    _wl = network.WLAN(network.STA_IF)
    _wl.active(True)
    _mac = ubinascii.hexlify(_wl.config("mac")).decode()
    if _mac in _cfg:
        _merge(_cfg, _cfg[_mac])

    if not _wl.isconnected():
        import time
        for _slot in ("wifi1", "wifi2", "wifi3"):
            _w = _cfg.get(_slot)
            if not isinstance(_w, dict) or not _w.get("SSID"):
                continue
            if int(_w.get("retries", 0)) <= 0:
                continue
            print("RESCUE-BOOT connecting to", _w["SSID"])
            _wl.connect(_w["SSID"], _w["password"])
            for _i in range(30):
                if _wl.isconnected():
                    break
                time.sleep(1)
            if _wl.isconnected():
                break

    print("RESCUE-BOOT wlan:", _wl.isconnected(), _wl.ifconfig() if _wl.isconnected() else None)

    import webrepl
    webrepl.start(password=_cfg["webrepl"]["password"])
except Exception as _ex:
    print("RESCUE-BOOT failed:", _ex)
'''


# ---------------------------------------------------------------- helpers


def _is_dir(path: str) -> bool:
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def _exists(path: str) -> bool:
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _update_deep(base: dict, upd: dict) -> dict:
    for k in upd:
        v = upd[k]
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _update_deep(base[k], v)
        else:
            base[k] = v
    return base


def _mac_no_colon() -> str:
    import network
    import ubinascii

    return ubinascii.hexlify(network.WLAN(network.STA_IF).config("mac")).decode()


def write_file(path: str, content: str) -> int:
    """Write, close explicitly, then read back to verify.

    Without close() the content stays in the VFS buffer and is lost on a
    following machine.reset() - the file ends up being 0 bytes.
    """
    fp = open(path, "w")
    try:
        fp.write(content)
    finally:
        fp.close()

    fp = open(path)
    try:
        back: str = fp.read()
    finally:
        fp.close()

    if back != content:
        raise Exception("verification failed for " + path)

    return len(back)


# ---------------------------------------------------------------- steps


def load_config() -> dict:
    """Merge base config, local config and the per-MAC block.

    Has to run before the cleanup: the wifi credentials may live in
    esp32config.json, which gets deleted later on.
    """
    cfg: dict = {}
    for fn in ("/esp32config.json", "/esp32config.local.json"):
        if not _exists(fn):
            continue
        fp = open(fn)
        try:
            _update_deep(cfg, json.load(fp))
        finally:
            fp.close()
        print("  config read:", fn)

    mac: str = _mac_no_colon()
    if mac in cfg:
        print("  per-MAC block found:", mac)
        _update_deep(cfg, cfg[mac])
    else:
        print("  no per-MAC block for", mac)

    return cfg


def cleanup_root(keep: set) -> list:
    removed: list = []
    for name in os.listdir("/"):
        if name in keep:
            continue
        path: str = "/" + name
        if _is_dir(path):
            print("  leaving directory untouched:", path)
            continue
        os.remove(path)
        removed.append(name)
    return removed


def stop_timers() -> None:
    """Silence the periodic callbacks of the old flat install.

    On a running device msgtimer/measuretimer keep firing and would reach into
    already deleted modules during the cleanup. The esp32 has four hardware
    timers; which of them are in use depends on the old revision.
    """
    from machine import Timer

    for i in range(4):
        try:
            Timer(i).deinit()
        except Exception:
            pass


def purge_modules() -> None:
    """Drop the flat modules from sys.modules.

    Otherwise sys.modules["time"] for example keeps pointing at the deleted
    /time.py instead of the built-in module.
    """
    for name in list(sys.modules.keys()):
        mod = sys.modules[name]
        src = getattr(mod, "__file__", "")
        if src and not src.startswith("/lib/") and not src.startswith("."):
            del sys.modules[name]


def connect_wifi(cfg: dict, timeout_s: int = WIFI_TIMEOUT_S) -> bool:
    import network
    import time

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("  wlan was already connected:", wlan.ifconfig()[0])
        return True

    hostname = cfg.get("hostname")
    if isinstance(hostname, str):
        try:
            wlan.config(hostname=hostname)
        except Exception as ex:
            print("  could not set hostname:", ex)

    for slot in ("wifi1", "wifi2", "wifi3"):
        w = cfg.get(slot)
        if not isinstance(w, dict) or not w.get("SSID"):
            continue
        if int(w.get("retries", 0)) <= 0:
            print("  ", slot, "skipped (retries<=0)")
            continue

        print("  connecting to", w["SSID"], "...")
        wlan.connect(w["SSID"], w["password"])
        for _ in range(timeout_s):
            if wlan.isconnected():
                print("  connected:", wlan.ifconfig()[0])
                return True
            time.sleep(1)
        print("  timeout on", w["SSID"])

    return bool(wlan.isconnected())


def resolve_mip_index(cfg: dict) -> str:
    """Determine the index url: the constant in this script beats the config."""
    if MIP_INDEX:
        return MIP_INDEX

    value = cfg.get("mip_index")
    if not isinstance(value, str) or not value.startswith("http"):
        return ""

    return value


def install_package(index: str) -> None:
    import mip

    mip.install(PACKAGE, index=index)


def verify_package() -> list:
    base: str = "/lib/" + PACKAGE
    if not _is_dir(base):
        return ["<" + base + " missing entirely>"]

    entries: list = os.listdir(base)
    stems: set = set()
    for e in entries:
        for suf in (".mpy", ".py"):
            if e.endswith(suf):
                stems.add(e[: -len(suf)])

    missing: list = [m for m in REQUIRED if m not in stems]
    if "esp32config.json" not in entries:
        missing.append("esp32config.json")
    return missing


def umqtt_supports_timeout() -> bool:
    """Check whether umqtt.simple.connect() knows the timeout parameter.

    The server name is empty on purpose: if the parameter is supported,
    connect() only fails later on in getaddrinfo (OSError); if it is missing,
    it already fails on the call itself (TypeError).
    """
    try:
        import umqtt.simple
    except Exception as ex:
        print("  umqtt.simple not importable:", ex)
        return True

    try:
        umqtt.simple.MQTTClient("probe", "").connect(clean_session=True, timeout=1)
    except TypeError:
        return False
    except Exception:
        return True
    return True


# ---------------------------------------------------------------- flow


def migrate() -> None:
    print("=" * 62)
    print("migration flat -> package")
    print("=" * 62)

    print("\n[1/10] reading config (before the cleanup!)")
    cfg: dict = load_config()

    if not _exists("/esp32config.local.json"):
        print("\nABORT: /esp32config.local.json is missing - without those")
        print("       credentials the device would not get back onto the network")
        print("       after the cleanup.")
        return

    if cfg.get("disable_inet"):
        print("\nABORT: disable_inet is set - this device has no network and")
        print("       cannot install via mip. deploy it over serial instead.")
        return

    # deliberately here and not just before the install: without an index the
    # migration is hopeless, and by then / should still be untouched.
    index: str = resolve_mip_index(cfg)
    if not index:
        print("\nABORT: no mipserver index. either put 'mip_index' into")
        print("       esp32config.local.json, e.g.")
        print('         "mip_index": "http://<host>:18891"')
        print("       or set MIP_INDEX at the top of this script.")
        return
    print("  mip index:", index)

    print("\n[2/10] stopping timers of the old install")
    stop_timers()

    print("\n[3/10] writing rescue boot.py")
    print("  ", write_file("/boot.py", RESCUE_BOOT), "bytes")

    print("\n[4/10] cleaning up /")
    keep: set = {"boot.py", "esp32config.json", "esp32config.local.json", SELF_PATH[1:]}
    removed: list = cleanup_root(keep)
    print("  removed:", len(removed), "files")
    print("  remaining:", sorted(os.listdir("/")))

    print("\n[5/10] purging sys.modules")
    purge_modules()

    print("\n[6/10] wlan")
    if not connect_wifi(cfg):
        print("\nABORT: no wlan - mip install not possible.")
        print("       the rescue boot.py is in place, a reset is harmless.")
        return

    print("\n[7/10] mip install from", index)
    install_package(index)

    missing: list = verify_package()
    if missing:
        print("\nABORT: modules missing after the install:", missing)
        print("       the rescue boot.py is in place, a reset is harmless.")
        return
    print("  complete:", sorted(os.listdir("/lib/" + PACKAGE)))

    print("\n[8/10] writing shims and removing the old base config")
    print("   boot.py:", write_file("/boot.py", BOOT_SHIM), "bytes")
    print("   main.py:", write_file("/main.py", MAIN_SHIM), "bytes")
    if _exists("/esp32config.json"):
        os.remove("/esp32config.json")
        print("   /esp32config.json removed (the new one lives in /lib/" + PACKAGE + "/)")

    print("\n[9/10] final checks")
    if not umqtt_supports_timeout():
        print("  WARNING: the umqtt.simple on this device does not know")
        print("           connect(timeout=). That needs mqttwrap.py with the")
        print("           try/except fallback - make sure that revision is")
        print("           pushed and installed, otherwise the device will run")
        print("           into a reboot loop.")
    else:
        print("  umqtt.simple: connect(timeout=) is supported")

    if _exists(SELF_PATH):
        os.remove(SELF_PATH)
        print("  migration script removed")

    print("\n[10/10] done. /:", sorted(os.listdir("/")))

    if RESET_WHEN_DONE:
        print("\nresetting...")
        import machine

        machine.reset()
    else:
        print("\nRESET_WHEN_DONE=False - please run machine.reset() manually")


migrate()
