import gc
import io
import sys
from micropysensorbase import logging, time
import micropython
from micropysensorbase.time import sleep  # type: ignore[attr-defined]
from machine import Timer, WDT
import machine

import mqttwrap
import wifi
import config

import _thread

DISABLED_AUTO_SETUP: bool = False

logger = logging.get_logger(__name__)
logger.setLevel(logging.DEBUG)

if __name__ in config.get_config_data_dict(config.data, "loglevel"):
    melv: int|None = logging.get_log_level_by_name(
        config.get_config_data_str(config.get_config_data_dict(config.data, "loglevel"), "mqttwrap"))
    if melv is not None:
        logger.setLevel(melv)

measurec: int = 0
logger.debug(f"measurements.py::{measurec}::STARTING")
measurec += 1

# will be set by call from main...
lock: _thread.LockType | config.DummyLock = config.DummyLock(name="measurements", loglevel=logging.INFO)

# will be set by call from main...
WATCHDOG: WDT|None = None

# will be set by call from main...
DISABLE_INET: bool = False

logger.debug(f"measurements.py::{measurec}::After boilerplate")
measurec += 1

import dht

from usmbus import SMBus

soft_i2cbus: machine.SoftI2C | None = None
ssd: SH1106_I2C | SSD1306_I2C | None = None  # type: ignore

sdapin: machine.Pin | None = None
sclpin: machine.Pin | None = None

smbus_sdapin: machine.Pin | None = None
smbus_sclpin: machine.Pin | None = None

smbus: SMBus | None = None

# both are one-wire-type
dht22: dht.DHT22 | None = None
dht11: dht.DHT11 | None = None


if "boot_ssd" in config.data and config.get_config_data_bool(config.data, "boot_ssd"):
    logger.debug("boot_ssd was active... flipping from there...")
    import boot_ssd

    ssd = boot_ssd.ssd
    sdapin = boot_ssd.sdapin
    sclpin = boot_ssd.sclpin
    soft_i2cbus = boot_ssd.soft_i2cbus
    boot_ssd.disable()
    logger.debug("\t-> flipping done")

    # TODO HT20251130 check what happens with sdapin vs smbus_sdapin etc...

logger.debug(f"measurements.py::{measurec}::After check for boot_ssd")
measurec += 1

ina: INA226 | None = None  # type: ignore

adc_input_pin: machine.Pin | None = None
digital_input_pin: machine.Pin | None = None

wakeup_deepsleep_pin: machine.Pin | None = None

input_adc: machine.ADC | None = None

output_pin: machine.Pin | None = None

output_pin_pwm: machine.Pin | None = None
output_pwm: machine.PWM | None = None

uart2: machine.UART | None = None
pin_low: bool = False

# MEASURE_TELE_PERIOD: int = 300
MEASURE_TELE_PERIOD: int = 60

# TODO HT20251201 -> make it a map/any other container structure...
last_ina_measure_sent_gmt: float | None = None
last_dht11_measure_sent_gmt: float | None = None
last_dht22_measure_sent_gmt: float | None = None


def handle_pin_interrupt_falling_rising(arg_pin: machine.Pin) -> None:
    global pin_low
    v: float | bool | int = arg_pin.value()
    pin_low = 0 == v
    logger.debug(f"handle_pin_value :: {v} {arg_pin=}")


logger.debug(f"measurements.py::{measurec}::Before setup_pins definition")
measurec += 1


def setup_pins() -> None:
    global adc_input_pin, digital_input_pin, input_adc, pin_low, output_pin, output_pin_pwm, output_pwm, uart2
    global soft_i2cbus, sdapin, sclpin, ssd, wakeup_deepsleep_pin, smbus, ina, smbus_sdapin, smbus_sclpin, dht22, dht11

    # generally usable pins ( https://www.youtube.com/watch?v=LY-1DHTxRAk  |  https://drive.google.com/file/d/1gbKM7DA7PI7s1-ne_VomcjOrb0bE2TPZ/view )
    # 04, 05, 16, 17, 18, 19, 23, 25, 26, 27, 32, 33

    # RTC_GPIO0 (GPIO36)
    # RTC_GPIO3 (GPIO39)
    # RTC_GPIO4 (GPIO34)
    # RTC_GPIO5 (GPIO35)
    # RTC_GPIO6 (GPIO25)
    # RTC_GPIO7 (GPIO26)
    # RTC_GPIO8 (GPIO33)
    # RTC_GPIO9 (GPIO32)
    # RTC_GPIO10 (GPIO4)
    # RTC_GPIO11 (GPIO0)
    # RTC_GPIO12 (GPIO2)
    # RTC_GPIO13 (GPIO15)
    # RTC_GPIO14 (GPIO13)
    # RTC_GPIO15 (GPIO12)
    # RTC_GPIO16 (GPIO14)
    # RTC_GPIO17 (GPIO27)

    # IO34	I	GPIO34	No	RTC_GPIO04	ADC1_CH06
    # IO35	I	GPIO35	No	RTC_GPIO05	ADC1_CH07
    # SENSOR_VP	I	GPIO36	No	RTC_GPIO00	ADC1_CH0
    # SENSOR_VN	I	GPIO39	No	RTC_GPIO03	ADC1_CH03

    # UART0: tx=1, rx=3
    # UART1: tx=10, rx=9
    # UART2: tx=17, rx=16

    logger.info("Setting up pins")

    smbusc: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "smbus")
    if config.get_config_data_bool(smbusc, "enabled"):
        if not smbus_sdapin:
            smbus_sdapin = machine.Pin(config.get_config_data_int(smbusc, "sda_pin"))
        else:
            logger.debug("smbus_sdapin already created")

        if not smbus_sclpin:
            smbus_sclpin = machine.Pin(config.get_config_data_int(smbusc, "scl_pin"))
        else:
            logger.debug("smbus_sclpin already created")

        if not smbus:
            smbus = SMBus(0, scl=smbus_sclpin, sda=smbus_sdapin, freq=400_000)
            logger.debug(f"{smbus=}")

            k: list = smbus.scan()
            for i in k:
                logger.debug(f"smbus: {i=}")
        else:
            logger.debug("smbus already created")

        ina226c: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "ina226")
        if config.get_config_data_bool(ina226c, "enabled") and not ina:
            ina_address = 0x40
            if "address" in ina226c:
                ina_address = config.get_config_data_int(ina226c, "address")

            from ina226_raspi import INA226
            ina = INA226(
                address=ina_address,
                smbus=smbus,
                max_expected_amps=config.get_config_data_float(ina226c, "max_expected_amps"),
                log_level=logging.INFO,
                shunt_ohms=config.get_config_data_float(ina226c, "shunt_ohms")
            )
            ina.configure(
                avg_mode=ina.AVG_4BIT,
                bus_ct=ina.VCT_204us_BIT,
                shunt_ct=ina.VCT_8244us_BIT
            )  # make avg-mode configurable ?!

            # ina.configure(avg_mode=ina.AVG_1024BIT, bus_ct=ina.VCT_204us_BIT, shunt_ct=ina.VCT_8244us_BIT)  # make avg-mode configurable ?!

    i2c: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "i2c")
    if config.get_config_data_bool(i2c, "enabled"):
        if not sdapin:
            sdapin = machine.Pin(config.get_config_data_int(i2c, "sda_pin"))
        else:
            logger.debug("sdapin already created")

        if not sclpin:
            sclpin = machine.Pin(config.get_config_data_int(i2c, "scl_pin"))
        else:
            logger.debug("sclpin already created")

        if not soft_i2cbus:
            soft_i2cbus = machine.SoftI2C(scl=sclpin, sda=sdapin)
            logger.debug(f"{soft_i2cbus=}")

            i2ck: list = soft_i2cbus.scan()
            for i in i2ck:
                logger.debug(f"i2c_scan: {i=}")
        else:
            logger.debug("i2c already created")

        flip_en: bool
        ssd1306: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "ssd1306")
        if not ssd and config.get_config_data_bool(ssd1306, "enabled"):
            flip_en = False
            if "flip_en" in ssd1306 and config.get_config_data_bool(ssd1306, "flip_en"):
                flip_en = True

            from ssd1306 import SSD1306_I2C
            ssd = SSD1306_I2C(
                width=config.get_config_data_int(ssd1306, "width"),
                height=config.get_config_data_int(ssd1306, "height"),
                i2c=soft_i2cbus,
                addr=config.get_config_data_int(ssd1306, "address")
            )
            if flip_en:
                ssd.rotate(180)

            ssd.init_display()

            ssd.text(f"_SCREEN_INIT", 0, 0, 1)
            ssd.show()

        sh1106: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "sh1106")
        if not ssd and config.get_config_data_bool(sh1106, "enabled"):
            flip_en = False
            if "flip_en" in sh1106 and config.get_config_data_bool(sh1106, "flip_en"):
                flip_en = True

            from sh1106 import SH1106_I2C
            ssd = SH1106_I2C(
                width=config.get_config_data_int(sh1106, "width"),
                height=config.get_config_data_int(sh1106, "height"),
                i2c=soft_i2cbus,
                addr=config.get_config_data_int(sh1106, "address"),
                rotate=180 if flip_en else 0
            )
            ssd.init_display()

            ssd.text(f"_SCREEN_INIT", 0, 0, 1)
            ssd.show()

    rotary: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "rotary")
    if config.get_config_data_bool(rotary, "enabled"):
        ...
        # TODO

    dht22_c: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "dht22")
    if config.get_config_data_bool(dht22_c, "enabled"):
        dipin: int = config.get_config_data_int(dht22_c, "input_pin")

        logger.info(f"Setting up DHT22 on PIN {dipin}")
        dht22_input_pin: machine.Pin = machine.Pin(dipin, machine.Pin.IN)

        dht22 = dht.DHT22(dht22_input_pin)

    dht11_c: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "dht11")
    if config.get_config_data_bool(dht11_c, "enabled"):
        d11ipin: int = config.get_config_data_int(dht11_c, "input_pin")

        logger.info(f"Setting up DHT11 on PIN {d11ipin}")
        dht11_input_pin: machine.Pin = machine.Pin(d11ipin, machine.Pin.IN)

        dht11 = dht.DHT11(dht11_input_pin)

    adc: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "adc")
    if config.get_config_data_bool(adc, "enabled"):
        ipin: int = config.get_config_data_int(adc, "input_pin")
        adc_input_pin = machine.Pin(ipin, machine.Pin.IN)

        logger.info(f"Setting up ADC on PIN {ipin}")
        input_adc = machine.ADC(adc_input_pin, atten=machine.ADC.ATTN_11DB)  # TN_11DB)
        input_adc.width(machine.ADC.WIDTH_12BIT)
        # adc.atten(ADC.ATTN_11DB)       #Full range: 3.3v
        # ADC.ATTN_0DB: 0dB attenuation, gives a maximum input voltage of 1.00v - this is the default configuration
        # ADC.ATTN_2_5DB: 2.5dB attenuation, gives a maximum input voltage of approximately 1.34v
        # ADC.ATTN_6DB: 6dB attenuation, gives a maximum input voltage of approximately 2.00v
        # ADC.ATTN_11DB: 11dB attenuation, gives a maximum input voltage of approximately 3.6v

    digital_output: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "digital_output")
    if config.get_config_data_bool(digital_output, "enabled"):
        opin: int = config.get_config_data_int(digital_output, "output_pin")
        logger.info(f"Setting up DIGITAL OUT on PIN {opin}")

        output_pin = machine.Pin(opin, machine.Pin.OUT)  # , pull=machine.Pin.PULL_DOWN)

    digital_input: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "digital_input")
    if config.get_config_data_bool(digital_input, "enabled"):
        digital_input_pin = machine.Pin(config.get_config_data_int(digital_input, "input_pin"))

        pin_low = digital_input_pin.value() == 0
        digital_input_pin.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                              handler=handle_pin_interrupt_falling_rising)

    wakeup_deepsleep_pin_config: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data,
                                                                                                   "wakeup_deepsleep_pin")
    if config.get_config_data_bool(wakeup_deepsleep_pin_config, "enabled") and not config.get_config_data_bool(rotary,
                                                                                                               "enabled"):
        import esp32

        wakeup_deepsleep_pin = machine.Pin(config.get_config_data_int(wakeup_deepsleep_pin_config, "input_pin"))

        trigger_level = esp32.WAKEUP_ANY_HIGH
        if "trigger" in wakeup_deepsleep_pin_config:
            trigger_level = esp32.WAKEUP_ANY_HIGH if config.get_config_data_int(wakeup_deepsleep_pin_config,
                                                                                "trigger") == 1 else esp32.WAKEUP_ALL_LOW

        logger.info(
            f'setting external wakeup-signal to HIGH on PIN#{config.get_config_data_int(wakeup_deepsleep_pin_config, "input_pin")} {trigger_level=}')

        if not "disable_handler" in wakeup_deepsleep_pin_config or not config.get_config_data_bool(
                wakeup_deepsleep_pin_config, "disable_handler"):
            wakeup_deepsleep_pin.irq(
                trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                handler=handle_pin_interrupt_falling_rising
            )

        esp32.wake_on_ext0(wakeup_deepsleep_pin, trigger_level)

    pwm: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "pwm")
    if config.get_config_data_bool(pwm, "enabled"):
        pin: int = config.get_config_data_int(pwm, "output_pin")
        logger.info(f"Setting up PWM on PIN {pin}")

        output_pin_pwm = machine.Pin(pin)
        output_pwm = machine.PWM(
            output_pin_pwm,
            duty_u16=0,
            freq=50_000
        )

    uart: dict[str, str | float | int | bool] = config.get_config_data_dict(config.data, "uart")
    if config.get_config_data_bool(uart, "enabled"):
        rxpin: int = config.get_config_data_int(uart, "rx_pin")
        txpin: int = config.get_config_data_int(uart, "tx_pin")

        logger.info(f"Setting up UART on PINs {rxpin} + {txpin}")
        if rxpin == 16 and txpin == 17:
            uart2 = machine.UART(2)
            # uart2 = machine.UART(2, baudrate=115201, bits=8, parity=None, stop=1, tx=17, rx=16, rts=-1, cts=-1, txbuf=256, rxbuf=256, timeout=10, timeout_char=10)
            # default: UART(2, baudrate=115201, bits=8, parity=None, stop=1, tx=17, rx=16, rts=-1, cts=-1, txbuf=256, rxbuf=256, timeout=0, timeout_char=0)
            # uart2.init(9600, bits=8, parity=None, stop=1)
            uart2.init(timeout=5_000, timeout_char=100)
        else:
            uart2 = machine.UART(2, tx=txpin, rx=rxpin, baudrate=115200, bits=8, parity=None, stop=1, txbuf=256,
                                 rxbuf=256)
            # uart2 = machine.UART(2, baudrate=115201, bits=8, parity=None, stop=1, tx=17, rx=16, rts=-1, cts=-1, txbuf=256, rxbuf=256, timeout=10, timeout_char=10)
            # default: UART(2, baudrate=115201, bits=8, parity=None, stop=1, tx=17, rx=16, rts=-1, cts=-1, txbuf=256, rxbuf=256, timeout=0, timeout_char=0)
            # uart2.init(9600, bits=8, parity=None, stop=1)
            uart2.init(timeout=5_000, timeout_char=100)


class DHTREADDATA:
    def __init__(
            self,
            temperature: float,
            humidity: float,
            measure_device_name: str
    ):
        self.temperature = temperature
        self.humidity = humidity
        self.measure_device_name = measure_device_name

    def to_dict(self) -> dict:
        r: dict = {}

        r["temperature"] = self.temperature
        r["humidity"] = self.humidity
        r["measure_device_name"] = self.measure_device_name

        return r


logger.debug(f"measurements.py::{measurec}::After DHTREADDATA and INAREADDATA definitions")
measurec += 1


class INAREADDATA:
    def __init__(
            self,
            current: float,
            busvoltage: float,
            supplyvoltage: float,
            shuntvoltage: float,
            power: float,
    ):
        self.current = current
        self.busvoltage = busvoltage
        self.supplyvoltage = supplyvoltage
        self.shuntvoltage = shuntvoltage
        self.power = power

    def to_dict(self) -> dict:
        r: dict = {}

        r["current"] = self.current
        r["busvoltage"] = self.busvoltage
        r["shuntvoltage"] = self.shuntvoltage
        r["supplyvoltage"] = self.supplyvoltage
        r["power"] = self.power

        return r


last_ina_measure_sent_data: INAREADDATA | None = None
last_dht11_measure_sent_data: DHTREADDATA | None = None
last_dht22_measure_sent_data: DHTREADDATA | None = None


def ina226read(ina226: INA226) -> INAREADDATA:  # type: ignore
    inadata: INAREADDATA = INAREADDATA(
        current=ina226.current(),
        busvoltage=ina226.voltage(),
        supplyvoltage=ina226.supply_voltage(),
        shuntvoltage=ina226.shunt_voltage(),
        power=ina226.power(),
    )

    logger.info("Bus Voltage    : %.3f V" % inadata.busvoltage)
    logger.info("Bus Current    : %.3f mA" % inadata.current)
    logger.info("Supply Voltage : %.3f V" % inadata.supplyvoltage)
    logger.info("Shunt voltage  : %.3f mV" % inadata.shuntvoltage)
    logger.info("Power          : %.3f mW" % inadata.power)

    return inadata


def send_data_to_mosquitto(data: INAREADDATA | DHTREADDATA) -> None:
    global DISABLE_INET

    if DISABLE_INET:
        return

    wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True)
    mqttwrap.ensure_mqtt_catch_reset(reset_if_mqtt_fails=True)

    timestring: str = time.getisotimenow()

    msgd: str|None = None
    topicd: str|None = None

    if isinstance(data, INAREADDATA):
        msgd = mqttwrap.value_to_mqtt_string(value=data.current, created_at=timestring)
        topicd = mqttwrap.get_feed("mafeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")

        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )

        msgd = mqttwrap.value_to_mqtt_string(value=data.busvoltage, created_at=timestring)
        topicd = mqttwrap.get_feed("busvoltagefeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")
        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )

        msgd = mqttwrap.value_to_mqtt_string(value=data.to_dict(), created_at=timestring)
        topicd = mqttwrap.get_feed("loggingfeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")
        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )
    elif isinstance(data, DHTREADDATA):
        msgd = mqttwrap.value_to_mqtt_string(value=data.temperature, created_at=timestring)
        topicd = mqttwrap.get_feed(f"{data.measure_device_name}_temperaturefeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")
        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )

        msgd = mqttwrap.value_to_mqtt_string(value=data.humidity, created_at=timestring)
        topicd = mqttwrap.get_feed(f"{data.measure_device_name}_humidityfeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")
        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )

        msgd = mqttwrap.value_to_mqtt_string(value=data.to_dict(), created_at=timestring)
        topicd = mqttwrap.get_feed("loggingfeed")

        logger.info(f"send_data_to_mosquitto({topicd}): {msgd}")
        mqttwrap.publish_one(
            topic=topicd,
            msg=msgd,
            retain=True,
            qos=1,
            reset_if_mqtt_fails=True
        )

    gc.collect()
    logger.debug(f"{gc.mem_free()=}")


def measure_masked_arg(arg: int) -> None:
    global lock, WATCHDOG
    global ina, dht11, dht22

    if WATCHDOG:
        WATCHDOG.feed()

    # send_data_forced: bool = bool(arg ^ 0b10)
    # send_data_enabled: bool = bool((arg ^ 0b01) >> 1)

    send_data_forced: bool = bool(arg & 0b10)
    send_data_enabled: bool = bool(arg & 0b01)

    logger.debug(f"measurements.py::measure_masked_arg: {send_data_forced=} {send_data_enabled=} ")

    gc.collect()

    acquired: bool = False
    try:
        acquired = lock.acquire()
        # timeout not implemented https://github.com/micropython/micropython/issues/3332
    except Exception as ex:
        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

    if WATCHDOG:
        WATCHDOG.feed()

    if not acquired:
        logger.debug("measurements.py::measure_masked_arg()::FAILED TO ACQUIRE LOCK...")
        return

    for measuredevice in ["ina", "dht11", "dht22"]:
        if measuredevice is None:
            continue

        try:
            if measuredevice == "ina" and ina is not None:
                ina226_measure(
                    send_data_forced=send_data_forced, send_data_enabled=send_data_enabled
                )
            elif measuredevice == "dht11" and dht11 is not None:
                dht_measure(
                    dht_measuredevice=dht11,
                    send_data_forced=send_data_forced,
                    send_data_enabled=send_data_enabled
                )
            elif measuredevice == "dht22" and dht22 is not None:
                dht_measure(
                    dht_measuredevice=dht22,
                    send_data_forced=send_data_forced,
                    send_data_enabled=send_data_enabled
                )

        except Exception as ex:
            _out = io.StringIO()
            sys.print_exception(ex)
            sys.print_exception(ex, _out)

            logger.error(_out.getvalue())

        if WATCHDOG:
            WATCHDOG.feed()

    logger.debug("measurements.py::measure_masked_arg()::releasing lock")
    lock.release()


logger.debug(f"measurements.py::{measurec}::Before dht_measure definition")
measurec += 1


def dht_measure(dht_measuredevice: dht.DHT11 | dht.DHT22, send_data_forced: bool = False,
                send_data_enabled: bool = False) -> None:
    global last_dht11_measure_sent_gmt, last_dht22_measure_sent_gmt, MEASURE_TELE_PERIOD, WATCHDOG
    global last_dht11_measure_sent_data, last_dht22_measure_sent_data

    if WATCHDOG:
        WATCHDOG.feed()

    now: float = time.mktime(time.gmtime())  # type: ignore[attr-defined]

    dhtdata_last: DHTREADDATA | None = None
    send_data_overdue: bool = False

    n: str = "UNDEFINED"
    if dht_measuredevice == dht11:
        n = "dht11"
        dhtdata_last = last_dht11_measure_sent_data
        send_data_overdue = not last_dht11_measure_sent_gmt or now - last_dht11_measure_sent_gmt > MEASURE_TELE_PERIOD
    elif dht_measuredevice == dht22:
        n = "dht22"
        dhtdata_last = last_dht22_measure_sent_data
        send_data_overdue = not last_dht22_measure_sent_gmt or now - last_dht22_measure_sent_gmt > MEASURE_TELE_PERIOD

    logger.debug(f"{send_data_overdue=} {send_data_forced=}")

    dht_measuredevice.measure()

    dhtdata: DHTREADDATA = DHTREADDATA(
        temperature=dht_measuredevice.temperature(),
        humidity=dht_measuredevice.humidity(),
        measure_device_name=n
    )

    logger.info(f"dht_measure({n}): {dhtdata.measure_device_name=}")
    logger.info(f"dht_measure({n}): {dhtdata.temperature=}")
    logger.info(f"dht_measure({n}): {dhtdata.humidity=}")

    temperature_change_send_trigger: bool = False
    humidity_change_send_trigger: bool = False

    if dhtdata_last:
        temperature_diff: float = abs(
            dhtdata.temperature - dhtdata_last.temperature
        )
        humidity_diff: float = abs(
            dhtdata.humidity - dhtdata_last.humidity
        )

        humidity_diff_change_threshold: float = abs(
            dhtdata_last.humidity * 0.1
        )
        temperature_diff_change_threshold: float = abs(
            dhtdata_last.temperature * 0.1
        )

        humidity_diff_change_threshold = min(
            humidity_diff_change_threshold, 1.0
        )
        temperature_diff_change_threshold = min(
            temperature_diff_change_threshold, 0.1
        )

        logger.debug(f"{n}\t{temperature_diff=} {humidity_diff=}")
        logger.debug(
            f"{n}\t{temperature_diff_change_threshold=} {humidity_diff_change_threshold=}"
        )

        if temperature_diff > temperature_diff_change_threshold:
            temperature_change_send_trigger = True

        if humidity_diff > humidity_diff_change_threshold:
            humidity_change_send_trigger = True
    else:
        logger.debug("no previous sent data found...")

    logger.debug(
        f"{send_data_forced=} {send_data_enabled=} {send_data_overdue=}"
    )
    logger.debug(
        f"{temperature_change_send_trigger=} {humidity_change_send_trigger=}"
    )

    if (
            send_data_forced
            or (send_data_enabled and send_data_overdue)
            or (temperature_change_send_trigger or humidity_change_send_trigger)
    ):
        logger.debug("sending data...")

        send_data_to_mosquitto(dhtdata)

        if n == "dht11":
            last_dht11_measure_sent_gmt = now
            last_dht11_measure_sent_data = dhtdata
        elif n == "dht22":
            last_dht22_measure_sent_gmt = now
            last_dht22_measure_sent_data = dhtdata

        logger.debug("data sent")


def ina226_measure(send_data_forced: bool = False, send_data_enabled: bool = False) -> None:
    global last_ina_measure_sent_gmt, last_ina_measure_sent_data, MEASURE_TELE_PERIOD, ina, WATCHDOG

    if WATCHDOG:
        WATCHDOG.feed()

    now: float = time.mktime(time.gmtime())  # type: ignore[attr-defined]
    send_data_overdue: bool = (
            not last_ina_measure_sent_gmt or now - last_ina_measure_sent_gmt > MEASURE_TELE_PERIOD
    )
    logger.debug(f"{send_data_overdue=} {send_data_forced=}")

    assert ina is not None

    ct: int = 0
    while 1:
        ct += 1
        if ina.is_conversion_ready():
            sleep(0.2)
            logger.info(f"=====> Conversion ready (after {ct} loops)")
            inadata: INAREADDATA = ina226read(ina)

            current_change_send_trigger: bool = False
            busvoltage_change_send_trigger: bool = False

            if last_ina_measure_sent_data:
                current_diff: float = abs(
                    inadata.current - last_ina_measure_sent_data.current
                )
                busvoltage_diff: float = abs(
                    inadata.busvoltage - last_ina_measure_sent_data.busvoltage
                )

                current_diff_change_threshold: float = abs(
                    last_ina_measure_sent_data.current * 0.1
                )
                busvoltage_diff_change_threshold: float = abs(
                    last_ina_measure_sent_data.busvoltage * 0.1
                )

                current_diff_change_threshold = min(
                    current_diff_change_threshold, 1.0
                )  # ~ca. 2cm change bei 16ma für 100cm
                busvoltage_diff_change_threshold = min(
                    busvoltage_diff_change_threshold, 0.32
                )

                logger.debug(f"{current_diff=} {busvoltage_diff=}")
                logger.debug(
                    f"{current_diff_change_threshold=} {busvoltage_diff_change_threshold=}"
                )

                if current_diff > current_diff_change_threshold:
                    current_change_send_trigger = True

                if busvoltage_diff > busvoltage_diff_change_threshold:
                    busvoltage_change_send_trigger = True
            else:
                logger.debug("no previous sent data found...")

            logger.debug(
                f"{send_data_forced=} {send_data_enabled=} {send_data_overdue=}"
            )
            logger.debug(
                f"{current_change_send_trigger=} {busvoltage_change_send_trigger=}"
            )

            if (
                    send_data_forced
                    or (send_data_enabled and send_data_overdue)
                    or (current_change_send_trigger or busvoltage_change_send_trigger)
            ):
                logger.debug("sending data...")

                send_data_to_mosquitto(inadata)
                last_ina_measure_sent_gmt = now
                last_ina_measure_sent_data = inadata
                logger.debug("data sent")

            break


send_data_forced_always: bool = False


def measure_callback(trigger: Timer) -> None:
    global WATCHDOG
    global send_data_forced_always

    global ina, dht11, dht22

    logger.debug(f"{type(trigger)=} {trigger=}")
    # ina219measureCB::type(trigger)=<class 'Timer'> trigger=Timer(3ffea620; alarm_en=1, auto_reload=1, counter_en=1)

    send_data_forced: bool = send_data_forced_always
    send_data_enabled: bool = True

    # arg: int = send_data_forced | send_data_enabled << 1
    arg: int = (send_data_forced << 1) | send_data_enabled

    if WATCHDOG:
        WATCHDOG.feed()

    if ina is not None or dht11 is not None or dht22 is not None:
        micropython.schedule(measure_masked_arg, arg)

        if WATCHDOG:
            WATCHDOG.feed()


logger.debug(f"measurements.py::{measurec}::Before setup definition")
measurec += 1

def main() -> None:
    global ina, dht11, dht22

    logger.debug("START::measurements.py::main()")

    if ina is not None or dht11 is not None or dht22 is not None:
        # ina226_measure(send_data_enabled=True)
        send_data_forced: bool = send_data_forced_always
        send_data_enabled: bool = True

        arg: int = (send_data_forced << 1) | send_data_enabled
        measure_masked_arg(arg)

    for n in ["dht11", "dht22"]:
        d = None
        if n == "dht11":
            d = dht11
        elif n == "dht22":
            d = dht22

        if d is not None:
            logger.debug(f"d={n} {d.measure()=}")
            logger.debug(f"d={n} {d.temperature()=}")
            logger.debug(f"d={n} {d.humidity()=}")

    logger.debug("DONE::main::main()")


logger.debug(f"measurements.py::{measurec}::Before __name__ == \"__main__\"")
measurec += 1

if __name__ == "__main__":
    setup_pins()
    main()