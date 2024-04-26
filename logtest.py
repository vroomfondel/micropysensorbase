import time

import logging

#logging.basicConfig(level=logging.DEBUG, format="%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)

logger.debug("STARTING main.py")
logger.info("info log")
logger.warning("warn log")
logger.error("HUHU")
#logger.error("Some trouble (%s)", "expected")

try :
    raise Exception("HUHUHUWOWOWO")
except Exception as ex:
    logger.exception(ex)
