from micropysensorbase import logging, time

logger = logging.get_logger(__name__)
logger.setLevel(logging.DEBUG)

logger.debug("STARTING main.py")

import machine

# from usmbus import SMBus

# import mqttwrap
# import wifi
import config

# wifi.ensure_wifi()
# mqttwrap.ensure_mqtt_connect()

from veml7700 import VEML7700
from ssd1306 import SSD1306_I2C

sdapin: machine.Pin | None = None
sclpin: machine.Pin | None = None
bus:  machine.SoftI2C | None = None

# outpin: machine.Pin = machine.Pin(16, machine.Pin.OPEN_DRAIN)  #, pull=machine.Pin.PULL_UP)
# outpin_bistable_relais: bool = True

import dht

dht11: dht.DHT11 | None = None

veml7700: VEML7700 | None = None

ssd: SSD1306_I2C | None = None


def setup_i2c():
    global bus, sdapin, sclpin

    if not sdapin:
        sdapin = machine.Pin(config.data["pins"]["sda"])
    else:
        logger.debug("sdapin already created")

    if not sclpin:
        sclpin = machine.Pin(config.data["pins"]["scl"])
    else:
        logger.debug("sclpin already created")

    if not bus:
        bus = machine.SoftI2C(scl=machine.Pin(22), sda=machine.Pin(21))
        logger.debug(f"{bus=}")

        k: list = bus.scan()
        for i in k:
            logger.debug(f"i2c: {i=}")

    else:
        logger.debug("i2c already created")


def setup_ssd1306():
    global bus, ssd

    setup_i2c()

    ssd = SSD1306_I2C(width=128, height=64, i2c=bus)
    ssd.init_display()


def setup_veml7000():
    global veml7700, sdapin, sclpin, bus

    setup_i2c()

    veml7700 = VEML7700(address=0x10, i2c=bus, it=100, gain=1 / 8)


def demo_ssd1306():
    global ssd

    ssd.fill(0)
    ssd.fill_rect(0, 0, 32, 32, 1)
    ssd.fill_rect(2, 2, 28, 28, 0)
    ssd.vline(9, 8, 22, 1)
    ssd.vline(16, 2, 22, 1)
    ssd.vline(23, 8, 22, 1)
    ssd.fill_rect(26, 24, 2, 4, 1)
    ssd.text('MicroPython', 40, 0, 1)
    ssd.text('SSD1306', 40, 12, 1)
    ssd.text('OLED 128x64', 40, 24, 1)
    ssd.show()

    # https://docs.micropython.org/en/latest/esp8266/tutorial/ssd1306.html
    #
    # display.text('Hello, World!', 0, 0, 1)
    # display.show()
    #
    # display.poweroff()     # power off the display, pixels persist in memory
    # display.poweron()      # power on the display, pixels redrawn
    # display.contrast(0)    # dim
    # display.contrast(255)  # bright
    # display.invert(1)      # display inverted
    # display.invert(0)      # display normal
    # display.rotate(True)   # rotate 180 degrees
    # display.rotate(False)  # rotate 0 degrees
    # display.show()         # write the contents of the FrameBuffer to display memory
    #
    #
    #
    #
    # display.fill(0)                         # fill entire screen with colour=0
    # display.pixel(0, 10)                    # get pixel at x=0, y=10
    # display.pixel(0, 10, 1)                 # set pixel at x=0, y=10 to colour=1
    # display.hline(0, 8, 4, 1)               # draw horizontal line x=0, y=8, width=4, colour=1
    # display.vline(0, 8, 4, 1)               # draw vertical line x=0, y=8, height=4, colour=1
    # display.line(0, 0, 127, 63, 1)          # draw a line from 0,0 to 127,63
    # display.rect(10, 10, 107, 43, 1)        # draw a rectangle outline 10,10 to 117,53, colour=1
    # display.fill_rect(10, 10, 107, 43, 1)   # draw a solid rectangle 10,10 to 117,53, colour=1
    # display.text('Hello World', 0, 0, 1)    # draw some text at x=0, y=0, colour=1
    # display.scroll(20, 0)                   # scroll 20 pixels to the right
    #
    # # draw another FrameBuffer on top of the current one at the given coordinates
    # import framebuf
    # fbuf = framebuf.FrameBuffer(bytearray(8 * 8 * 1), 8, 8, framebuf.MONO_VLSB)
    # fbuf.line(0, 0, 7, 7, 1)
    # display.blit(fbuf, 10, 10, 0)           # draw on top at x=10, y=10, key=0
    # display.show()

def setup_dht11():
    global dht11

    dht11 = dht.DHT11(machine.Pin(17))

def measure_dht11() -> tuple[float, float]:
    dht11.measure()
    temp: float = dht11.temperature()
    hum: float = dht11.humidity()
    return temp, hum

def main():
    global ssd, veml7700, outpin_bistable_relais

    setup_ssd1306()

    # demo_ssd1306()

    setup_dht11()

    setup_veml7000()

    onoff: bool = True
    while True:
        lx: int = veml7700.read_lux()
        logger.info(f"LUX read: {lx}")
        ssd.fill(0)

        ssd.text(f'LUX: {lx}', 5, 5, 1)

        temp: float
        hum: float
        temp, hum = measure_dht11()

        logger.info(f"TEMP read: {temp}")
        logger.info(f"HUM read: {hum}")

        ssd.text(f'TEMP: {temp}°C', 5, 14, 1)
        ssd.text(f'HUM: {hum}%', 5, 23, 1)

        ssd.show()
        time.sleep(1)




        # if outpin_bistable_relais:
        #     # bistable is already flip-flopping
        #     outpin.on()
        #     time.sleep(0.1)
        #     outpin.off()
        # else:
        #     if onoff:
        #         outpin.on()
        #     else:
        #         outpin.off()
        #
        # onoff = not onoff

if __name__ == "__main__":
    main()