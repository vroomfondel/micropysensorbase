"""Library for the INA226 current and power monitor from Texas Instruments.

Supports the Raspberry Pi using the I2C bus.

https://raw.githubusercontent.com/e71828/pi_ina226/main/ina226.py
https://github.com/e71828/pi_ina226/blob/main/ina226.py

"""

from micropysensorbase import logging
from math import trunc

# from smbus import SMBus

# changed for micropython to usmbus facade
# from smbus2 import SMBus
from usmbus import SMBus


def to_bytes(register_value: int) -> list[int]:
    return [(register_value >> 8) & 0xFF, register_value & 0xFF]


def binary_as_string(register_value: int) -> str:
    r = bin(register_value)[2:]
    logging.get_logger(__name__).debug(f"{type(r)=} {r=}")
    return f'{r:010s}'  # '{0:010d}'.format(r)  # r.format("0d16")  #.zfill(16)


def max_expected_amps_to_string(max_expected_amps: float | None) -> str:
    if max_expected_amps is None:
        return ""
    return str(", max expected amps: %.3fA" % max_expected_amps)


class INA226:
    """Class containing the INA226 functionality."""

    AVG_1BIT = 0  # 1 samples at 16-bit
    AVG_4BIT = 1
    AVG_16BIT = 2
    AVG_64BIT = 3
    AVG_128BIT = 4
    AVG_256BIT = 5
    AVG_512BIT = 6
    AVG_1024BIT = 7

    VCT_140us_BIT = 0
    VCT_204us_BIT = 1
    VCT_332us_BIT = 2
    VCT_588us_BIT = 3
    VCT_1100us_BIT = 4
    VCT_2116us_BIT = 5
    VCT_4156us_BIT = 6
    VCT_8244us_BIT = 7

    __REG_CONFIG = 0x00
    __REG_SHUNTVOLTAGE = 0x01
    __REG_BUSVOLTAGE = 0x02
    __REG_POWER = 0x03
    __REG_CURRENT = 0x04
    __REG_CALI = 0x05
    __REG_MASK = 0x06
    __REG_LIMIT = 0x07
    __REG_MANUFACTURER_ID = 0xFE
    __REG_DIE_ID = 0xFF

    __RST = 15
    __AVG0 = 9
    __VBUSCT0 = 6
    __VSHCT0 = 3
    __MODE3 = 2
    __MODE2 = 1
    __MODE1 = 0
    __CONT_SH_BUS = 7

    __SOL = 15  # Shunt Voltage Over-Voltage
    __SUL = 14  # Shunt Voltage Under-Voltage
    __BOL = 13  # Bus Voltage Over-Voltage
    __BUL = 12  # Bus Voltage Under-Voltage
    __POL = 11  # Power Over-Limit : invalid current and power data
    __CNVR = (
        10  # Conversion Ready : Alert pin to be asserted when the __CVRF is asserted
    )
    __AFF = 4  # Alert Function Flag :
    # determine if the Alert Function was the source
    # when an alert function and the Conversion Ready are both enabled
    # When the Alert Latch Enable bit is set to Latch mode, the Alert Function Flag bit clears only when the Mask/Enable
    # Register is read. When the Alert Latch Enable bit is set to Transparent mode, the Alert Function Flag bit is
    # cleared following the next conversion that does not result in an Alert condition

    __CVRF = 3  # Conversion Ready Flag : SET after complete, clear when write __REG_CONFIG or Read __REG_MASK
    # help coordinate one-shot or triggered conversions

    __OVF = 2  # Math Overflow Flag
    __APOL = 1  # Alert Polarity bit; sets the Alert pin polarity
    __LEN = 0  # Alert Latch Enable; configures the latching feature of the Alert pin and Alert Flag bit:
    # When the Alert Latch Enable bit is set to Transparent mode, the Alert pin and Flag bit
    # resets to the idle states when
    # the fault has been cleared. When the Alert Latch Enable bit is set to Latch mode, the Alert pin and Alert Flag bit
    # remains active following a fault until the Mask/Enable Register has been rea

    __AMP_ERR_MSG = (
        "Expected current %.3fA is greater " "than max possible current %.3fA"
    )

    __LOG_FORMAT = f"%(asctime)s - %(levelname)s -  %(name)-12s - %(message)s"
    __LOG_MSG_1 = (
        "shunt ohms: %.3f, bus max volts: %d, "
        "shunt volts max: %.2f%s, "
        "VBUSCT BIT: %d, VSHSCT BIT: %d"
    )
    __LOG_MSG_2 = (
        "calibrate called with: bus max volts: %dV, " "max shunt volts: %.2fV%s"
    )
    __LOG_MSG_3 = (
        "Current overflow detected - " "attempting to increase max_expected_amps"
    )

    __BUS_RANGE = 40.96  # HEX = 7FFF, LSB = 1.25 mV, Must to positive
    __GAIN_VOLTS = (
        0.08192  # HEX = 7FFF, LSB = 2.5 uV, An MSB = '1' denotes a negative number.
    )
    __SHUNT_MILLIVOLTS_LSB = 0.0025
    __BUS_MILLIVOLTS_LSB = 1.25
    __CALIBRATION_FACTOR = 0.00512
    __MAX_CALIBRATION_VALUE = 0x7FFF  # Max value supported (32767 decimal)
    __MAX_CURRENT_VALUE = 0x7FFF
    __CURRENT_LSB_FACTOR = 32768

    def __init__(
        self,
        smbus: SMBus,
        address: int=0x40,
        max_expected_amps: float|None=None,
        shunt_ohms: float=0.002,
        log_level: int= logging.ERROR,
    ):
        """Construct the class.

        Pass in the resistance of the shunt resistor and the maximum expected
        current flowing through it in your system.

        Arguments:
        shunt_ohms -- value of shunt resistor in Ohms (mandatory).
        max_expected_amps -- the maximum expected current in Amps (optional).
        address -- the I2C address of the INA226, defaults
            to *0x40* (optional).
        log_level -- set to logging.DEBUG to see detailed calibration
            calculations (optional).
        """
        if len(logging.get_logger().handlers) == 0:
            # Initialize the root logger only if it hasn't been done yet by a
            # parent module.
            logging.basic_config(level=log_level, format=self.__LOG_FORMAT)

        self.logger = logging.get_logger(__name__)
        self.logger.setLevel(log_level)
        self._address = address
        self._i2c = smbus

        self._shunt_ohms = shunt_ohms
        self._max_expected_amps = max_expected_amps
        self._min_device_current_lsb = self._calculate_min_current_lsb()


    def configure(
        self, avg_mode: int=AVG_1BIT, bus_ct: int=VCT_8244us_BIT, shunt_ct: int=VCT_8244us_BIT
    ) -> None:
        """Configure and calibrate how the INA226 will take measurements."""

        self.logger.debug(
            self.__LOG_MSG_1
            % (
                self._shunt_ohms,
                self.__BUS_RANGE,
                self.__GAIN_VOLTS,
                max_expected_amps_to_string(self._max_expected_amps),
                bus_ct,
                shunt_ct,
            )
        )

        self._calibrate(self.__BUS_RANGE, self.__GAIN_VOLTS, self._max_expected_amps)
        configuration = (
            avg_mode << self.__AVG0
            | bus_ct << self.__VBUSCT0
            | shunt_ct << self.__VSHCT0
            | self.__CONT_SH_BUS
            | 1 << 14
        )
        self._configuration_register(configuration)


    def voltage(self) -> float:
        """Return the bus voltage in volts."""
        value = self._voltage_register()
        return float(value) * self.__BUS_MILLIVOLTS_LSB / 1000


    def supply_voltage(self) -> float:
        """Return the bus supply voltage in volts.

        This is the sum of the bus voltage and shunt voltage. A
        DeviceRangeError exception is thrown if current overflow occurs.
        """
        return self.voltage() + (float(self.shunt_voltage()) / 1000)


    def current(self) -> float:
        """Return the bus current in milliamps.

        A DeviceRangeError exception is thrown if current overflow occurs.
        """
        self._handle_current_overflow()
        return self._current_register() * self._current_lsb * 1000


    def power(self) -> float:
        """Return the bus power consumption in milliwatts.

        A DeviceRangeError exception is thrown if current overflow occurs.
        """
        self._handle_current_overflow()
        return self._power_register() * self._power_lsb * 1000


    def shunt_voltage(self) -> float:
        """Return the shunt voltage in millivolts.

        A DeviceRangeError exception is thrown if current overflow occurs.
        """
        self._handle_current_overflow()
        return self._shunt_voltage_register() * self.__SHUNT_MILLIVOLTS_LSB


    def sleep(self) -> None:
        """Put the INA226 into power down mode."""
        configuration = self._read_configuration()
        self._configuration_register(configuration & 0xFFF8)


    def wake(self, mode: int=__CONT_SH_BUS) -> None:
        """Wake the INA226 from power down mode."""
        configuration = self._read_configuration()
        self._configuration_register(configuration & 0xFFF8 | mode)


    def current_overflow(self) -> int:
        """Return true if the sensor has detect current overflow.

        In this case the current and power values are invalid.
        """
        return self._has_current_overflow()


    def reset(self) -> None:
        """Reset the INA226 to its default configuration."""
        self._configuration_register(1 << self.__RST)
        self.logger.info(
            "config register: 0x%02x, value: 0x%04x"
            % (self.__REG_CONFIG, self._read_configuration())
        )
        self.logger.info(
            "Calibration: 0x%02x, value: 0x%04x"
            % (self.__REG_CALI, self.__read_register(self.__REG_CALI))
        )
        self.logger.info(
            "mask register: 0x%02x, value: 0x%04x"
            % (self.__REG_MASK, self._read_mask_register())
        )
        self.logger.info(
            "limit register: 0x%02x, value: 0x%04x"
            % (self.__REG_LIMIT, self._read_limit_register())
        )
        self.logger.info(
            "manufacturer id: 0x%02x, value: 0x%04x"
            % (self.__REG_MANUFACTURER_ID, self._manufacture_id())
        )
        self.logger.info(
            "die id: 0x%02x, value: 0x%04x" % (self.__REG_DIE_ID, self._die_id())
        )


    def set_low_battery(self, low_limit: int=3, high_level_trigger: bool=True) -> None:
        # trunc actually return an int which is (bit)shiftable
        self._limit_register(trunc(low_limit * 1000 / self.__BUS_MILLIVOLTS_LSB))  # type: ignore

        if high_level_trigger:
            self._mask_register(1 << 12 | 3)
        else:
            self._mask_register(1 << 12 | 1)


    def _calibrate(self, bus_volts_max: float, shunt_volts_max: float, max_expected_amps: float|None=None) -> None:
        self.logger.info(
            self.__LOG_MSG_2
            % (
                bus_volts_max,
                shunt_volts_max,
                max_expected_amps_to_string(max_expected_amps),
            )
        )
        max_possible_amps = shunt_volts_max / self._shunt_ohms

        self.logger.info("max possible current: %.2fA" % max_possible_amps)

        self._current_lsb = self._determine_current_lsb(
            max_expected_amps, max_possible_amps
        )
        self.logger.info("current LSB: %.3e A/bit" % self._current_lsb)

        self._power_lsb = self._current_lsb * 25.2
        self.logger.info("power LSB: %.3e W/bit" % self._power_lsb)

        max_current = self._current_lsb * self.__MAX_CURRENT_VALUE
        self.logger.info("max current before overflow: %.4fA" % max_current)

        max_shunt_voltage = max_current * self._shunt_ohms
        self.logger.info(
            "max shunt voltage before overflow: %.4fmV" % (max_shunt_voltage * 1000)
        )

        # trunc returned an int!
        calibration: int = trunc(self.__CALIBRATION_FACTOR / (self._current_lsb * self._shunt_ohms))  # type: ignore

        self.logger.info("calibration: 0x%04x (%d)" % (calibration, calibration))
        self._calibration_register(calibration)

    def _determine_current_lsb(self, max_expected_amps: float|None, max_possible_amps: float) -> float:
        if max_expected_amps is not None:
            if max_expected_amps > round(max_possible_amps, 3):
                raise ValueError(
                    self.__AMP_ERR_MSG % (max_expected_amps, max_possible_amps)
                )
            self.logger.info("max expected current: %.3fA" % max_expected_amps)
            if max_expected_amps < max_possible_amps:
                current_lsb = max_expected_amps / self.__CURRENT_LSB_FACTOR
            else:
                current_lsb = max_possible_amps / self.__CURRENT_LSB_FACTOR
        else:
            current_lsb = max_possible_amps / self.__CURRENT_LSB_FACTOR
        self.logger.info(
            "expected current LSB base on max_expected_amps: %.3e A/bit" % current_lsb
        )
        if current_lsb < self._min_device_current_lsb:
            current_lsb = self._min_device_current_lsb
            self.logger.info(
                "current_lsb is less equal than min_device_current_lsb, use the latter"
            )
        return current_lsb

    def _calculate_min_current_lsb(self) -> float:
        return self.__CALIBRATION_FACTOR / (
            self._shunt_ohms * self.__MAX_CALIBRATION_VALUE
        )

    def _has_current_overflow(self) -> bool:
        ovf = self._read_mask_register() >> self.__OVF & 1
        return bool(ovf)

    def is_conversion_ready(self) -> int:
        """Check if conversion of a new reading has occured."""
        cnvr = self._read_mask_register() >> self.__CVRF & 1
        return cnvr

    def is_low_battery(self) -> int:
        bul = self._read_mask_register() >> self.__BUL & 1
        return bul

    def _handle_current_overflow(self) -> None:
        if self._has_current_overflow():
            raise DeviceRangeError(self.__GAIN_VOLTS)

    def _configuration_register(self, register_value: int) -> None:
        self.logger.debug("configuration: 0x%04x" % register_value)
        self.__write_register(self.__REG_CONFIG, register_value)

    def _read_configuration(self) -> int:
        return self.__read_register(self.__REG_CONFIG)

    def _voltage_register(self) -> int:
        return self.__read_register(self.__REG_BUSVOLTAGE)

    def _current_register(self)-> int:
        return self.__read_register(self.__REG_CURRENT, True)

    def _shunt_voltage_register(self) -> int:
        return self.__read_register(self.__REG_SHUNTVOLTAGE, True)

    def _power_register(self) -> int:
        return self.__read_register(self.__REG_POWER)

    def _calibration_register(self, register_value: int) -> None:
        self.logger.debug("calibration: 0x%04x" % register_value)
        self.__write_register(self.__REG_CALI, register_value)

    def _read_mask_register(self) -> int:
        return self.__read_register(self.__REG_MASK)

    def _mask_register(self, register_value: int) -> None:
        self.logger.debug("mask/enable: 0x%04x" % register_value)
        self.__write_register(self.__REG_MASK, register_value)

    def _read_limit_register(self) -> int:
        return self.__read_register(self.__REG_LIMIT)

    def _limit_register(self, register_value: int) -> None:
        self.logger.debug("limit value: 0x%04x" % register_value)
        self.__write_register(self.__REG_LIMIT, register_value)

    def _manufacture_id(self) -> int:
        return self.__read_register(self.__REG_MANUFACTURER_ID)

    def _die_id(self) -> int:
        return self.__read_register(self.__REG_DIE_ID)

    def __write_register(self, register: int, register_value: int) -> None:
        register_bytes = to_bytes(register_value)
        self.logger.debug(
            "write register 0x%02x: 0x%04x 0b%s"
            % (register, register_value, binary_as_string(register_value))
        )
        self._i2c.write_i2c_block_data(self._address, register, register_bytes)
        # self._i2c.write_word_data(self._address, register, register_value)

    def __read_register(self, register: int, negative_value_supported: bool=False) -> int:
        result: int = self._i2c.read_word_data(self._address, register) & 0xFFFF
        register_value = ((result << 8) & 0xFF00) + (result >> 8)
        if negative_value_supported:
            if register_value > 32767:
                register_value -= 65536
        self.logger.debug(
            "read register 0x%02x: 0x%04x 0b%s"
            % (register, register_value, binary_as_string(register_value))
        )
        return register_value


class DeviceRangeError(Exception):
    """Class containing the INA226 error functionality."""

    __DEV_RNG_ERR = "Current out of range (overflow), " "for gain %.2fV"

    def __init__(self, gain_volts: float, device_max: bool=False):
        """Construct a DeviceRangeError."""
        msg = self.__DEV_RNG_ERR % gain_volts
        if device_max:
            msg = msg + ", device limit reached"
        super(DeviceRangeError, self).__init__(msg)
        self.gain_volts = gain_volts
        self.device_limit_reached = device_max
