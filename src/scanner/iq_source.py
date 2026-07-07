"""Continuous IQ capture from one RTL-SDR dongle via SoapySDR."""
import logging
import queue
import threading

import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

log = logging.getLogger(__name__)

BLOCK_SIZE = 32768  # samples per delivered block (~16 ms at 2.048 MS/s)
_READ_CHUNK = 4096  # samples requested per readStream call


class IQSource:
    def __init__(self, serial: str, center_freq: float, sample_rate: float,
                 gain: float | None = None, ppm: int = 0, queue_depth: int = 8):
        self.serial = serial
        self.center_freq = center_freq
        self.sample_rate = sample_rate
        self.gain = gain
        self.ppm = ppm
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=queue_depth)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"iq-{self.serial}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def get_block(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    # ── private ────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        try:
            dev = SoapySDR.Device({"driver": "rtlsdr", "serial": self.serial})
            dev.setSampleRate(SOAPY_SDR_RX, 0, self.sample_rate)
            dev.setFrequency(SOAPY_SDR_RX, 0, self.center_freq)
            if self.gain is not None:
                dev.setGain(SOAPY_SDR_RX, 0, self.gain)
            else:
                dev.setGainMode(SOAPY_SDR_RX, 0, True)
            if self.ppm:
                dev.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(self.ppm))

            stream = dev.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
            dev.activateStream(stream)
            log.info("IQSource %s: %.3f MHz, %.0f S/s", self.serial,
                     self.center_freq / 1e6, self.sample_rate)

            acc = np.zeros(BLOCK_SIZE, dtype=np.complex64)
            pos = 0
            buf = np.zeros(_READ_CHUNK, dtype=np.complex64)

            while not self._stop.is_set():
                sr = dev.readStream(stream, [buf], _READ_CHUNK)
                if sr.ret < 0:
                    log.warning("readStream error %d (serial=%s)", sr.ret, self.serial)
                    continue
                if sr.ret == 0:
                    continue

                n = sr.ret
                remaining = BLOCK_SIZE - pos
                if n <= remaining:
                    acc[pos:pos + n] = buf[:n]
                    pos += n
                else:
                    acc[pos:] = buf[:remaining]
                    pos = BLOCK_SIZE

                if pos >= BLOCK_SIZE:
                    try:
                        self._q.put_nowait(acc.copy())
                    except queue.Full:
                        pass  # consumer too slow; drop block
                    pos = 0

        except Exception:
            log.exception("IQSource thread crashed (serial=%s)", self.serial)
        finally:
            log.info("IQSource %s stopped", self.serial)
