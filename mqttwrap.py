import micropython
import time
import machine
import sys
import io

#### monkeypatching galore!!! ####
#### needed for retain-bit ####
# taken from https://github.com/micropython/micropython-lib/blob/master/micropython/umqtt.simple/umqtt/simple.py
# and adapted
from umqtt.simple import MQTTClient as MQTTClientSimple


def wait_msg(self):
    res = self.sock.read(1)
    self.sock.setblocking(True)
    if res is None:
        return None
    if res == b"":
        raise OSError(-1)
    if res == b"\xd0":  # PINGRESP
        sz = self.sock.read(1)[0]
        assert sz == 0
        return None
    op = res[0]
    if op & 0xF0 != 0x30:
        return op
    sz = self._recv_len()
    topic_len = self.sock.read(2)
    topic_len = (topic_len[0] << 8) | topic_len[1]
    topic = self.sock.read(topic_len)
    sz -= topic_len + 2
    if op & 6:
        pid = self.sock.read(2)
        pid = pid[0] << 8 | pid[1]
        sz -= 2
    msg = self.sock.read(sz)

    # do not ignore retained
    retained = op & 0x01

    self.cb(topic, msg, retained == 1)
    if op & 6 == 2:
        pkt = bytearray(b"\x40\x02\0\0")
        struct.pack_into("!H", pkt, 2, pid)
        self.sock.write(pkt)
    elif op & 6 == 4:
        assert 0
    return op


MQTTClientSimple.wait_msg = wait_msg
#### /monkeypatching galore!!! ####

# from umqtt.robust import MQTTClient
from umqtt.simple import MQTTClient

import config
import wifi

import _thread

lock = _thread.allocate_lock()

TELE_PERIOD: int = 60

last_status_gmt: float | None = None

try:
    import ujson
except Exception as ex:
    import json as ujson

try:
    import usocket as socket
except:
    import socket

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

boottime_gmt: float = time.mktime(time.gmtime())
boottime_local_str = time.getisotime(boottime_gmt)

_lastping: int = time.time()

_mqttclient: MQTTClient | None = None
_keepalive: int = 60
_controlfeed: str | None = None
_received_commands: list[tuple[int, str, str | None]] = []


def get_client_id() -> str:
    return f"esp32_{wifi.mac_no_colon}"
    # import machine
    # return hexlify(machine.unique_id())


def format_with_clientid(topic: str) -> str:
    return topic.format(clientid=get_client_id())


def get_feed(feedname: str) -> str | None:
    return format_with_clientid(config.data["mosquitto"][feedname])


mosquitto_to_send_base_data: dict = {
    "lat": config.data["mosquitto"]["lat_loc2"],
    "lon": config.data["mosquitto"]["lon_loc2"],
    "ele": config.data["mosquitto"]["ele_loc2"],
}


def pop_cmd_received() -> tuple[int, str, str | None] | None:
    if len(_received_commands) > 0:
        r: tuple[int, str, str | None] = _received_commands.pop(0)
        return r

    return None


def sub_cb(topic, msg, retained):
    global _lastping
    _lastping = time.time()

    msg: str = msg.decode("utf-8")
    topic = topic.decode("utf-8")
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


def get_ip(host, port=80):
    addr_info = socket.getaddrinfo(host, port)
    return addr_info[0][-1][0]


def ensure_mqtt_connect():
    global _mqttclient, _keepalive, _controlfeed, _lastping, lock

    with lock:
        if _mqttclient is None:
            _mqttclient = MQTTClient(
                client_id=get_client_id(),
                server=config.data["mosquitto"]["MOSQUITTO_HOST"],
                port=config.data["mosquitto"]["MOSQUITTO_PORT"],
                keepalive=_keepalive,
                password=config.data["mosquitto"]["MOSQUITTO_PASSWORD"],
                user=config.data["mosquitto"]["MOSQUITTO_USERNAME"],
            )

            _mqttclient.set_callback(sub_cb)

            _mqttclient.set_last_will(
                format_with_clientid(config.data["mosquitto"]["lwtfeed"]),
                "OFFLINE",
                qos=1,
                retain=True,
            )
            _mqttclient.connect(clean_session=True)
            _mqttclient.publish(
                format_with_clientid(config.data["mosquitto"]["lwtfeed"]),
                "ONLINE",
                qos=1,
                retain=True,
            )

            _controlfeed = format_with_clientid(config.data["mosquitto"]["controlfeed"])
            _mqttclient.subscribe(
                topic=_controlfeed
            )

    # acquires its own lock...
    ping(reset_if_mqtt_fails=False)


def ensure_mqtt_catch_reset(reset_if_mqtt_fails: bool = True):
    try:
        ensure_mqtt_connect()
    except Exception as ex:
        _timestring = time.getisotimenow()

        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

        if reset_if_mqtt_fails:
            logger.debug("RESETTING...in 30s")
            time.sleep(30)
            machine.reset()


def value_to_mqtt_string(
        value: str | float | int | dict, created_at: str | None = None
) -> str:
    d: dict = mosquitto_to_send_base_data.copy()  # ggf. aus performancegründen einfach gar kein copy...
    d["created_at"] = time.getisotimenow() if created_at is None else created_at
    d["value"] = value

    return ujson.dumps(d)


def publish_one(topic: str, msg: str, qos: int = 1, retain: bool = True, reset_if_mqtt_fails: bool = True):
    global _lastping, _mqttclient, lock

    logger.debug(f"publish_one {topic=} {len(msg)=} {qos=}")

    with lock:
        if reset_if_mqtt_fails:
            try:
                _mqttclient.publish(topic=topic, msg=msg, retain=retain, qos=qos)
            except Exception as ex:
                _timestring = time.getisotimenow()

                _out = io.StringIO()
                sys.print_exception(ex)
                sys.print_exception(ex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                time.sleep(30)
                machine.reset()
        else:
            _mqttclient.publish(topic=topic, msg=msg, retain=retain, qos=qos)

    logger.debug(f"publisheD {topic=}")
    _lastping = time.time()


def check_msg():
    with lock:
        _mqttclient.check_msg()


def ping(reset_if_mqtt_fails: bool = True):
    global _lastping, lock
    now: int = time.time()
    logger.debug("=> PING")

    with lock:
        if reset_if_mqtt_fails:
            try:
                _mqttclient.ping()
            except Exception as ex:
                _timestring = time.getisotimenow()

                _out = io.StringIO()
                sys.print_exception(ex)
                sys.print_exception(ex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                time.sleep(30)
                machine.reset()
        else:
            _mqttclient.ping()

        _lastping = now

def ping_if_needed(threshhold: int = 10, reset_if_mqtt_fails: bool = True):
    global _keepalive
    global _lastping
    now: int = time.time()
    if now - _lastping > _keepalive - threshhold:
        # acquires own lock
        ping(reset_if_mqtt_fails=reset_if_mqtt_fails)



def send_status_to_mosquitto(include_wifi_scan: bool = True):
    global boottime_local_str, boottime_gmt, last_status_gmt

    ifconfig: tuple = wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True)
    ensure_mqtt_catch_reset(reset_if_mqtt_fails=True)

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

    rtseconds: int = round(time.time() - boottime_gmt)
    statusdata["runtime_seconds"] = rtseconds
    statusdata["running_since"] = boottime_local_str

    statusdata["reboot_pending_in"] = -1
    if config.data["forcerestart_after_running_seconds"] > 0:
        statusdata["reboot_pending_in"] = (
                config.data["forcerestart_after_running_seconds"] - rtseconds
        )

    msg: str = value_to_mqtt_string(value=statusdata)

    logger.debug(msg)

    publish_one(
        topic=get_feed("statusfeed"),
        msg=msg,
        qos=1,
        retain=True,
        reset_if_mqtt_fails=True
    )
    # mqttwrap.loop()
    last_status_gmt = time.mktime(time.gmtime())


def check_msgs(reset_if_mqtt_fails: bool = True):
    """ also pings if needed """
    global last_status_gmt, TELE_PERIOD

    now: float = time.mktime(time.gmtime())
    ll: float = -1
    if last_status_gmt:
        ll = now - last_status_gmt

    # logger.debug(f"{last_status_gmt=} now-last_status_gmt={ll} {TELE_PERIOD=}")

    if not last_status_gmt or now - last_status_gmt > TELE_PERIOD:
        send_status_to_mosquitto(include_wifi_scan=False)
        last_status_gmt = now

    # logger.debug("check_msgs")

    if reset_if_mqtt_fails:
        try:
            check_msg()
            ping_if_needed(threshhold=10)
        except OSError as ex:
            if ex.errno == -1:
                _out = io.StringIO()
                sys.print_exception(ex)
                sys.print_exception(ex, _out)

                logger.error(_out.getvalue())

                logger.debug("RESETTING...in 30s")
                time.sleep(30)
                machine.reset()
            else:
                raise ex
    else:
        check_msg()
        ping_if_needed(threshhold=10)


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
