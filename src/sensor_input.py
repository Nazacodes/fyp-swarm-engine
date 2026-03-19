# sensor_input.py

import logging
import random
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class TemperatureSource(ABC):
    @abstractmethod
    def read(self) -> float:
        ...


class MockTemperatureSource(TemperatureSource):
    def __init__(self, base_temp: float = 22.0, noise: float = 0.1):  # Reduced noise for better convergence
        # Start with random initial temp between 15-30°C
        self.base_temp = random.uniform(15.0, 30.0)
        self.noise = noise

    def read(self) -> float:
        return max(10.0, self.base_temp + random.uniform(-self.noise, self.noise))

    def apply_action(self, action: str) -> None:
        """Apply the chosen action to adjust the base temperature."""
        if action == "HEAT_UP":
            self.base_temp += 0.5
        elif action == "COOL_DOWN":
            self.base_temp -= 0.5
        # IDLE does nothing


class RealSensorSource(TemperatureSource):
    """Tries to use a real sensor; falls back to mock if not present."""

    def __init__(self, node_id: str):
        self._inner: Optional[TemperatureSource] = None
        self.node_id = node_id
        self._try_init()

    def _try_init(self):
        try:
            # Try DS18B20 first (1‑wire); simple example; adapt to your lib.
            self._inner = self._try_ds18b20()
            if self._inner:
                logger.info("[%s] using DS18B20", self.node_id)
                return
        except Exception as e:
            logger.warning("[%s] DS18B20 probe failed: %r", self.node_id, e)

        try:
            # Try DHT22.
            self._inner = self._try_dht22()
            if self._inner:
                logger.info("[%s] using DHT22", self.node_id)
                return
        except Exception as e:
            logger.warning("[%s] DHT22 probe failed: %r", self.node_id, e)

        self._inner = MockTemperatureSource()
        logger.info("[%s] no real sensor; using mock", self.node_id)

    def _try_ds18b20(self) -> Optional[TemperatureSource]:
        """Return DS18B20‑style sensor if module exists and device present."""
        try:
            import glob

            # Example 1‑wire path; adapt to your setup.
            base_dir = "/sys/bus/w1/devices/"
            device_folder = glob.glob(base_dir + "28*")
            if not device_folder:
                return None

            device_file = device_folder[0] + "/w1_slave"

            def read_temp():
                try:
                    with open(device_file, "r") as f:
                        lines = f.readlines()
                    if "YES" in lines[0]:
                        line = lines[1]
                        if "t=" in line:
                            temp_c = float(line.split("t=")[1]) / 1000.0
                            return temp_c
                except Exception:
                    pass
                return 22.0  # fallback

            return _SimpleDS18B20(read_temp)
        except (ImportError, ModuleNotFoundError):
            return None

    def _try_dht22(self) -> Optional[TemperatureSource]:
        """Return DHT22‑style sensor if module exists."""
        try:
            import board  # Adafruit–style
            import adafruit_dht

            dht = adafruit_dht.DHT22(board.D4)

            def read_temp():
                try:
                    # Pin 4 on RPi; adjust as needed.
                    temp = dht.temperature
                    if temp is not None:
                        return float(temp)
                except Exception:
                    pass
                return 22.0

            return _SimpleDHT22(read_temp)
        except (ImportError, ModuleNotFoundError, RuntimeError):
            return None

    def read(self) -> float:
        return self._inner.read()


class _SimpleDS18B20(TemperatureSource):
    def __init__(self, read_fn):
        self._read = read_fn

    def read(self) -> float:
        return self._read()


class _SimpleDHT22(TemperatureSource):
    def __init__(self, read_fn):
        self._read = read_fn

    def read(self) -> float:
        return self._read()
