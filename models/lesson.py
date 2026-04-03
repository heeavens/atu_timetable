from dataclasses import dataclass
from datetime import time


@dataclass
class Lesson:
    subject: str
    start_time: time
    end_time: time
    room: str
    building: str | None
    lecturer: str | None
    lesson_type: str
    maps_url: str
