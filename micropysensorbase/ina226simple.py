from . import time

from machine import Pin, I2C
from math import trunc

print("loading INA226 module...")
import ina226
print("loading INA226 module... DONE")


i2c = None

if not i2c:
    sdapin = Pin(21)
    sclpin = Pin(22)

    i2c = I2C(0, scl=sclpin, sda=sdapin, freq=400000)

    print("performing i2scan...")
    i2c.scan()
    print("performing i2scan... DONE")

ina = None

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


def _calculate_min_current_lsb(_shunt_ohms):
    return __CALIBRATION_FACTOR / (
            _shunt_ohms * __MAX_CALIBRATION_VALUE
    )



def _determine_current_lsb(max_expected_amps, max_possible_amps, _min_device_current_lsb):
    print(f"{max_expected_amps=} {max_possible_amps=} {_min_device_current_lsb=}")

    if max_expected_amps is not None:
        if max_expected_amps > round(max_possible_amps, 3):
            print(f"{max_expected_amps=} > {round(max_possible_amps, 3)=}")
            raise ValueError("blargh")
        print("max expected current: %.3fA" % max_expected_amps)

        if max_expected_amps < max_possible_amps:
            current_lsb = max_expected_amps / __CURRENT_LSB_FACTOR
        else:
            current_lsb = max_possible_amps / __CURRENT_LSB_FACTOR
    else:
        current_lsb = max_possible_amps / __CURRENT_LSB_FACTOR

    print("expected current LSB base on max_expected_amps: %.3e A/bit" % current_lsb)

    if current_lsb < _min_device_current_lsb:
        current_lsb = _min_device_current_lsb
        print("current_lsb is less equal than min_device_current_lsb, use the latter")

    return current_lsb



def get_calvalue_other(bus_volts_max, shunt_volts_max, max_expected_amps, _shunt_ohms=0.1):
    _min_device_current_lsb = _calculate_min_current_lsb(_shunt_ohms)


    max_possible_amps = shunt_volts_max / _shunt_ohms

    print("max possible current: %.2fA" % max_possible_amps)

    _current_lsb = _determine_current_lsb(
        max_expected_amps, max_possible_amps, _min_device_current_lsb
    )
    print("current LSB: %.3e A/bit" % _current_lsb)

    _power_lsb = _current_lsb * 25.2
    print("power LSB: %.3e W/bit" % _power_lsb)

    max_current = _current_lsb * __MAX_CURRENT_VALUE
    print("max current before overflow: %.4fA" % max_current)

    max_shunt_voltage = max_current * _shunt_ohms
    print("max shunt voltage before overflow: %.4fmV" % (max_shunt_voltage * 1000))

    # trunc returned an int!
    calibration: int = trunc(__CALIBRATION_FACTOR / (_current_lsb * _shunt_ohms))  # type: ignore

    return calibration

def get_calvalue():
    # calvalue = 512

    current_lsb = 0.05 / (2 ^ 15)
    print(f"{current_lsb=}")
    # current_lsb = 0.0001098632813
    # -> Rounding to "nicer" numbers:
    # current_lsb = 0.0001

    current_lsb = round(current_lsb, 4)

    print(f"{current_lsb=} rounded")

    # 3. Setting the power LSB
    power_lsb = 25 * current_lsb
    print(f"{power_lsb=}")

    # 4. Determine calibration register value
    RSHUNT = 0.1
    cal_value = 0.00512 / (RSHUNT * current_lsb)
    print(f"{cal_value=}")

    cal_value = round(cal_value)

    return cal_value


if not ina:
    # ina226
    ina = ina226.INA226(i2c, 0x40)
    # default configuration and calibration value
    #ina.set_calibration()

    # cal_value = get_calvalue()
    #cal_value = get_calvalue_other(bus_volts_max=36, shunt_volts_max=36, max_expected_amps=0.5, _shunt_ohms=0.1)
    # cal_value = get_calvalue_other(__BUS_RANGE, __GAIN_VOLTS, 1, 0.1)
    # print(f"{cal_value=}")

    # ina.set_calibration_custom(calValue=cal_value, config=0x4fff)  # 0x4d27)  #SHBUSCONT 0x4cdf  #SHV_CONT) # 0x4d27

    ina.set_calibration()

def reset_calibration():
    ina.set_calibration()


def calibrate_custom(bus_range=__BUS_RANGE, gain_volts=__GAIN_VOLTS, max_expected_amps=1, shut_ohms=0.1):
    cal_value = get_calvalue_other(bus_range, gain_volts, max_expected_amps, shut_ohms)
    print(f"{bus_range=}, {gain_volts=} {max_expected_amps=} {shut_ohms=} => {cal_value=}")

    # cal_value=2560
    ina.set_calibration_custom(calValue=cal_value, config=0x4fff)  # 0x4d27)  #SHBUSCONT 0x4cdf  #SHV_CONT) # 0x4d27


def ina226measure():
    busvoltage = ina.bus_voltage
    shuntvoltage = ina.shunt_voltage
    current = ina.current * 1000
    power = ina.power


    print("Shunt Voltage: %.3f V" % shuntvoltage)
    print("Bus Voltage: %.3f V" % busvoltage)
    print("Current: %.3f mA" % current)
    print("Power: %.3f mW" % power)
    print("\n")


def ina226measure_loop(max: int = 10):
    for i in range(0, max):
        print(f"{i+1}/{max}")
        ina226measure()
        time.sleep(1)

def reset():
    """Reset the INA226 to its default configuration."""
    ina._write_register(ina226._REG_CONFIG, 1 << ina226._CONFIG_RESET)
    print(
        "config register: 0x%02x, value: 0x%04x"
        % (ina226._REG_CONFIG, ina._read_register(ina226._REG_CONFIG))
    )
    print(
        "Calibration: 0x%02x, value: 0x%04x"
        % (ina226._REG_CALIBRATION, ina._read_register(ina226._REG_CALIBRATION))
    )

if __name__ == "__main__":
    ina226measure_loop()