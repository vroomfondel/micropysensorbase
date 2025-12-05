""" Provides an SMBus class for use on micropython """
from micropysensorbase import logging

# https://github.com/vroomfondel/micropython-smbus/tree/add-read_word_data
# https://github.com/matteius/micropython-smbus/blob/fix-edgecase-from-bme280-work/usmbus/__init__.py

import machine
#
# try:
#     from machine import I2C, Pin
# except ImportError:
#     raise ImportError("Can't find the micropython machine.I2C class: "
#                       "perhaps you don't need this adapter?")


class SMBus():  # machine.I2C):
    """ Provides an 'SMBus' module which supports some of the py-smbus
        i2c methods, as well as being a subclass of machine.I2C

        Hopefully this will allow you to run code that was targeted at
        py-smbus unmodified on micropython.

        Use it like you would the machine.I2C class:

            import usmbus.SMBus

            bus = SMBus(id=0, scl=machine.Pin(15), sda=machine.Pin(10), freq=100000)
            bus.read_byte_data(addr, register)
            ... etc
    """

    __LOG_FORMAT = f"%(asctime)s - %(levelname)s -  %(name)-12s - %(message)s"

    def __init__(self, id: int, scl: machine.Pin, sda: machine.Pin, freq: int=400_000, log_level: int= logging.ERROR):
        self.i2c = machine.I2C(id, scl=scl, sda=sda, freq=freq)

        self.scl = scl
        self.sda = sda
        self.freq = freq

        if len(logging.get_logger().handlers) == 0:
            # Initialize the root logger only if it hasn't been done yet by a
            # parent module.
            logging.basic_config(level=log_level, format=self.__LOG_FORMAT)

        self.logger: logging.Logger = logging.get_logger(__name__)
        self.logger.setLevel(log_level)

        #(0, scl=machine.Pin(22), sda = machine.Pin(21), freq = 400_000)

    def scan(self) -> list:
        return self.i2c.scan()

    def read_byte_data(self, addr: int, register: int) -> int:
        """ Read a single byte from register of device at addr
            Returns a single byte """

        self.logger.debug(f"read_byte_data {addr=} {register=}")

        return self.i2c.readfrom_mem(addr, register, 1)[0]


    def read_i2c_block_data(self, addr: int, register: int, length: int) -> bytes:
        """ Read a block of length from register of device at addr
            Returns a bytes object filled with whatever was read """

        self.logger.debug(f"read_i2c_block_data {addr=} {register=} {length=}")

        return self.i2c.readfrom_mem(addr, register, length)


    def write_byte_data(self, addr: int, register: int, data: int|bytes) -> None:
        """ Write a single byte from buffer `data` to register of device at addr
            Returns None """

        # writeto_mem() expects something it can treat as a buffer
        if isinstance(data, int):
            data = bytes([data])

        return self.i2c.writeto_mem(addr, register, data)


    def write_i2c_block_data(self, addr: int, register: int, data: bytes|list[int]) -> None:
        """ Write multiple bytes of data to register of device at addr
            Returns None """

        #writeto_mem() expects something it can treat as a buffer
        if not isinstance(data, bytes):
            if not isinstance(data, list):
                data = [data]
            data = bytes(data)

        return self.i2c.writeto_mem(addr, register, data)


    # The following haven't been implemented, but could be.
    def read_byte(self, *args: list[object]|None, **kwargs: dict[str, object]|None) -> int:
        """ Not yet implemented """

        raise RuntimeError("Not yet implemented")


    def write_byte(self, *args: list[object]|None, **kwargs: dict[str, object]|None) -> None:
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")


    def read_word_data(self, addr: int, register: int) -> int:
        """ Not yet implemented """
        # DEBUG:root:read_word_data args=(64, 2) kwargs={}

        bs: bytes = self.i2c.readfrom_mem(addr, register, 2)
        self.logger.debug(f"read_word_data::{addr=} {register=} {bs=}")

        return int.from_bytes(bs, 'little')


    def write_word_data(self, *args: list[object]|None, **kwargs: dict[str, object]|None) -> None:
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")
