import config
import wifi

import time
import machine
import sys
import io

import logging
logger = logging.get_logger(__name__)
logger.setLevel(logging.INFO)

if __name__ in config.get_config_data_dict(config.data, "loglevel"):
    melv: int|None = logging.get_log_level_by_name(config.get_config_data_str(config.get_config_data_dict(config.data, "loglevel"), "mqttwrap"))
    if melv is not None:
        logger.setLevel(melv)

from umqtt.simple import MQTTClient as MQTTClientSimple
# from umqtt.robust import MQTTClient as MQTTClientRobust

#### needed for retain-bit ####
# from umqtt.simple import MQTTException
# taken from https://github.com/micropython/micropython-lib/blob/master/micropython/umqtt.simple/umqtt/simple.py
# and adapted
# import socket
# import struct
# from binascii import hexlify
# class MQTTClientSimple(umqtt.simple.MQTTClient):
#     # Wait for a single incoming MQTT message and process it.
#     # Subscribed messages are delivered to a callback previously
#     # set by .set_callback() method. Other (internal) MQTT
#     # messages processed internally.
#     def wait_msg(self):
#         res = self.sock.read(1)
#         self.sock.setblocking(True)
#         if res is None:
#             return None
#         if res == b"":
#             raise OSError(-1)
#         if res == b"\xd0":  # PINGRESP
#             sz = self.sock.read(1)[0]
#             assert sz == 0
#             return None
#         op = res[0]
#         if op & 0xF0 != 0x30:
#             return op
#         sz = self._recv_len()
#         topic_len = self.sock.read(2)
#         topic_len = (topic_len[0] << 8) | topic_len[1]
#         topic = self.sock.read(topic_len)
#         sz -= topic_len + 2
#         if op & 6:
#             pid = self.sock.read(2)
#             pid = pid[0] << 8 | pid[1]
#             sz -= 2
#
#         msg = self.sock.read(sz)
#
#         # do not ignore retained
#         retained = op & 0x01
#
#         if self.cb is not None:
#             self.cb(topic, msg, retained == 1)
#
#         if op & 6 == 2:
#             pkt = bytearray(b"\x40\x02\0\0")
#             struct.pack_into("!H", pkt, 2, pid)
#             self.sock.write(pkt)
#         elif op & 6 == 4:
#             assert 0
#         return op



import _thread

lock: _thread.LockType | config.DummyLock = config.DummyLock(name="mqttwrap", loglevel=logging.INFO)
if config.ENABLE_LOCK:
    lock = _thread.allocate_lock()

TELE_PERIOD: int = 60

last_status_gmt: float | None = None

import json
import socket


boottime_gmt: float = time.mktime(time.gmtime())  # type: ignore[attr-defined]
boottime_local_str = time.getisotime(boottime_gmt)

_lastping: int = time.time()  # type: ignore[attr-defined]

_mqttclient: MQTTClientSimple | None = None
_keepalive: int = 60
_controlfeed: str | None = None
_received_commands: list[tuple[int, str, str | None]] = []


def get_client_id() -> str:
    return f"esp32_{wifi.mac_no_colon}"
    # import machine
    # return hexlify(machine.unique_id())


def format_with_clientid(topic: str) -> str:
    return topic.format(clientid=get_client_id())


def get_feed(feedname: str) -> str:
    mos: dict[str, str|float|int] = config.data["mosquitto"]  # type: ignore
    fn: str = mos[feedname]  # type: ignore
    return format_with_clientid(fn)


mosquitto_to_send_base_data: dict = {
    "lat": config.data["mosquitto"]["lat_loc2"],  # type: ignore
    "lon": config.data["mosquitto"]["lon_loc2"],  # type: ignore
    "ele": config.data["mosquitto"]["ele_loc2"],  # type: ignore
}


def pop_cmd_received() -> tuple[int, str, str | None] | None:
    if len(_received_commands) > 0:
        r: tuple[int, str, str | None] = _received_commands.pop(0)
        return r

    return None


def sub_cb(_topic: bytes, _msg: bytes, retained: bool|None = None) -> None:
    global _lastping

    logger.debug(f"mqttwrap::sub_cb:called {_topic=} {_msg=} {retained=}")

    _lastping = time.time()  # type: ignore

    msg: str = _msg.decode("utf-8")
    topic = _topic.decode("utf-8")
    logger.info(f"{topic=} {msg=} {retained=}")

    if topic == _controlfeed:
        cmd_arg = msg.split(None, 1)
        cmd: str = cmd_arg[0]
        arg: str | None = None

        if len(cmd_arg) > 1:
            arg = cmd_arg[1]

        logger.info(f"received {cmd=} {arg=} {retained=}")
        if not retained:
            _received_commands.append((_lastping, cmd, arg))


def get_ip(host: str, port: int = 80) -> str:
    addr_info: list[tuple[int, int, int, str, tuple[str, int] | tuple[str, int, int, int]]] = socket.getaddrinfo(host, port)
    # fe: tuple[int, int, int, str, tuple[str, int] | tuple[str, int, int, int]] = addr_info[0]
    # fele: tuple[str, int] | tuple[str, int, int, int] = fe[-1]
    # felefe: str = fele[0]
    # return felefe
    return addr_info[0][-1][0]  # type: ignore


def ensure_mqtt_connect(watchdog: machine.WDT|None = None, timeout_s: float|None=None) -> None:
    global _mqttclient, _keepalive, _controlfeed, _lastping, lock

    logger.debug(f"mqttwrap.py::ensure_mqtt_connect::called {watchdog=} {timeout_s=}")

    if watchdog:
        watchdog.feed()

    logger.debug("mqttwrap.py::ensure_mqtt_connect::before trying to get lock...")
    with lock:
        logger.debug("mqttwrap.py::ensure_mqtt_connect::AFTER trying to get lock...")

        if watchdog:
            watchdog.feed()

        if _mqttclient is None:
            _mqttclient = MQTTClientSimple(
                client_id=get_client_id(),
                server=config.data["mosquitto"]["MOSQUITTO_HOST"],  # type: ignore
                port=config.data["mosquitto"]["MOSQUITTO_PORT"],  # type: ignore
                ssl=None,
                keepalive=_keepalive,
                password=config.data["mosquitto"]["MOSQUITTO_PASSWORD"],  # type: ignore
                user=config.data["mosquitto"]["MOSQUITTO_USERNAME"],  # type: ignore
            )
            if watchdog:
                watchdog.feed()

            _mqttclient.set_callback(sub_cb)

            lwtf: str = config.get_config_data_str(config.get_config_data_dict(config.data, "mosquitto"), "lwtfeed")
            lwtfeed: str = format_with_clientid(lwtf)

            logger.debug(f"mqttwrap.py::ensure_mqtt_connect::lwt_feed: {lwtfeed}")
            _mqttclient.set_last_will(
                topic=lwtfeed,  # type: ignore
                msg="OFFLINE",
                qos=0,
                retain=True,
            )

            logger.debug("mqttwrap.py::ensure_mqtt_connect::before call to .connect()")


            logger.debug(f"mqttwrap.py::ensure_mqtt_connect::before trying to connect to {_mqttclient.server=}:{_mqttclient.port=}")

            addr = socket.getaddrinfo(_mqttclient.server, _mqttclient.port, 0, socket.SOCK_STREAM)[0][-1]
            logger.debug(f"mqttwrap.py::ensure_mqtt_connect::before trying to connect to {addr=}")

            logger.debug(f"mqttwrap.py::ensure_mqtt_connect::before trying to connect with {_mqttclient.user=} {_mqttclient.pswd=}")
            _mqttclient.connect(clean_session=True, timeout=timeout_s)
            logger.debug("mqttwrap.py::ensure_mqtt_connect::after call to .connect()")

            if watchdog:
                watchdog.feed()

            _mqttclient.publish(
                format_with_clientid(config.data["mosquitto"]["lwtfeed"]),  # type: ignore
                "ONLINE",
                qos=0,
                retain=True,
            )

            _controlfeed = format_with_clientid(config.data["mosquitto"]["controlfeed"])  # type: ignore
            _mqttclient.subscribe(
                topic=_controlfeed
            )

    if watchdog:
        watchdog.feed()

    # acquires its own lock...
    # ping(reset_if_mqtt_fails=False)

    if watchdog:
        watchdog.feed()


def ensure_mqtt_catch_reset(reset_if_mqtt_fails: bool = True, watchdog: machine.WDT|None = None, mqtt_connect_timeout_s: float|None = None) -> None:
    try:
        ensure_mqtt_connect(watchdog=watchdog, timeout_s=mqtt_connect_timeout_s)
    except Exception as ex:
        _timestring = time.getisotimenow()

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

        if reset_if_mqtt_fails:
            logger.debug("RESETTING...in 60s")
            if watchdog:
                logger.debug("\tor if watchdog kicks in")
            time.sleep(60)  # type: ignore[attr-defined]
            machine.reset()


def value_to_mqtt_string(
        value: str | float | int | dict, created_at: str | None = None
) -> str:
    d: dict = mosquitto_to_send_base_data.copy()  # ggf. aus performancegründen einfach gar kein copy...
    d["created_at"] = time.getisotimenow() if created_at is None else created_at
    d["value"] = value

    return json.dumps(d)


def publish_one(topic: str, msg: str, qos: int = 1, retain: bool = True, reset_if_mqtt_fails: bool = True, watchdog: machine.WDT|None = None) -> None:
    global _lastping, _mqttclient, lock

    logger.debug(f"publish_one {topic=} {len(msg)=} {qos=}")
    if watchdog:
        watchdog.feed()

    with lock:
        if watchdog:
            watchdog.feed()

        # assert _mqttclient is not None
        if reset_if_mqtt_fails:
            try:
                _mqttclient.publish(topic=topic, msg=msg, retain=retain, qos=qos)  #type: ignore
            except Exception as iex:
                _timestring = time.getisotimenow()

                _out = io.StringIO()
                sys.print_exception(iex)
                sys.print_exception(iex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                if watchdog:
                    logger.debug("\tor if watchdog kicks in")
                time.sleep(30)  # type: ignore[attr-defined]
                machine.reset()
        else:
            _mqttclient.publish(topic=topic, msg=msg, retain=retain, qos=qos)  #type: ignore

    logger.debug(f"published {topic=}")
    _lastping = time.time()  # type: ignore[attr-defined]

    if watchdog:
        watchdog.feed()


def check_msg(watchdog: machine.WDT|None = None) -> None:
    global _mqttclient
    if watchdog:
        watchdog.feed()

    with lock:
        if watchdog:
            watchdog.feed()

        # assert _mqttclient is not None
        _mqttclient.check_msg()  # type: ignore

    if watchdog:
        watchdog.feed()


def ping(reset_if_mqtt_fails: bool = True, watchdog: machine.WDT|None = None) -> None:
    global _lastping, lock, _mqttclient
    now: int = time.time()  # type: ignore[attr-defined]
    logger.debug("mqttwrap::ping()::trying to get lock...")
    with lock:
        logger.debug("mqttwrap::ping()::got lock...")
        if watchdog:
            watchdog.feed()

        # assert _mqttclient is not None
        if reset_if_mqtt_fails:
            try:
                _mqttclient.ping()  # type: ignore
            except Exception as ex:
                _timestring = time.getisotimenow()

                _out = io.StringIO()
                sys.print_exception(ex)
                sys.print_exception(ex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                if watchdog:
                    logger.debug("\tor if watchdog kicks in...")

                time.sleep(30)  # type: ignore[attr-defined]
                machine.reset()
        else:
            _mqttclient.ping()  # type: ignore

        _lastping = now

        if watchdog:
            watchdog.feed()

def ping_if_needed(threshhold: int = 10, reset_if_mqtt_fails: bool = True, watchdog: machine.WDT|None = None) -> None:
    global _keepalive
    global _lastping
    now: int = time.time()  # type: ignore[attr-defined]
    if now - _lastping > _keepalive - threshhold:
        # acquires own lock
        ping(reset_if_mqtt_fails=reset_if_mqtt_fails, watchdog=watchdog)



def send_status_to_mosquitto(include_wifi_scan: bool = True, watchdog: machine.WDT|None = None, also_send_LWT: bool = True) -> None:
    global boottime_local_str, boottime_gmt, last_status_gmt

    ifconfig: tuple = wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True, watchdog=watchdog)
    ensure_mqtt_catch_reset(reset_if_mqtt_fails=True, watchdog=watchdog)

    statusdata: dict = {
        "wifi": {
            "ip": ifconfig[0],
            "subnet": ifconfig[1],
            "gateway": ifconfig[2],
            "dns": ifconfig[2],
            "strength": wifi.get_wifi_strength(),
            "config": wifi.get_wifi_config(),
        }
    }

    if include_wifi_scan:
        statusdata["wifi_scan"] = wifi.get_wifi_scan()
    else:
        statusdata["wifi_scan"] = None

    rtseconds: int = round(time.time() - boottime_gmt)  # type: ignore[attr-defined]
    statusdata["runtime_seconds"] = rtseconds
    statusdata["running_since"] = boottime_local_str

    statusdata["reboot_pending_in"] = -1
    if config.data["forcerestart_after_running_seconds"] > 0:  # type: ignore
        statusdata["reboot_pending_in"] = (
                config.data["forcerestart_after_running_seconds"] - rtseconds  # type: ignore
        )

    msg: str = value_to_mqtt_string(value=statusdata)

    logger.debug(msg)

    publish_one(
        topic=get_feed("statusfeed"),
        msg=msg,
        qos=1,
        retain=True,
        reset_if_mqtt_fails=True,
        watchdog=watchdog
    )
    # mqttwrap.loop()
    last_status_gmt = time.mktime(time.gmtime())  # type: ignore

    if also_send_LWT:
        publish_one(
            topic=get_feed("lwtfeed"),
            msg="ONLINE",
            qos=1,
            retain=True,
            reset_if_mqtt_fails=True,
            watchdog=watchdog
        )


def check_msgs(reset_if_mqtt_fails: bool = True, watchdog: machine.WDT|None = None) -> None:
    """ also pings if needed """
    global last_status_gmt, TELE_PERIOD

    if watchdog:
        watchdog.feed()

    now: float = time.mktime(time.gmtime())  # type: ignore[attr-defined]
    ll: float = -1
    if last_status_gmt:
        ll = now - last_status_gmt

    # logger.debug(f"{last_status_gmt=} now-last_status_gmt={ll} {TELE_PERIOD=}")

    if not last_status_gmt or now - last_status_gmt > TELE_PERIOD:
        send_status_to_mosquitto(include_wifi_scan=False, watchdog=watchdog)
        last_status_gmt = now

    # logger.debug("check_msgs")

    if reset_if_mqtt_fails:
        try:
            check_msg(watchdog=watchdog)
            ping_if_needed(threshhold=10, reset_if_mqtt_fails=True, watchdog=watchdog)
        except OSError as ex:
            if ex.errno == -1:
                _out = io.StringIO()
                sys.print_exception(ex)
                sys.print_exception(ex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                if watchdog:
                    logger.debug("\tor if watchdog kicks in...")
                time.sleep(30)  # type: ignore[attr-defined]
                machine.reset()
            else:
                raise ex
    else:
        check_msg(watchdog=watchdog)
        ping_if_needed(threshhold=10, reset_if_mqtt_fails=False, watchdog=watchdog)


# def loop():
#     # logger.debug("loop")
#     ifdata: str | None = wifi.ensure_wifi()
#     if not ifdata:
#         logger.error("No wifi connected - sleeping 30s now and then restarting...")
#         time.sleep(30)
#         machine.reset()
#
#     with lock:
#         _mqttclient.check_msg()
#
#     # logger.debug("looped")