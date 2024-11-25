# https://github.com/orgs/micropython/discussions/13177
# https://github.com/orgs/micropython/discussions/9661

from machine import Pin
from time import sleep
from neopixel import NeoPixel

pin = Pin(48, Pin.OUT)   # set GPIO48  to output to drive NeoPixel
neo = NeoPixel(pin,
               1,  # 1 pixel
               3, # RGB | 4 RGBW
               1 # 800khz | 0 400 khz
               )   # create NeoPixel driver on GPIO48 for 1 pixel




neo[0] = (255, 255, 255) # set the first pixel to white

neo.write()              # write data to all pixels


r, g, b= neo[0]         # get first pixel colour
print(f"{r=}, {g=}, {b=}")

sleep(5)



neo.fill( (100,100,100) )
neo.write()
sleep(5)

while (True):
    print("woop.")
    neo[0] = (255,0,0)
    neo.write()
    sleep(1)
    neo[0] = (0,255,0)
    neo.write()
    sleep(1)
    neo[0] = (0,0,255)
    neo.write()
    sleep(1)