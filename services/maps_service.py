from config.mappings import GOOGLE_MAPS_FALLBACK_URL, MAZEMAP_BASE_URL, ROOM_COORDINATES


class MapsService:
    @staticmethod
    def get_maps_url(room: str) -> str:
        for prefix, coordinates in ROOM_COORDINATES.items():
            if room.upper().startswith(prefix):
                lat, lon = coordinates
                return f"{MAZEMAP_BASE_URL}?v=1&zlevel=1&center={lon},{lat}&zoom=18"
        return f"{GOOGLE_MAPS_FALLBACK_URL}{room}"
