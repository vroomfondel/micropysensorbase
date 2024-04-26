import sys
from machine import Pin, ADC
from time import sleep

import mqttwrap
import wifi
import config

wifi.ensure_wifi()

p35 = Pin(35, Pin.IN)
adc = ADC(p35, atten=ADC.ATTN_11DB)
# adc.atten(ADC.ATTN_11DB)       #Full range: 3.3v

mqttwrap.ensure_mqtt_connect()


if __name__ == "__main__":
    # s: str = config.data["mosquitto"]["loggingfeed"]
    # print(f"s: {s}")
    #
    # s2: str = mqttwrap.format_with_clientid(s)
    # print(f"s: {s2}")
    #
    # sys.exit(0)

    while True:
        pot_value = adc.read_uv()
        r: str = "{0:.2f}mv".format(pot_value / 1000.0)
        print(r)
        mqttwrap.publish_one(mqttwrap.format_with_clientid(config.data["mosquitto"]["loggingfeed"]), r, qos=1,
                             retain=False, reset_if_mqtt_fails=True)
        # m.ping()
        sleep(5)
