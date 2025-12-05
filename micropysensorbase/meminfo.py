import gc
import os

from . import logging

logger = logging.get_logger(__name__)
logger.setLevel(logging.INFO)

# import esp32, vfs
# p = esp32.Partition.find(esp32.Partition.TYPE_DATA, label='foo')
# vfs.mount(p, '/foo')

def df() -> str:
    s = os.statvfs('//')
    return '{0} MB'.format((s[0]*s[3])/1_048_576)

def free_mem() -> str:
    gc.collect()
    fm = gc.mem_free()
    ma = gc.mem_alloc()
    tot = fm + ma
    perc = '{0:.2f}%'.format(fm/tot*100)

    return 'Total:{0} Free:{1} ({2})'.format(tot, fm, perc)

def main() -> None:
    logger.info(df())
    logger.info(free_mem())


if __name__ == "__main__":
    main()



