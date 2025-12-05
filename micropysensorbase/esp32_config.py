import json

class ConfigSection:
    """Basis-Klasse für Config-Sektionen"""

    def __init__(self, data: dict | None = None) -> None:
        if data:
            self._load_from_dict(data)

    def _load_from_dict(self, data: dict) -> None:
        """Lädt Daten aus einem Dictionary"""
        for key, value in data.items():
            if isinstance(value, dict):
                # Verschachtelte Dicts als ConfigSection
                setattr(self, key, ConfigSection(value))
            else:
                setattr(self, key, value)

    def _merge(self, other: object) -> None:
        """Merged andere Config-Sektion in diese"""
        if not isinstance(other, (ConfigSection, dict)):
            return

        other_dict = other.__dict__ if isinstance(other, ConfigSection) else other

        for key, value in other_dict.items():
            if key.startswith('_'):
                continue

            if hasattr(self, key):
                existing = getattr(self, key)
                if isinstance(existing, ConfigSection) and isinstance(value, (ConfigSection, dict)):
                    existing._merge(value)
                else:
                    setattr(self, key, value)
            else:
                if isinstance(value, dict):
                    setattr(self, key, ConfigSection(value))
                else:
                    setattr(self, key, value)


class WiFiConfig(ConfigSection):
    """WiFi-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.SSID: str | None = None
        self.password: str | None = None
        self.retries: int = 10
        super().__init__(data)


class WebReplConfig(ConfigSection):
    """WebREPL-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.password: str | None = None
        super().__init__(data)


class MosquittoConfig(ConfigSection):
    """MQTT/Mosquitto-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.MOSQUITTO_USERNAME: str | None = None
        self.MOSQUITTO_PASSWORD: str | None = None
        self.MOSQUITTO_HOST: str | None = None
        self.MOSQUITTO_PORT: int = 1883
        self.lwtfeed: str | None = None
        self.statusfeed: str | None = None
        self.controlfeed: str | None = None
        self.loggingfeed: str | None = None
        self.mafeed: str | None = None
        self.busvoltagefeed: str | None = None
        self.wasserstandfeed: str | None = None
        self.dht11_temperaturefeed: str | None = None
        self.dht11_humidityfeed: str | None = None
        self.dht22_temperaturefeed: str | None = None
        self.dht22_humidityfeed: str | None = None
        self.lat_loc1: float | None = None
        self.lon_loc1: float | None = None
        self.ele_loc1: float | None = None
        self.lat_loc2: float | None = None
        self.lon_loc2: float | None = None
        self.ele_loc2: float | None = None
        super().__init__(data)


class I2CConfig(ConfigSection):
    """I2C-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.sda_pin: int = 21
        self.scl_pin: int = 22
        super().__init__(data)


class SMBusConfig(ConfigSection):
    """SMBus-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.sda: int = 21
        self.scl: int = 22
        super().__init__(data)


class INA226Config(ConfigSection):
    """INA226-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.shunt_ohms: float = 0.1
        self.max_expected_amps: float = 0.05
        self.address: int = 64
        super().__init__(data)


class ADCConfig(ConfigSection):
    """ADC-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.input_pin: int = 35
        super().__init__(data)


class DHTConfig(ConfigSection):
    """DHT-Sensor-Konfiguration (DHT11/DHT22)"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.input_pin: int = 35
        super().__init__(data)


class RotaryConfig(ConfigSection):
    """Rotary-Encoder-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.clk_pin: int = 25
        self.dt_pin: int = 26
        self.sw_pin: int = 27
        super().__init__(data)


class DigitalOutputConfig(ConfigSection):
    """Digital-Output-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.output_pin: int = 27
        super().__init__(data)


class DigitalInputConfig(ConfigSection):
    """Digital-Input-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.input_pin: int = 26
        super().__init__(data)


class WakeupDeepSleepConfig(ConfigSection):
    """Wakeup-DeepSleep-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.input_pin: int = 26
        super().__init__(data)


class PWMConfig(ConfigSection):
    """PWM-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.output_pin: int = 19
        super().__init__(data)


class UARTConfig(ConfigSection):
    """UART-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.rx_pin: int = 16
        self.tx_pin: int = 17
        super().__init__(data)


class DisplayConfig(ConfigSection):
    """Display-Konfiguration (SSD1306/SH1106)"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        self.address: int = 60
        self.width: int = 128
        self.height: int = 64
        self.flip_en: bool = False
        super().__init__(data)


class ESPNowPeerConfig(ConfigSection):
    """ESP-NOW Peer-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.mac: str | None = None
        self.lmk: str | None = None
        super().__init__(data)


class ESPNowConfig(ConfigSection):
    """ESP-NOW-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.channel: int = 7
        self.pmk: str | None = None
        self.peers: dict = {}
        super().__init__(data)

        # Peers als ConfigSection-Objekte konvertieren
        if isinstance(self.peers, dict):
            peers_dict: dict = {}
            for peer_name, peer_data in self.peers.items():
                if isinstance(peer_data, dict):
                    peers_dict[peer_name] = ESPNowPeerConfig(peer_data)
                else:
                    peers_dict[peer_name] = peer_data
            self.peers = peers_dict


class GetTimeESPNowConfig(ConfigSection):
    """Get-Time-per-ESPNow-Konfiguration"""

    def __init__(self, data: dict | None = None) -> None:
        self.enabled: bool = False
        super().__init__(data)


class ESP32Config:
    """Haupt-Config-Klasse für ESP32"""

    def __init__(self, config_file: str = 'esp32config.json') -> None:
        """
        Initialisiert die Config-Klasse

        Args:
            config_file: Pfad zur JSON-Config-Datei
        """
        self.config_file: str = config_file
        self._raw_config: dict = {}
        self.device_mac: str | None = None

        # Top-Level Config-Attribute
        self.boot_ssd: bool = False
        self.disable_autosetup: bool = False
        self.enable_watchdog: bool = True
        self.enable_lock: bool = True
        self.hostnameprefix: str = "micropyhydro_"
        self.hostname: str | None = None
        self.disable_inet: bool = False
        self.get_time_per_uart: bool = False
        self.measure_tele_period_s: int = 60
        self.chckmsgs_period_ms: int = 3000
        self.measuretimer_period_ms: int = 10000
        self.loglevel: dict[str, str] = {}
        self.forcerestart_after_running_seconds: int = 86400

        # Config-Sektionen als Klassen
        self.webrepl: WebReplConfig = WebReplConfig()
        self.wifi1: WiFiConfig = WiFiConfig()
        self.wifi2: WiFiConfig = WiFiConfig()
        self.wifi3: WiFiConfig = WiFiConfig()
        self.mosquitto: MosquittoConfig = MosquittoConfig()
        self.i2c: I2CConfig = I2CConfig()
        self.smbus: SMBusConfig = SMBusConfig()
        self.ina226: INA226Config = INA226Config()
        self.adc: ADCConfig = ADCConfig()
        self.dht11: DHTConfig = DHTConfig()
        self.dht22: DHTConfig = DHTConfig()
        self.rotary: RotaryConfig = RotaryConfig()
        self.digital_output: DigitalOutputConfig = DigitalOutputConfig()
        self.digital_input: DigitalInputConfig = DigitalInputConfig()
        self.wakeup_deepsleep_pin: WakeupDeepSleepConfig = WakeupDeepSleepConfig()
        self.pwm: PWMConfig = PWMConfig()
        self.uart: UARTConfig = UARTConfig()
        self.ssd1306: DisplayConfig = DisplayConfig()
        self.sh1106: DisplayConfig = DisplayConfig()
        self.espnow: ESPNowConfig = ESPNowConfig()
        self.get_time_per_espnow: GetTimeESPNowConfig = GetTimeESPNowConfig()

        self.load()

    def load(self) -> None:
        """Lädt die Config-Datei"""
        try:
            with open(self.config_file, 'r') as f:
                self._raw_config = json.load(f)
            self._parse_config(self._raw_config)
        except Exception as e:
            print(f"Fehler beim Laden der Config: {e}")
            self._raw_config = {}

    def _parse_config(self, config_dict: dict) -> None:
        """Parsed Config-Dictionary in Klassen-Attribute"""
        # Mapping von Config-Keys zu Attributen
        section_mapping = {
            'webrepl': (WebReplConfig, 'webrepl'),
            'wifi1': (WiFiConfig, 'wifi1'),
            'wifi2': (WiFiConfig, 'wifi2'),
            'wifi3': (WiFiConfig, 'wifi3'),
            'mosquitto': (MosquittoConfig, 'mosquitto'),
            'i2c': (I2CConfig, 'i2c'),
            'smbus': (SMBusConfig, 'smbus'),
            'ina226': (INA226Config, 'ina226'),
            'adc': (ADCConfig, 'adc'),
            'dht11': (DHTConfig, 'dht11'),
            'dht22': (DHTConfig, 'dht22'),
            'rotary': (RotaryConfig, 'rotary'),
            'digital_output': (DigitalOutputConfig, 'digital_output'),
            'digital_input': (DigitalInputConfig, 'digital_input'),
            'wakeup_deepsleep_pin': (WakeupDeepSleepConfig, 'wakeup_deepsleep_pin'),
            'pwm': (PWMConfig, 'pwm'),
            'uart': (UARTConfig, 'uart'),
            'ssd1306': (DisplayConfig, 'ssd1306'),
            'sh1106': (DisplayConfig, 'sh1106'),
            'espnow': (ESPNowConfig, 'espnow'),
            'get_time_per_espnow': (GetTimeESPNowConfig, 'get_time_per_espnow'),
        }

        for key, value in config_dict.items():
            # MAC-Adressen überspringen
            if len(key) == 12 and all(c in '0123456789abcdef' for c in key.lower()):
                continue

            if key in section_mapping:
                class_type, attr_name = section_mapping[key]
                setattr(self, attr_name, class_type(value))
            else:
                # Einfache oder dict-basierte Top-Level Werte (z.B. loglevel)
                setattr(self, key, value)

    def set_device_mac(self, mac: str) -> None:
        """
        Setzt die MAC-Adresse des Geräts für gerätespezifische Configs

        Args:
            mac: MAC-Adresse als String (z.B. "aabbccddeeff11")
        """
        self.device_mac = mac
        self._merge_device_config()

    def _merge_device_config(self) -> None:
        """Merged gerätespezifische Config mit globaler Config"""
        if not self.device_mac or self.device_mac not in self._raw_config:
            return

        device_config = self._raw_config[self.device_mac]

        # Top-Level Werte überschreiben
        for key, value in device_config.items():
            if not isinstance(value, dict):
                setattr(self, key, value)
            else:
                # Verschachtelte Sektionen mergen
                if hasattr(self, key):
                    section = getattr(self, key)
                    if isinstance(section, ConfigSection):
                        section._merge(value)


# Beispiel-Verwendung:
# config = ESP32Config('esp32config.json')
# config.set_device_mac('aabbccddeeff11')
# print(config.hostname)
# print(config.mosquitto.MOSQUITTO_HOST)
# print(config.i2c.enabled)
# print(config.wifi1.SSID)
# if config.espnow.peers:
#     for peer_name, peer in config.espnow.peers.items():
#         print(f"{peer_name}: {peer.mac}")
