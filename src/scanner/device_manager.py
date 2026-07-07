"""Discover and enumerate connected RTL-SDR dongles via SoapySDR."""
import logging
import SoapySDR

log = logging.getLogger(__name__)


def list_connected_devices() -> list[dict]:
    """Return a list of connected RTL-SDR devices with their serials."""
    results = SoapySDR.Device.enumerate({"driver": "rtlsdr"})
    devices = []
    for r in results:
        # SoapySDRKwargs supports [] access but not .get(); convert to plain dict
        r_dict = dict(r)
        devices.append({
            "serial": r_dict.get("serial", ""),
            "label":  r_dict.get("label", ""),
            "driver": r_dict.get("driver", ""),
        })
    return devices


def open_device(serial: str) -> SoapySDR.Device:
    dev = SoapySDR.Device({"driver": "rtlsdr", "serial": serial})
    log.info("Opened device serial=%s", serial)
    return dev


def configure_rx(dev: SoapySDR.Device, freq_hz: float, sample_rate: float,
                 gain: float | None = None, ppm: int = 0) -> None:
    dev.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate)
    dev.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq_hz)
    if gain is not None:
        dev.setGain(SoapySDR.SOAPY_SDR_RX, 0, gain)
    else:
        dev.setGainMode(SoapySDR.SOAPY_SDR_RX, 0, True)  # AGC
    if ppm:
        dev.setFrequencyCorrection(SoapySDR.SOAPY_SDR_RX, 0, float(ppm))
