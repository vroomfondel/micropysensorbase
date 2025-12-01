#
# MicroPython SH1106 OLED driver, I2C and SPI interfaces
#
# The MIT License (MIT)
#
# Copyright (c) 2016 Radomir Dopieralski (@deshipu),
#               2017-2021 Robert Hammelrath (@robert-hh)
#               2021 Tim Weber (@scy)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Sample code sections for ESP8266 pin assignments
# ------------ SPI ------------------
# Pin Map SPI
#   - 3v - xxxxxx   - Vcc
#   - G  - xxxxxx   - Gnd
#   - D7 - GPIO 13  - Din / MOSI fixed
#   - D5 - GPIO 14  - Clk / Sck fixed
#   - D8 - GPIO 4   - CS (optional, if the only connected device)
#   - D2 - GPIO 5   - D/C
#   - D1 - GPIO 2   - Res
#
# for CS, D/C and Res other ports may be chosen.
#
# from machine import Pin, SPI
# import sh1106

# spi = SPI(1, baudrate=1000000)
# display = sh1106.SH1106_SPI(128, 64, spi, Pin(5), Pin(2), Pin(4))
# display.sleep(False)
# display.fill(0)
# display.text('Testing 1', 0, 0, 1)
# display.show()
#
# --------------- I2C ------------------
#
# Pin Map I2C
#   - 3v - xxxxxx   - Vcc
#   - G  - xxxxxx   - Gnd
#   - D2 - GPIO 5   - SCK / SCL
#   - D1 - GPIO 4   - DIN / SDA
#   - D0 - GPIO 16  - Res
#   - G  - xxxxxx     CS
#   - G  - xxxxxx     D/C
#
# Pin's for I2C can be set almost arbitrary
#
# from machine import Pin, I2C
# import sh1106
#
# i2c = I2C(scl=Pin(5), sda=Pin(4), freq=400000)
# display = sh1106.SH1106_I2C(128, 64, i2c, Pin(16), 0x3c)
# display.sleep(False)
# display.fill(0)
# display.text('Testing 1', 0, 0, 1)
# display.show()

from micropython import const
import time
import framebuf

import machine


# a few register definitions
_SET_CONTRAST        = const(0x81)
_SET_NORM_INV        = const(0xa6)
_SET_DISP            = const(0xae)
_SET_SCAN_DIR        = const(0xc0)
_SET_SEG_REMAP       = const(0xa0)
_LOW_COLUMN_ADDRESS  = const(0x00)
_HIGH_COLUMN_ADDRESS = const(0x10)
_SET_PAGE_ADDRESS    = const(0xB0)


class SH1106(framebuf.FrameBuffer):
    def __init__(self, width: int, height: int, external_vcc: bool, rotate: int=0):
        self.width: int = width
        self.height: int = height
        self.external_vcc: bool = external_vcc
        self.flip_en: bool = rotate == 180 or rotate == 270
        self.rotate90: bool = rotate == 90 or rotate == 270
        self.pages: int = self.height // 8
        self.bufsize: int = self.pages * self.width
        self.renderbuf: bytearray = bytearray(self.bufsize)
        self.pages_to_update: int = 0
        self.res: machine.Pin|None = None
        self.delay: float|None = None

        if self.rotate90:
            self.displaybuf = bytearray(self.bufsize)
            # HMSB is required to keep the bit order in the render buffer
            # compatible with byte-for-byte remapping to the display buffer,
            # which is in VLSB. Else we'd have to copy bit-by-bit!
            super().__init__(self.renderbuf, self.height, self.width,
                             framebuf.MONO_HMSB)
        else:
            self.displaybuf = self.renderbuf
            super().__init__(self.renderbuf, self.width, self.height,
                             framebuf.MONO_VLSB)

        # flip() was called rotate() once, provide backwards compatibility.
        self.rotate = self.flip
        self.init_display()

    def init_display(self) -> None:
        self.reset(self.res)
        self.fill(0)
        self.show()
        self.poweron()
        # rotate90 requires a call to flip() for setting up.
        self.flip(self.flip_en)

    def poweroff(self) -> None:
        self.write_cmd(_SET_DISP | 0x00)

    def poweron(self) -> None:
        self.write_cmd(_SET_DISP | 0x01)
        if self.delay:
            time.sleep_ms(self.delay)  # type: ignore[attr-defined]

    def flip(self, flag: bool|None=None, update: bool=True) -> None:
        if flag is None:
            flag = not self.flip_en
        mir_v = flag ^ self.rotate90
        mir_h = flag
        self.write_cmd(_SET_SEG_REMAP | (0x01 if mir_v else 0x00))
        self.write_cmd(_SET_SCAN_DIR | (0x08 if mir_h else 0x00))
        self.flip_en = flag
        if update:
            self.show(True) # full update

    def sleep(self, value: bool) -> None:
        self.write_cmd(_SET_DISP | (not value))

    def contrast(self, contrast: int) -> None:
        self.write_cmd(_SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert: bool) -> None:
        self.write_cmd(_SET_NORM_INV | (invert & 1))

    def show(self, full_update: bool = False) -> None:
        # self.* lookups in loops take significant time (~4fps).
        (w, p, db, rb) = (self.width, self.pages,
                          self.displaybuf, self.renderbuf)
        if self.rotate90:
            for i in range(self.bufsize):
                db[w * (i % p) + (i // p)] = rb[i]
        if full_update:
            pages_to_update = (1 << self.pages) - 1
        else:
            pages_to_update = self.pages_to_update
        #print("Updating pages: {:08b}".format(pages_to_update))
        for page in range(self.pages):
            if (pages_to_update & (1 << page)):
                self.write_cmd(_SET_PAGE_ADDRESS | page)
                self.write_cmd(_LOW_COLUMN_ADDRESS | 2)
                self.write_cmd(_HIGH_COLUMN_ADDRESS | 0)
                self.write_data(db[(w*page):(w*page+w)])
        self.pages_to_update = 0

    def pixel(self, x: int, y: int, color: int|None=None) -> int:
        if color is None:
            return super().pixel(x, y)

        ret: int = super().pixel(x, y , color)  # type: ignore
        page = y // 8
        self.pages_to_update |= 1 << page
        return ret

    def text(self, text: str, x: int, y: int, color: int=1) -> None:
        super().text(text, x, y, color)
        self.register_updates(y, y+7)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: int) -> None:
        super().line(x0, y0, x1, y1, color)
        self.register_updates(y0, y1)

    def hline(self, x: int, y: int, w: int, color: int) -> None:
        super().hline(x, y, w, color)
        self.register_updates(y)

    def vline(self, x: int, y: int, h: int, color: int) -> None:
        super().vline(x, y, h, color)
        self.register_updates(y, y+h-1)

    def fill(self, color: int) -> None:
        super().fill(color)
        self.pages_to_update = (1 << self.pages) - 1

    def blit(self, fbuf: framebuf.FrameBuffer, x: int, y: int, key: int=-1, palette: bytes|None=None) -> None:
        super().blit(fbuf, x, y, key, palette)
        self.register_updates(y, y+self.height)

    def scroll(self, x: int, y: int) -> None:
        # my understanding is that scroll() does a full screen change
        super().scroll(x, y)
        self.pages_to_update =  (1 << self.pages) - 1

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        super().fill_rect(x, y, w, h, color)
        self.register_updates(y, y+h-1)

    def rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        super().rect(x, y, w, h, color)
        self.register_updates(y, y+h-1)

    def register_updates(self, y0: int, y1: int|None=None) -> None:
        # this function takes the top and optional bottom address of the changes made
        # and updates the pages_to_change list with any changed pages
        # that are not yet on the list
        start_page = max(0, y0 // 8)
        end_page = max(0, y1 // 8) if y1 is not None else start_page
        # rearrange start_page and end_page if coordinates were given from bottom to top
        if start_page > end_page:
            start_page, end_page = end_page, start_page
        for page in range(start_page, end_page+1):
            self.pages_to_update |= 1 << page

    def reset(self, res: machine.Pin|None) -> None:
        if res is not None:
            res(1)
            time.sleep_ms(1)  # type: ignore[attr-defined]
            res(0)
            time.sleep_ms(20)  # type: ignore[attr-defined]
            res(1)
            time.sleep_ms(20)  # type: ignore[attr-defined]


    def write_cmd(self, cmd: int) -> None:
        raise NotImplementedError("Subclasses must implement write_cmd()")

    def write_data(self, buf: bytearray) -> None:
        raise NotImplementedError("Subclasses must implement write_data()")


class SH1106_I2C(SH1106):
    def __init__(self,
                 width: int,
                 height: int,
                 i2c: machine.SoftI2C|machine.I2C,
                 res: machine.Pin|None,
                 addr: int=0x3c,
                 rotate: int=0,
                 external_vcc: bool=False,
                 delay: float=0):
        self.i2c = i2c
        self.addr = addr
        self.res = res
        self.temp = bytearray(2)
        self.delay = delay
        if res is not None:
            res.init(res.OUT, value=1)
        super().__init__(width, height, external_vcc, rotate)

    def write_cmd(self, cmd: int) -> None:
        self.temp[0] = 0x80  # Co=1, D/C#=0
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf: bytearray) -> None:
        self.i2c.writeto(self.addr, b'\x40'+buf)

    def reset(self, _: machine.Pin|None=None) -> None:
        super().reset(self.res)


class SH1106_SPI(SH1106):
    def __init__(self,
                 width: int,
                 height: int,
                 spi: machine.SoftSPI|machine.SPI,
                 dc: machine.Pin,
                 res: machine.Pin|None=None,
                 cs: machine.Pin|None=None,
                 rotate: int=0,
                 external_vcc: bool=False,
                 delay: float=0):
        dc.init(dc.OUT, value=0)
        if res is not None:
            res.init(res.OUT, value=0)
        if cs is not None:
            cs.init(cs.OUT, value=1)
        self.spi = spi
        self.dc = dc
        self.res = res
        self.cs = cs
        self.delay = delay
        super().__init__(width, height, external_vcc, rotate)

    def write_cmd(self, cmd: int) -> None:
        if self.cs is not None:
            self.cs(1)
            self.dc(0)
            self.cs(0)
            self.spi.write(bytearray([cmd]))
            self.cs(1)
        else:
            self.dc(0)
            self.spi.write(bytearray([cmd]))

    def write_data(self, buf: bytearray) -> None:
        if self.cs is not None:
            self.cs(1)
            self.dc(1)
            self.cs(0)
            self.spi.write(buf)
            self.cs(1)
        else:
            self.dc(1)
            self.spi.write(buf)

    def reset(self, _: machine.Pin|None=None) -> None:
        super().reset(self.res)
