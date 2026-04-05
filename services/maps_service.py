import logging
import re
from urllib.parse import urlencode

import aiohttp

from config.mappings import (
    MAZEMAP_API_URL,
    MAZEMAP_BASE_URL,
    MAZEMAP_CAMPUS_ID,
    MAZEMAP_FALLBACK_URL,
)

logger = logging.getLogger(__name__)

# Finds all groups of consecutive digits in a string
_ALL_DIGITS_RE = re.compile(r"\d+")


class MapsService:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    @staticmethod
    def _extract_room_number(room: str) -> str:
        """Extract the clean room number from any timetable room string.

        Always pulls out just the numeric room identifier, regardless of
        any prefix, suffix, dashes, or descriptive text.

        'GA 0903'              → '903'
        'GA 0436 COMP LAB 5'   → '436'
        'GA 1000'              → '1000'
        '903'                  → '903'
        'Room 0903'            → '903'
        'LC-0903'              → '903'
        'Block B 436'          → '436'
        'GALWAY 0903 Theatre'  → '903'
        'B2-204'               → '204'
        """
        numbers = _ALL_DIGITS_RE.findall(room)
        if not numbers:
            return room.strip()

        # Prefer the first number that is 3+ digits (after stripping
        # leading zeros), as room numbers at ATU are typically 3-4 digits
        for num in numbers:
            stripped = num.lstrip("0") or "0"
            if len(stripped) >= 3:
                return stripped

        # Fallback: first number stripped of leading zeros
        return numbers[0].lstrip("0") or numbers[0]

    async def get_maps_url(self, room: str) -> str:
        clean_room = self._extract_room_number(room)
        cache_key = clean_room.upper()

        logger.info(
            "MazeMap: raw room='%s' → clean='%s'",
            room,
            clean_room,
        )

        if cache_key in self._cache:
            return self._cache[cache_key]

        url = await self._lookup_poi(clean_room)
        self._cache[cache_key] = url
        return url

    async def _lookup_poi(self, room: str) -> str:
        params = {
            "q": room,
            "campusid": MAZEMAP_CAMPUS_ID,
            "rows": 10,
            "lang": "en",
        }
        request_url = f"{MAZEMAP_API_URL}?{urlencode(params)}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    request_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "MazeMap API returned %d for room '%s'",
                            resp.status,
                            room,
                        )
                        return MAZEMAP_FALLBACK_URL

                    data = await resp.json()

            results = data.get("result", [])
            if not results:
                logger.info(
                    "MazeMap: no results for room '%s'", room
                )
                return MAZEMAP_FALLBACK_URL

            poi = self._find_best_match(results, room)
            if not poi:
                logger.info(
                    "MazeMap: no match for room '%s'", room
                )
                return MAZEMAP_FALLBACK_URL

            return self._build_url(poi, room)

        except Exception as exc:
            logger.warning(
                "MazeMap API error for room '%s': %s", room, exc
            )
            return MAZEMAP_FALLBACK_URL

    def _find_best_match(
        self, results: list[dict], room: str
    ) -> dict | None:
        """Find the result whose poiNames contain an exact match
        for the requested room number."""
        room_upper = room.strip().upper()

        # Priority 1: exact match in poiNames
        for poi in results:
            poi_names = poi.get("poiNames", [])
            for name in poi_names:
                if name.strip().upper() == room_upper:
                    logger.info(
                        "MazeMap: room '%s' matched poiId=%s (%s)",
                        room,
                        poi.get("poiId"),
                        poi.get("dispBldNames", ["?"])[0],
                    )
                    return poi

        # Priority 2: exact match in title (strip HTML <em> tags)
        for poi in results:
            title = poi.get("title", "")
            clean_title = (
                title.replace("<em>", "")
                .replace("</em>", "")
                .strip()
                .upper()
            )
            if clean_title == room_upper:
                return poi

        # No exact match — don't guess
        return None

    def _build_url(self, poi: dict, room: str) -> str:
        poi_id = poi.get("poiId")
        z_value = poi.get("zValue", 1)
        geometry = poi.get("point") or poi.get("geometry", {})
        coords = geometry.get("coordinates", [])

        if not poi_id:
            return MAZEMAP_FALLBACK_URL

        lon = coords[0] if len(coords) > 0 else -9.011044
        lat = coords[1] if len(coords) > 1 else 53.277990

        url = (
            f"{MAZEMAP_BASE_URL}"
            f"#v=1"
            f"&campusid={MAZEMAP_CAMPUS_ID}"
            f"&zlevel={int(z_value)}"
            f"&center={lon},{lat}"
            f"&zoom=18.7"
            f"&sharepoitype=poi"
            f"&sharepoi={poi_id}"
        )

        logger.info(
            "MazeMap: room '%s' → poiId=%s (%s)",
            room,
            poi_id,
            poi.get("dispBldNames", ["?"])[0],
        )
        return url
