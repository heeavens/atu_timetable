from dataclasses import dataclass, field
from datetime import date

from models.lesson import Lesson


@dataclass
class DaySchedule:
    date: date
    lessons: list[Lesson] = field(default_factory=list)
