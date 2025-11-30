import logging
import micropython

micropython.alloc_emergency_exception_buf(100)

# serial stuff also here: https://github.com/micropython/micropython/blob/master/tools/pyboard.py

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.debug("STARTING boot_ssd.py")

import machine
import config

from ssd1306 import SSD1306_I2C
from sh1106 import SH1106_I2C

ssd: SH1106_I2C | SSD1306_I2C | None = None

sdapin: machine.Pin | None = None
sclpin: machine.Pin | None = None
soft_i2cbus: machine.SoftI2C | None = None

def setup_pins() -> None:
    global soft_i2cbus, sdapin, sclpin, ssd

    logger.info("Setting up pins")

    assert config.data is not None
    # if "i2c" in config.data and isinstance(config.data["i2c"], dict) and config.data["i2c"].get("enabled", False) == True:
    i2c: dict[str, str|float|int|bool] = config.get_config_data_dict(config.data, "i2c")
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

            k: list = soft_i2cbus.scan()
            for i in k:
                logger.debug(f"i2c_scan: {i=}")
        else:
            logger.debug("i2c already created")

        flip_en: bool
        ssd1306: dict[str, str|float|int|bool] = config.get_config_data_dict(config.data, "ssd1306")
        if config.get_config_data_bool(ssd1306, "enabled"):
            flip_en = False
            if "flip_en" in ssd1306 and config.get_config_data_bool(ssd1306, "flip_en"):
                flip_en = True

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
        if config.get_config_data_bool(sh1106, "enabled"):
            flip_en = False
            if "flip_en" in sh1106 and config.get_config_data_bool(sh1106, "flip_en"):
                flip_en = True

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


def init_ssd() -> None:
    global ssd
    if not ssd:
        logger.debug("ssd is None")
        return

    ssd.poweron()
    ssd.fill(0)
    ssd.text("_SCREEN_INIT", 0, 12, 1)
    ssd.show()

def setup() -> None:
    setup_pins()
    init_ssd()

def disable() -> None:
    global ssd, sdapin, sclpin, soft_i2cbus

    ssd = None
    sdapin = None
    sclpin = None
    soft_i2cbus = None