import io
import os
import webrepl

class DUP(io.IOBase):

    def __init__(self, s):
        self.s = s

    def write(self, data):
        self.s += data
        return len(data)

    def readinto(self, data):
        return 0

s = bytearray()
os.dupterm(DUP(s))
help(webrepl)
os.dupterm(None)
print(bytes(s).decode())