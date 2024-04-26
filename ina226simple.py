import time

from machine import Pin, I2C

i2c = None

if not i2c:
	sdapin = Pin(18)
	sclpin = Pin(19)

	i2c = I2C(0, scl=sclpin, sda=sdapin, freq=400000)

	print("performing i2scan...")
	i2c.scan()
	print("performing i2scan... DONE")

ina = None

if not ina:
	print("loading INA226 module...")
	import ina226
	print("loading INA226 module... DONE")

	# ina226
	ina = ina226.INA226(i2c, 0x40)
	# default configuration and calibration value
	#ina.set_calibration()
	ina.set_calibration_custom(calValue=512, config=0x4cdf)  #SHBUSCONT 0x4cdf  #SHV_CONT)



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


for i in range(0, 100):
	ina226measure()
	time.sleep(1)
