"""OSM slippy-map tile fetching/caching and lat-lon <-> screen-pixel projection.

Tiles are fetched once from the public OSM tile server and cached to disk
forever after (base map imagery doesn't need refreshing). Per OSM's tile
usage policy: a descriptive User-Agent is sent, fetches are throttled, and
"(c) OpenStreetMap contributors" attribution must be shown on screen by the
caller. If usage ever grows beyond a personal kiosk, switch to a paid tile
provider (MapTiler, Thunderforest) or a self-hosted tile server instead of
hammering the free OSM server.
"""
import logging
import math
import time
from pathlib import Path

import pygame
import requests

log = logging.getLogger(__name__)

TILE_SIZE = 256
TILE_SERVER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "SDRScanner-ADSB-Display/1.0 (personal hobby ADS-B kiosk display)"
FETCH_DELAY_S = 0.15

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sdrscanner" / "tiles"

_FALLBACK_COLOR = (40, 40, 45)


def _lat_lon_to_tile_xy(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator projection: lat/lon -> fractional tile x/y at given zoom."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y


_MILES_PER_DEG_LAT = 69.0


def zoom_for_radius_miles(center_lat_deg: float, radius_miles: float, screen_h_px: int) -> int:
    """Smallest integer zoom whose vertical extent (the tighter screen dimension,
    since screens are wider than tall) covers at least `radius_miles` above and
    below center. Horizontal extent ends up larger, which is fine — extra margin
    on the sides, never less than the requested radius in any direction."""
    target_height_deg = (2.0 * radius_miles) / _MILES_PER_DEG_LAT
    sec_lat = 1.0 / math.cos(math.radians(center_lat_deg))
    # pixels_per_degree_lat = TILE_SIZE * n * sec_lat / 360  (Mercator y-derivative)
    # screen_h_px == target_height_deg * pixels_per_degree_lat  -->  solve for n
    n = screen_h_px * 360.0 / (target_height_deg * TILE_SIZE * sec_lat)
    zoom = round(math.log2(n))
    return max(2, min(19, zoom))


class MapView:
    """Projects lat/lon to screen pixels and builds a cached OSM tile background."""

    def __init__(self, center_lat: float, center_lon: float, zoom: int,
                 screen_w: int, screen_h: int, cache_dir: Path = DEFAULT_CACHE_DIR):
        self.zoom = zoom
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.cache_dir = Path(cache_dir)

        cx, cy = _lat_lon_to_tile_xy(center_lat, center_lon, zoom)
        center_px_x, center_px_y = cx * TILE_SIZE, cy * TILE_SIZE
        # Screen-space origin, in global pixel coordinates at this zoom level
        self.origin_px_x = center_px_x - screen_w / 2
        self.origin_px_y = center_px_y - screen_h / 2

    def latlon_to_screen(self, lat: float, lon: float) -> tuple[int, int]:
        x, y = _lat_lon_to_tile_xy(lat, lon, self.zoom)
        px_x, px_y = x * TILE_SIZE, y * TILE_SIZE
        return int(px_x - self.origin_px_x), int(px_y - self.origin_px_y)

    def build_background(self) -> pygame.Surface:
        bg = pygame.Surface((self.screen_w, self.screen_h))
        x0 = int(self.origin_px_x // TILE_SIZE)
        y0 = int(self.origin_px_y // TILE_SIZE)
        x1 = int((self.origin_px_x + self.screen_w) // TILE_SIZE)
        y1 = int((self.origin_px_y + self.screen_h) // TILE_SIZE)

        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

        n_tiles = 2 ** self.zoom
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if not (0 <= tx < n_tiles and 0 <= ty < n_tiles):
                    continue
                tile_surf = self._get_tile(session, tx, ty)
                dest_x = int(tx * TILE_SIZE - self.origin_px_x)
                dest_y = int(ty * TILE_SIZE - self.origin_px_y)
                bg.blit(tile_surf, (dest_x, dest_y))
        return bg

    def _get_tile(self, session: requests.Session, x: int, y: int) -> pygame.Surface:
        path = self.cache_dir / str(self.zoom) / str(x) / f"{y}.png"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            url = TILE_SERVER.format(z=self.zoom, x=x, y=y)
            try:
                log.info("Fetching tile %s", url)
                resp = session.get(url, timeout=10)
                resp.raise_for_status()
                path.write_bytes(resp.content)
                time.sleep(FETCH_DELAY_S)
            except (requests.RequestException, OSError) as e:
                log.warning("Tile fetch failed for z=%d x=%d y=%d: %s", self.zoom, x, y, e)
                fallback = pygame.Surface((TILE_SIZE, TILE_SIZE))
                fallback.fill(_FALLBACK_COLOR)
                return fallback

        try:
            return pygame.image.load(str(path))
        except pygame.error as e:
            log.warning("Corrupt cached tile %s: %s", path, e)
            path.unlink(missing_ok=True)
            fallback = pygame.Surface((TILE_SIZE, TILE_SIZE))
            fallback.fill(_FALLBACK_COLOR)
            return fallback
