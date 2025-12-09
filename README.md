[![mypy and pytests](https://github.com/vroomfondel/micropysensorbase/actions/workflows/mypynpytests.yml/badge.svg)](https://github.com/vroomfondel/micropysensorbase/actions/workflows/mypynpytests.yml)
![Cumulative Clones](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/vroomfondel/c17ace0474819e400a8369e269c21dc6/raw/micropysensorbase_clone_count.json)

# Some esp32 micropython sensor projectbase

Project containing base-logic / configurable boilerplate for connecting sensors via esp32 via mqtt to nodered/whatever

## Description

Initial/Main project goal was to setup a device (or to be precise a couple of those) to be put in drainage 
systems in the field(s) to monitor the water-levels in the drainage system shafts and thus the proper functioning 
of the drainage pumps and their triggering.


### Extended description

This repository provides a reusable MicroPython-based foundation for building ESP32 sensor nodes that publish
telemetry to an MQTT broker for downstream processing in Node-RED, time-series storage (e.g., InfluxDB), and
monitoring/alerting (e.g., Uptime Kuma). The reference implementation focuses on hydrostatic water-level
monitoring for agricultural drainage shafts and pump supervision, but the architecture is intentionally modular
to support additional sensors and use-cases.

- Purpose and scope
  - Enable rapid provisioning of one or more ESP32 devices that read sensor data (current, voltage, illumination,
    custom analog values, etc.) and reliably publish messages via Wi‑Fi/MQTT.
  - Provide configuration-driven setup (Wi‑Fi, MQTT, I2C, sensor parameters) without reflashing firmware.
  - Offer an opinionated example flow for transforming and visualizing the data using Node‑RED and InfluxDB,
    as well as basic uptime/health monitoring.

- Architecture at a glance
  - Device firmware: MicroPython running on ESP32 with boot/main entry points and a small set of modules for
    connectivity, configuration, sensor I/O (e.g., INA226), and MQTT publishing.
  - Transport: MQTT (tested with Mosquitto) using topic conventions that are easy to consume from Node‑RED.
  - Backend/visualization: Example Node‑RED flows for normalization/calibration and routing to time-series
    storage and monitoring dashboards (InfluxDB, Uptime Kuma). Grafana can be added if desired.

- Hardware reference (water‑level monitoring)
  - ESP32 board with Wi‑Fi
  - INA226-based current/voltage measurement and a DC‑DC boost converter (XL6009/XL6019) to power 24 V sensors
  - Hydrostatic water level sensor (e.g., TL‑136)
  - Optional custom PCB (KiCAD files provided) and simple printed enclosure (FreeCAD/STL provided)

- Software components
  - Wi‑Fi management with retry and configurable credentials
  - MQTT client wrapper for robust publish/subscribe behavior on lossy links
  - INA226 measurement driver and helpers for shunt/expected‑amps configuration
  - Simple logging and diagnostics utilities suitable for constrained devices

- Data flow (typical)
  1) Sensor read cycle on the ESP32 collects samples (e.g., current/voltage correlated to water level)
  2) Values are formatted and published to MQTT topics
  3) Node‑RED consumes topics, applies calibration/offsets, and forwards to InfluxDB
  4) Uptime‑Kuma (or similar) monitors device and pump activity for alerting

- Configuration
  - Central JSON config (`esp32config.json` or `esp32config.local.json`) governs Wi‑Fi networks, MQTT broker
    credentials, I2C pin mapping, and sensor specifics (shunt value, expected current range, etc.).
  - Behavior can be adapted per device without code changes by distributing a device‑local JSON file.

- Reliability and operations
  - Designed to run unattended in outdoor enclosures; on boot, devices connect, read, and publish on a schedule.
  - Example Node‑RED flows include basic normalization and can be extended for fault detection.
  - Power draw of pumps can be correlated using separate smart plugs (e.g., Tasmota) to verify actuation events.

- Security considerations
  - Use unique MQTT credentials per device and, where possible, TLS‑enabled brokers.
  - Isolate the IoT network segment and restrict broker access to trusted clients.

- Extensibility
  - Add new sensors by implementing lightweight drivers and publishing to the existing topic structure.
  - Swap storage/visualization backends with minimal changes on the server side.



## Getting Started

### Dependencies

#### hydrostatic water-level monitoring :: hardware / environment
  * hydrostatic water level sensor TL-136
  * esp32
  * INA226
  * XL6009 DC-DC boost converter (TL-136 wants 24V which will be created by this converter 
    from the voltage/current supplied by the esp32's voltage(regulator))
  * wiring / breadboard / soldering iron
  * waterproof box (used this one in the end: https://www.amazon.de/gp/product/B0751QPFKM)

#### **(Update 2025-11-09)** KiCAD :: PCB :: hydrostatic water-level monitoring :: hardware / environment
  * KiCAD project files for PCB creation (used https://aisler.net/ for this): [kicad_ina226_xl6019_esp32_EXPORT.zip](PCB/kicad_ina226_xl6019_esp32_EXPORT.zip)
  * [<img src="media/3d_pcb_render.jpg" width="650"/>](media/3d_pcb_render.jpg)
  * [<img src="media/ina226_xl6019_esp32_pcb.png" width="650">](media/ina226_xl6019_esp32_pcb.png)
  * [<img src="media/ina226_xl6019_esp32_schematic.png" width="650">](media/ina226_xl6019_esp32_schematic.pdf)
  * Received Board:<br/>
    [<img src="media/PXL_20251117_095251478_CUT.png" width="650">](...)
  * Soldered+Assembled (broke one unused socket from the pin header):<br/>
    [<img src="media/PXL_20251118_094316034.png" width="650">](...)
    [<img src="media/PXL_20251118_094311591.png" width="650">](...)

#### **(Update 2025-11-22)** FreeCAD :: PCB :: Enclosure
  * [<img src="media/Bildschirmfoto_freecad_espbox_sideview.png" width="650">](media/esp32ina226pcbbox-sideview.pdf)
  * [esp32ina226pcbbox.FCStd](media/esp32ina226pcbbox.FCStd)
  * [esp32ina226pcbbox-BoxBase.stl](media/esp32ina226pcbbox-BoxBase.stl)
  * [esp32ina226pcbbox-BoxLid.stl](media/esp32ina226pcbbox-BoxLid.stl)

#### software / environment
  * wifi
  * installed mqtt-server (we used a local mosquitto instance for that purpose)
  * not needed, but pretty much the sense of it all: installed monitoring solution (we chose uptime-kuma)
  * installed node-red (used for some data mapping for monitoring the levels in uptime-kuma and 
    normalizing data (also used for applying "calibration"-/offset-data gathered beforehand))
  * installed influxdb (used for storing data over time and also for displaying 
    metrics (i do not really like to configure grafana - which is of course a wonderful tool))

#### Notes
* Could also be adapted to be used via esp-now -> but that would need quite hefty (but manageable) adaption 
  in regards to the mqtt-logic
* nodered-screenshot does not contains flow for monitoring the power-draw/-usage by the pumps which are connected 
  via a tasmota-enabled switchable socket (nous-A1T)


### Installing

* install a fresh version of micropython on an esp32 with wifi capabilities 
* copy over all files found in this repo to the device
* either adapt esp32config.json or create a copy of esp32config.json named as esp32config.local.json and adapt settings therein such as:
  * wifi-networks credentials
  * mqtt-broker credentials
  * enable i2c and set pins appropriately
  * enable INA226 and set shunt and expected amps appropriately 
  * create proper logic in node red/monitoring in uptime-kuma

### Executing program

* since the code is placed in boot.py and main.py just booting/resetting the esp32 should make this work


## Authors

Contributors names and contact info

* This repo's owner
* Other people mentioned/credited in the files

## Version History

* -0.42
    * there will be no proper versioning
    * earlier versions used INA219, but INA226 seems to be 
      more accurate and can additionally/also monitor voltage on the high side whilst 
      monitoring current on the low side.
  

## License

This project is licensed under the LGPL where applicable/possible License - see the [LICENSE.md](LICENSE.md) file for details.
Some files/part of files could be governed by different/other licenses and/or licensors, 
such as (e.g., but not limited to) [MIT](LICENSEMIT.md) | [GPL](LICENSEGPL.md) | [LGPL](LICENSELGPL.md); so please also 
regard/pay attention to comments in regards to that throughout the codebase / files / part of files.

## Acknowledgments

Inspiration, code snippets, etc.
* please see comments in files for that


## some pictures of it
* [<img src="media/53604859770_0842156e31_o_noexif.jpg" width="650"/>](media/53604859770_0842156e31_o_noexif.jpg)
* [<img src="media/Bildschirmfoto_influxdb.png" width="650"/>](media/Bildschirmfoto_influxdb.png)
* [<img src="media/Bildschirmfoto_mqtt_explorer.png" width="650"/>](media/Bildschirmfoto_mqtt_explorer.png)
* [<img src="media/Bildschirmfoto_nodered.png" width="650"/>](media/Bildschirmfoto_nodered.png)
* [<img src="media/Bildschirmfoto_uptimekuma.png" width="650"/>](media/Bildschirmfoto_uptimekuma.png)


#### btw. removing (relevant) exif-data from jpg-files should be quite easy
* ```for i in *jpg ; do exif -o ${i%.jpg}_noexif.jpg --remove $i ; done```


## TODO
* could make it pull needed files from this repo based on actual enable config-options
* exception-handling // stacktrace-printing has a lot of duplicated code throughout the codebase
* use more subflows in nodered and not just copy-paste custom-nodes :slightly_frowning_face:
* provide (fritzing?!) wiring diagram maybe ?!
* make a 3d printed enclosure which better suits the circuitry (at the moment I just 
  threw that in an plastik bag into the outdoor-box)
* make a PCB


## "Bonus content"
### tasmota-rules used on the switchable socket
* ```{"Rule1":{"State":"ON","Once":"OFF","StopOnError":"OFF","Length":258,"Free":253,"Rules":"ON Time#Minute|5 DO BackLog WebQuery http://somehost.in.the.internet.de/ GET ENDON ON WebQuery#Data=Done DO Publish stat/tasmota_112233/CONNECTIVITY OK ENDON ON WebQuery#Data$!Done DO BackLog AP 0 ; Delay 400; Publish stat/tasmota_112233/CONNECTIVITY FAILED ENDON"}}```
* ```{"Rule2":{"State":"ON","Once":"OFF","StopOnError":"OFF","Length":313,"Free":198,"Rules":"ON Power1#state=1 DO var1 ON ENDON ON Power1#state=0 DO var1 OFF ENDON ON system#boot do Backlog Power1 ON; var1 ON; Publish2 tele/tasmota_112233/POWER_STATE %var1% ENDON ON Time#Minute|1 DO Publish2 tele/tasmota_112233/POWER_STATE %var1% ENDON on Energy#Power>0 do Publish tele/tasmota_112233/POWER %value% endon"}}```
* ```{"Rule3":{"State":"ON","Once":"ON","StopOnError":"OFF","Length":216,"Free":295,"Rules":"on Energy#Power>=10 do Publish tele/tasmota_112233/POWERTRIGGER 1 endon on Energy#Power<10 do Publish tele/tasmota_112233/POWERTRIGGER 0 endon on Energy#Power<=0.001 do Publish tele/tasmota_112233/POWER %value% endon"}}```
