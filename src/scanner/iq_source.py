"""Continuous IQ capture from one RTL-SDR dongle via SoapySDR."""
import logging
import queue
import threading

import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_RX

log = logging.getLogger(__name__)

BLOCK_SIZE = 32768  # samples per delivered block (~16 ms at 2.048 MS/s)
_READ_CHUNK = 16384  # samples per readStream call — large enough to drain the USB buffer promptly
# Discard this much IQ after tuning: the tuner/PLL settling produces a burst
# of junk that the detector reads as activity (seen as short false
# recordings right after an HF band switch).
SETTLE_S = 0.5


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
        dev = stream = None
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
            settle_blocks = int(SETTLE_S * self.sample_rate / BLOCK_SIZE)
            buf = np.zeros(_READ_CHUNK, dtype=np.complex64)

            _TIMEOUT = -1   # SoapySDR SOAPY_SDR_TIMEOUT — normal during startup
            _consecutive_errors = 0

            while not self._stop.is_set():
                sr = dev.readStream(stream, [buf], _READ_CHUNK)
                if sr.ret < 0:
                    if sr.ret != _TIMEOUT:
                        log.warning("readStream error %d (serial=%s)", sr.ret, self.serial)
                    _consecutive_errors += 1
                    if _consecutive_errors > 50:
                        log.error("Too many consecutive readStream errors — stopping capture")
                        break
                    continue
                _consecutive_errors = 0
                if sr.ret == 0:
                    continue

                # Copy into fixed-size blocks; samples past the end of one
                # block start the next (dropping them would put a gap in the
                # audio every time a read straddles a block boundary).
                n, src = sr.ret, 0
                while src < n:
                    take = min(n - src, BLOCK_SIZE - pos)
                    acc[pos:pos + take] = buf[src:src + take]
                    pos += take
                    src += take
                    if pos < BLOCK_SIZE:
                        break
                    pos = 0
                    if settle_blocks > 0:
                        settle_blocks -= 1
                        continue
                    try:
                        self._q.put_nowait(acc.copy())
                    except queue.Full:
                        pass  # consumer too slow; drop block

        except Exception:
            log.exception("IQSource thread crashed (serial=%s)", self.serial)
        finally:
            # Release the dongle explicitly so it can be reopened right away
            # (band switching retunes by stopping and restarting the source).
            if dev is not None and stream is not None:
                try:
                    dev.deactivateStream(stream)
                    dev.closeStream(stream)
                except Exception:
                    log.exception("Error closing stream (serial=%s)", self.serial)
            dev = None
            log.info("IQSource %s stopped", self.serial)
