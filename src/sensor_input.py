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

    def apply_action(self, action: str) -> None:
        pass


class MockTemperatureSource(TemperatureSource):
    """Mock with internal state that responds to actions."""

    def __init__(self, start_temp: float = 18.0, target_temp: float = 22.0):
        self._internal_temp = start_temp
        self._target_temp = target_temp
        self._ambient_temp = start_temp

    def read(self) -> float:
        noise = random.uniform(-0.06, 0.06)
        return round(self._internal_temp + noise, 2)

    def apply_action(self, action: str) -> None:
        error = self._target_temp - self._internal_temp
        ambient_pull = (self._ambient_temp - self._internal_temp) * 0.01

        if abs(error) < 0.3:
            step = 0.015
        elif abs(error) < 1.0:
            step = 0.04
        else:
            step = 0.10

        if action == "HEAT_UP":
            self._internal_temp += step
        elif action == "COOL_DOWN":
            self._internal_temp -= step
        else:
            self._internal_temp += error * 0.015

        self._internal_temp += ambient_pull
        self._internal_temp = max(10.0, min(35.0, self._internal_temp))


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

    def apply_action(self, action: str) -> None:
        if hasattr(self._inner, 'apply_action'):
            self._inner.apply_action(action)


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
