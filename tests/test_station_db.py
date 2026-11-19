"""EiBi shortwave schedule lookups. No network: uses a small sample file.

Run: python3 -m tests.test_station_db
"""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from src.display.audio_panel import describe
from src.scanner.station_db import StationDB, _day_ok, season_code

SAMPLE = """kHz:75;Time(UTC):93;Days:59;ITU:49;Station:201;Lng:49;Target:62;Remarks:135;P:35;Start:60;Stop:60;
15140;0700-1900;;ALG;Ifrikya FM;A;WAf;o;0;;
15140;1600-1900;;CUB;Radio Habana Cuba;S;NAm;b;2;;[0126]
15140;1600-1630;Su;CUB;Radio Habana Cuba;EO;NAm;b;2;;
9580;2300-0100;Mo-Fr;USA;Night Owl Radio;E;NAm;;1;;
6070;0000-2400;;CAN;CFRX Toronto;E;ENA;;1;;
"""

utc = lambda *a: datetime(*a, tzinfo=timezone.utc)

assert season_code(utc(2026, 11, 18)) == "b26"
assert season_code(utc(2027, 2, 1)) == "b26"
assert season_code(utc(2027, 3, 27)) == "b26" and season_code(utc(2027, 3, 28)) == "a27"
assert season_code(utc(2026, 10, 24)) == "a26" and season_code(utc(2026, 10, 25)) == "b26"
print("  season codes: OK")

assert _day_ok("", 3) and _day_ok("Mo-Fr", 0) and not _day_ok("Mo-Fr", 5)
assert _day_ok("Sa,Su", 6) and not _day_ok("Su", 0) and _day_ok("1357", 4) and not _day_ok("1357", 1)
assert _day_ok("Fr-Mo", 6) and not _day_ok("Fr-Mo", 2)
print("  day rules: OK")

with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "sked-b26.csv").write_text(SAMPLE, encoding="latin-1")
    db = StationDB(Path(tmp), download=False)

    # Wed 2026-11-18 17:00 UTC: both 15140 broadcasts on; the one aimed at
    # North America is listed first.
    wed17 = utc(2026, 11, 18, 17, 0)
    assert db.identify(15140, wed17) == ("Radio Habana Cuba / Ifrikya FM", "Spanish"), db.identify(15140, wed17)
    assert db.label(15141, wed17).startswith("Radio Habana Cuba")      # ±2 kHz
    assert db.identify(15150, wed17) is None
    assert db.label(15140, utc(2026, 11, 18, 20, 0)) is None           # off air

    # 2300-0100 Mo-Fr: Friday 23:30 and Saturday 00:30 (Friday's broadcast) on,
    # Saturday 23:30 off
    assert db.label(9580, utc(2026, 11, 20, 23, 30))
    assert db.label(9580, utc(2026, 11, 21, 0, 30))
    assert db.label(9580, utc(2026, 11, 21, 23, 30)) is None
    assert db.label(6070, utc(2026, 11, 18, 3, 0)) == "CFRX Toronto (English)"
    assert {e.station for e in db.on_air(6000, 7000, wed17)} == {"CFRX Toronto"}
print("  lookups: OK")

title, detail, _ = describe({"device": "ham", "channel": "19m 15140", "freq_khz": 15140,
                             "station": "Radio Habana Cuba", "language": "Spanish"})
assert (title, detail) == ("Radio Habana Cuba", "15140 kHz · Spanish · 19m"), (title, detail)
print("  panel label: OK")
print("\nAll station schedule checks passed.")
