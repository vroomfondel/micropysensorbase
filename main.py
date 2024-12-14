import io
import sys
import time
import logging
import micropython
from time import sleep
from machine import Timer, WDT
import machine

import mqttwrap
import wifi
import config

import _thread


DISABLED_AUTO_SETUP: bool = False

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.debug("STARTING main.py")

DISABLE_INET: bool = False

if "disable_inet" in config.data and config.data["disable_inet"]:
    DISABLE_INET = True

if "disable_autosetup" in config.data and config.data["disable_autosetup"]:
    DISABLED_AUTO_SETUP = True

if not DISABLE_INET:
    wifi.ensure_wifi_catch_reset()  # without WATCHDOG for the first run!
    mqttwrap.ensure_mqtt_catch_reset()  # without WATCHDOG for the first run!


msgtimer: Timer = Timer(0)
measuretimer: Timer = Timer(1)
reboottimer: Timer = Timer(2)
# esp32: four hardware-timers available

lock = _thread.allocate_lock()
WATCHDOG: WDT|None = None


def reboot_callback(_=None):
    micropython.schedule(reboot_trigger, None)


def reboot_trigger(_=None):
    timestring: str = time.getisotimenow()
    logger.info(f"{timestring}::rebooting...")
    mqttwrap.publish_one(
        topic=mqttwrap.get_feed("loggingfeed"),
        msg=f"rebooting at {timestring}",
        retain=True,
        qos=1,
        reset_if_mqtt_fails=True
    )
    machine.reset()


def check_msgs(_=None):
    global lock, DISABLE_INET, WATCHDOG

    if WATCHDOG:
        WATCHDOG.feed()

    if DISABLE_INET:
        return

    # logger.debug("check_msgs")

    if lock.locked():
        logger.debug("LOCKED...")

    try:
        with lock:
            wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True, watchdog=WATCHDOG)
            if WATCHDOG:
                WATCHDOG.feed()

            mqttwrap.ensure_mqtt_catch_reset(reset_if_mqtt_fails=True, watchdog=WATCHDOG)
            if WATCHDOG:
                WATCHDOG.feed()

            mqttwrap.check_msgs(reset_if_mqtt_fails=True, watchdog=WATCHDOG)  # check for connect-error!
            if WATCHDOG:
                WATCHDOG.feed()

            ts_cmd_arg: tuple[int, str, str | None] | None

            while True:
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

    if WATCHDOG:
        WATCHDOG.feed()


def check_msgs_callback(_=None):
    global WATCHDOG
    # logger.debug(f"{type(trigger)=} {trigger=}")
    # DEBUG:__main__:type(trigger)=<class 'Timer'> trigger=Timer(0, mode=PERIODIC, period=3000)

    micropython.schedule(check_msgs, None)

    if WATCHDOG:
        WATCHDOG.feed()

############################# end of boilerplate #############################


from ssd1306 import SSD1306_I2C
from sh1106 import SH1106_I2C
from usmbus import SMBus
from ina226_raspi import INA226

# import boot_ssd
# ssd: SH1106_I2C | SSD1306_I2C | None = boot_ssd.ssd
# sdapin: machine.Pin | None = boot_ssd.sdapin
# sclpin: machine.Pin | None = boot_ssd.sclpin
# soft_i2cbus: machine.SoftI2C | None = boot_ssd.soft_i2cbus
# boot_ssd.disable()

smbus_sdapin: machine.Pin | None = None
smbus_sclpin: machine.Pin | None = None

sdapin: machine.Pin | None = None
sclpin: machine.Pin | None = None
smbus: SMBus | None = None

ina: INA226 | None = None

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
CKMSGS_PERIOD_MS: int = 3_000
MEASURETIMER_PERIOD_MS: int = 10_000

last_measure_sent_gmt: float | None = None

def handle_pin_interrupt_falling_rising(arg_pin: machine.Pin):
    global pin_low
    v: float | bool | int = arg_pin.value()
    pin_low = 0 == v
    logger.debug(f"handle_pin_value :: {v} {arg_pin=}")


def setup_pins():
    global adc_input_pin, digital_input_pin, input_adc, pin_low, output_pin, output_pin_pwm, output_pwm, uart2
    global soft_i2cbus, sdapin, sclpin, ssd, wakeup_deepsleep_pin, smbus, ina, smbus_sdapin, smbus_sclpin

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

    if config.data["smbus"]["enabled"]:
        if not smbus_sdapin:
            smbus_sdapin = machine.Pin(config.data["smbus"]["sda_pin"])
        else:
            logger.debug("smbus_sdapin already created")

        if not smbus_sclpin:
            smbus_sclpin = machine.Pin(config.data["smbus"]["scl_pin"])
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

        if config.data["ina226"]["enabled"] and not ina:
            ina = INA226(
                smbus=smbus, max_expected_amps=config.data["ina226"]["max_expected_amps"], log_level=logging.INFO, shunt_ohms=config.data["ina226"]["shunt_ohms"]
            )
            ina.configure(avg_mode=ina.AVG_16BIT)  # make avg-mode configurable ?!


    if config.data["i2c"]["enabled"]:
        if not sdapin:
            sdapin = machine.Pin(config.data["i2c"]["sda_pin"])
        else:
            logger.debug("sdapin already created")

        if not sclpin:
            sclpin = machine.Pin(config.data["i2c"]["scl_pin"])
        else:
            logger.debug("sclpin already created")

        if not soft_i2cbus:
            soft_i2cbus = machine.SoftI2C(scl=sclpin, sda=sdapin)
            logger.debug(f"{soft_i2cbus=}")

            k: list = soft_i2cbus.scan()
            for i in k:
                logger.debug(f"i2c_scan: {i=}")
        else:
            logger.debug("i2c already created")

        if not ssd and config.data["ssd1306"]["enabled"]:
            flip_en: bool = False
            if "flip_en" in config.data["ssd1306"] and config.data["ssd1306"]["flip_en"]:
                flip_en = True

            ssd = SSD1306_I2C(width=config.data["ssd1306"]["width"], height=config.data["ssd1306"]["height"],
                              i2c=soft_i2cbus, addr=config.data["ssd1306"]["address"])
            if flip_en:
                ssd.rotate(180)

            ssd.init_display()

            ssd.text(f"_SCREEN_INIT", 0, 0, 1)
            ssd.show()

        if not ssd and config.data["sh1106"]["enabled"]:
            flip_en: bool = config.data["sh1106"]["flip_en"]
            ssd = SH1106_I2C(width=config.data["sh1106"]["width"], height=config.data["sh1106"]["height"],
                             i2c=soft_i2cbus, addr=config.data["sh1106"]["address"], rotate=180 if flip_en else 0)
            ssd.init_display()

            ssd.text(f"_SCREEN_INIT", 0, 0, 1)
            ssd.show()

    # TODO
    if config.data["rotary"]["enabled"]:
        ...

    if config.data["adc"]["enabled"]:
        pin: int = config.data["adc"]["input_pin"]
        adc_input_pin = machine.Pin(pin, machine.Pin.IN)

        logger.info(f"Setting up ADC on PIN {pin}")
        input_adc = machine.ADC(adc_input_pin, atten=machine.ADC.ATTN_11DB)  # TN_11DB)
        input_adc.width(machine.ADC.WIDTH_12BIT)
        # adc.atten(ADC.ATTN_11DB)       #Full range: 3.3v
        # ADC.ATTN_0DB: 0dB attenuation, gives a maximum input voltage of 1.00v - this is the default configuration
        # ADC.ATTN_2_5DB: 2.5dB attenuation, gives a maximum input voltage of approximately 1.34v
        # ADC.ATTN_6DB: 6dB attenuation, gives a maximum input voltage of approximately 2.00v
        # ADC.ATTN_11DB: 11dB attenuation, gives a maximum input voltage of approximately 3.6v

    if config.data["digital_output"]["enabled"]:
        pin: int = config.data["digital_output"]["output_pin"]
        logger.info(f"Setting up DIGITAL OUT on PIN {pin}")

        output_pin = machine.Pin(pin, machine.Pin.OUT)  # , pull=machine.Pin.PULL_DOWN)

    if config.data["digital_input"]["enabled"]:
        digital_input_pin = machine.Pin(config.data["digital_input"]["input_pin"])

        pin_low = digital_input_pin.value() == 0
        digital_input_pin.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                              handler=handle_pin_interrupt_falling_rising)

    if config.data["wakeup_deepsleep_pin"]["enabled"] and not config.data["rotary"]["enabled"]:
        import esp32

        wakeup_deepsleep_pin = machine.Pin(config.data["wakeup_deepsleep_pin"]["input_pin"])

        trigger_level = esp32.WAKEUP_ANY_HIGH
        if "trigger" in config.data["wakeup_deepsleep_pin"]:
            trigger_level = esp32.WAKEUP_ANY_HIGH if config.data["wakeup_deepsleep_pin"][
                                                         "trigger"] == 1 else esp32.WAKEUP_ALL_LOW

        logger.info(
            f'setting external wakeup-signal to HIGH on PIN#{config.data["wakeup_deepsleep_pin"]["input_pin"]} {trigger_level=}')

        if not "disable_handler" in config.data["wakeup_deepsleep_pin"] or not config.data["wakeup_deepsleep_pin"][
            "disable_handler"]:
            wakeup_deepsleep_pin.irq(trigger=machine.Pin.IRQ_FALLING | machine.Pin.IRQ_RISING,
                                     handler=handle_pin_interrupt_falling_rising)

        esp32.wake_on_ext0(wakeup_deepsleep_pin, trigger_level)

    if config.data["pwm"]["enabled"]:
        pin: int = config.data["pwm"]["output_pin"]
        logger.info(f"Setting up PWM on PIN {pin}")

        output_pin_pwm = machine.Pin(pin)
        output_pwm = machine.PWM(output_pin_pwm, duty=0, freq=50_000)

    if config.data["uart"]["enabled"]:
        rxpin: int = config.data["uart"]["rx_pin"]
        txpin: int = config.data["uart"]["tx_pin"]

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




last_measure_sent_data: INAREADDATA | None = None


def ina226read(ina226: INA226) -> INAREADDATA:
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


def send_data_to_mosquitto(inadata: INAREADDATA):
    global DISABLE_INET

    if DISABLE_INET:
        return

    wifi.ensure_wifi_catch_reset(reset_if_wifi_fails=True)
    mqttwrap.ensure_mqtt_catch_reset(reset_if_mqtt_fails=True)

    timestring: str = time.getisotimenow()

    mqttwrap.publish_one(
        topic=mqttwrap.get_feed("mafeed"),
        msg=mqttwrap.value_to_mqtt_string(value=inadata.current, created_at=timestring),
        retain=True,
        qos=1,
        reset_if_mqtt_fails=True
    )

    mqttwrap.publish_one(
        topic=mqttwrap.get_feed("busvoltagefeed"),
        msg=mqttwrap.value_to_mqtt_string(
            value=inadata.busvoltage, created_at=timestring
        ),
        retain=True,
        qos=1,
        reset_if_mqtt_fails=True
    )

    mqttwrap.publish_one(
        topic=mqttwrap.get_feed("loggingfeed"),
        msg=mqttwrap.value_to_mqtt_string(
            value=inadata.to_dict(), created_at=timestring
        ),
        retain=True,
        qos=1,
        reset_if_mqtt_fails=True
    )


def ina226_measure_masked_arg(arg: int):
    global lock, WATCHDOG

    if WATCHDOG:
        WATCHDOG.feed()

    send_data_forced: bool = bool(arg ^ 0b10)
    send_data_enabled: bool = bool((arg ^ 0b01) >> 1)

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
        logger.debug("FAILED TO ACQUIRE LOCK...")
        return

    try:
        ina226_measure(
            send_data_forced=send_data_forced, send_data_enabled=send_data_enabled
        )
    except Exception as ex:
        _out = io.StringIO()
        sys.print_exception(ex)
        sys.print_exception(ex, _out)

        logger.error(_out.getvalue())

    if WATCHDOG:
        WATCHDOG.feed()

    lock.release()



def ina226_measure(send_data_forced: bool = False, send_data_enabled: bool = False):
    global last_measure_sent_gmt, last_measure_sent_data, MEASURE_TELE_PERIOD, ina, WATCHDOG

    if WATCHDOG:
        WATCHDOG.feed()

    now: float = time.mktime(time.gmtime())
    send_data_overdue: bool = (
        not last_measure_sent_gmt or now - last_measure_sent_gmt > MEASURE_TELE_PERIOD
    )
    logger.debug(f"{send_data_overdue=} {send_data_forced=}")

    ct: int = 0
    while 1:
        ct += 1
        if ina.is_conversion_ready():
            sleep(0.2)
            logger.info(f"=====> Conversion ready (after {ct} loops)")
            inadata: INAREADDATA = ina226read(ina)

            current_change_send_trigger: bool = False
            busvoltage_change_send_trigger: bool = False

            if last_measure_sent_data:
                current_diff: float = abs(
                    inadata.current - last_measure_sent_data.current
                )
                busvoltage_diff: float = abs(
                    inadata.busvoltage - last_measure_sent_data.busvoltage
                )

                current_diff_change_threshold: float = abs(
                    last_measure_sent_data.current * 0.1
                )
                busvoltage_diff_change_threshold: float = abs(
                    last_measure_sent_data.busvoltage * 0.1
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
                last_measure_sent_gmt = now
                last_measure_sent_data = inadata
                logger.debug("data sent")

            break


def ina226_measure_callback(trigger):
    global WATCHDOG
    logger.debug(f"{type(trigger)=} {trigger=}")
    # ina219measureCB::type(trigger)=<class 'Timer'> trigger=Timer(3ffea620; alarm_en=1, auto_reload=1, counter_en=1)

    send_data_forced: bool = False
    send_data_enabled: bool = True

    arg: int = send_data_forced | send_data_enabled << 1

    if WATCHDOG:
        WATCHDOG.feed()

    micropython.schedule(ina226_measure_masked_arg, arg)

    if WATCHDOG:
        WATCHDOG.feed()


def setup():
    global msgtimer, measuretimer, MEASURETIMER_PERIOD_MS, CKMSGS_PERIOD_MS, WATCHDOG

    if config.ENABLE_WATCHDOG:
        WATCHDOG = WDT(timeout=8_000)

    logger.debug("main::setup()")

    check_msgs()

    if WATCHDOG:
        WATCHDOG.feed()

    msgtimer.init(
        period=CKMSGS_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=check_msgs_callback
    )

    setup_pins()

    if WATCHDOG:
        WATCHDOG.feed()

    # measurement will be executed each MEASURETIMER_PERIOD_MS; MEASURE_TELE_PERIOD will be checked if "overdue";
    # also if threshold since last sent measurement is exceeeded
    measuretimer.init(
        period=MEASURETIMER_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=ina226_measure_callback
    )

    if config.data["forcerestart_after_running_seconds"] > 0:
        reboottimer.init(
            period=config.data["forcerestart_after_running_seconds"] * 1000,
            mode=machine.Timer.ONE_SHOT,
            callback=reboot_callback,
        )

    # tim2 = Timer(-1)
    # tim2.init(period=30000, mode=Timer.PERIODIC, callback=lambda t: mqttclient.ping())
    # tim.deinit()

    if WATCHDOG:
        WATCHDOG.feed()

def whoami():
    logger.info(wifi.wlan.config("hostname") + "\t" + mqttwrap.boottime_local_str)


def main():
    logger.debug("START::main::main()")
    ina226_measure(send_data_enabled=True)
    logger.debug("DONE::main::main()")


if __name__ == "__main__":
    if DISABLED_AUTO_SETUP:
        logger.debug("DISABLED AUTO SETUP")
    else:
        setup()  # also calls setup_pins
        main()
