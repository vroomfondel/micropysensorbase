#!/bin/bash

cd $(dirname $0)

./compile_mpy_cross.sh

mpremote fs -r mkdir /lib/micropysensorbase
mpremote fs cp -r micropysensorbase/*mpy micropysensorbase/*json :lib/micropysensorbase/

mpremote fs cp main.py boot.py esp32config.local.json :/
