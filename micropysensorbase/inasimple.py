from micropysensorbase import time

from machine import Pin, I2C

sdapin = Pin(21)
sclpin = Pin(22)

i2c = I2C(0, scl=sclpin, sda=sdapin, freq=400000)
print("performing i2scan...")
i2c.scan()
print("performing i2scan... DONE")


print("loading INA219 module...")
from ina219 import INA219
print("loading INA219 module... DONE")


SHUNT_OHMS = 0.1  # Check value of shunt used with your INA219

# 64, 65, 66, 67  || 0x40 0x41 0x42 0x43
ina = INA219(SHUNT_OHMS, i2c)
# ina.ssetCalibration_16V_400mA();
ina.configure(
voltage_range=INA219.RANGE_16V,
gain=INA219.GAIN_1_40MV,
shunt_adc=INA219.ADC_128SAMP
)

ina.configure(
voltage_range=INA219.RANGE_32V,
gain=INA219.GAIN_AUTO,
shunt_adc=INA219.ADC_128SAMP
)

# GAIN_1_40MV, GAIN_2_80MV, GAIN_4_160MV, GAIN_8_320MV, GAIN_AUTO (default).


# /* Set PGain
#   * Gain *  * Shunt Voltage Range *   * Max Current (if shunt is 0.1 ohms) *
#    PG_40       40 mV                    0.4 A
#    PG_80       80 mV                    0.8 A
#    PG_160      160 mV                   1.6 A
#    PG_320      320 mV                   3.2 A (DEFAULT)
#   */
# ina.sleep()

def ina219measure():
	current = ina.current()
	busvoltage = ina.voltage()
	shuntvoltage = ina.shunt_voltage()
	power = ina.power()

	print("Shunt Voltage: %.3f V" % shuntvoltage)
	print("Bus Voltage: %.3f V" % busvoltage)
	print("Current: %.3f mA" % current)
	print("Power: %.3f mW" % power)
	print("\n")


for i in range(0, 10):
	ina219measure()
	time.sleep(1)
