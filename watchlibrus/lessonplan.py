import enum
from dataclasses import dataclass
from typing import List, Optional, Any

from librus import Lesson as LibrusLesson


@dataclass
class Lesson(object):
    day: int
    hour: int
    name: str
    time: str
    teacher: Optional[str]
    classroom: Optional[str]

    @staticmethod
    def from_librus_lesson(ll: LibrusLesson) -> 'Lesson':
        return Lesson(
            day=int(ll.day),
            hour=int(ll.index),
            name=ll.name,
            time=ll.time,
            teacher=ll.teacher,
            classroom=ll.classroom
        )

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'day': self.day,
            'hour': self.hour,
            'time': self.time,
            'classroom': self.classroom,
            'teacher': self.teacher
        }

    @staticmethod
    def from_dict(input_: dict) -> 'Lesson':
        return Lesson(
            name=input_['name'], day=input_['day'], hour=input_['hour'],
            time=input_['time'], classroom=input_['classroom'], teacher=input_['teacher'])


@dataclass
class LessonDelta(object):
    l1: Lesson
    l2: Lesson

    def __eq__(self, other):
        def _eq_l1_l2(l1: Lesson, l2: Lesson) -> bool:
            if l1 and l2:
                return compare_lessons(l1, l2) == LessonCompareResult.EQUALS
            return not l1 and not l2

        return _eq_l1_l2(self.l1, other.l1) and _eq_l1_l2(self.l2, other.l2)

    def __init__(self, l1: Optional[Lesson], l2: Optional[Lesson]) -> None:
        if not l1 and not l2:
            raise ValueError('Either l1 or l2 must not be None')
        self.l1 = l1
        self.l2 = l2

    @staticmethod
    def from_dict(dict_: dict) -> 'LessonDelta':
        d = dict_.get('lesson-1')
        l1 = Lesson.from_dict(d) if d else None
        d = dict_.get('lesson-2')
        l2 = Lesson.from_dict(d) if d else None
        return LessonDelta(l1=l1, l2=l2)


@dataclass
class LessonPlanComparison(object):
    lesson_deltas: List[LessonDelta]

    @staticmethod
    def from_dict_list(dict_list: List[dict]) -> 'LessonPlanComparison':
        return LessonPlanComparison(
            lesson_deltas=[LessonDelta.from_dict(d) for d in dict_list])


class LessonCompareResult(enum.Enum):
    DIFFERENT = 1,
    EQUALS = 2,
    OTHER = 3


def compare_lessons(l1: Lesson, l2: Lesson) -> LessonCompareResult:
    if (l1.day, l1.hour) == (l2.day, l2.hour):
        return LessonCompareResult.EQUALS \
            if (l1.time, l1.name, l1.teacher, l1.classroom) == (
            l2.time, l2.name, l2.teacher, l2.classroom) else LessonCompareResult.DIFFERENT
    else:
        return LessonCompareResult.OTHER


@dataclass
class LessonPlan(object):
    lessons: List[Lesson]

    def to_list(self) -> List[dict]:
        return [lesson.to_dict() for lesson in self.lessons]

    @staticmethod
    def from_dict_list(lessons: List[dict]) -> 'LessonPlan':
        return LessonPlan([Lesson.from_dict(d) for d in lessons])

    def compare(self, other: 'LessonPlan') -> LessonPlanComparison:
        output: List[LessonDelta] = []

        for l1 in self.lessons:
            found_equal = False
            found_different = False
            for l2 in other.lessons:
                c_result = compare_lessons(l1, l2)
                if c_result == LessonCompareResult.DIFFERENT:
                    found_different = True
                    output.append(LessonDelta(l1, l2))
                    break
                elif c_result == LessonCompareResult.EQUALS:
                    found_equal = True
                    break
            if not found_equal and not found_different:
                output.append(LessonDelta(l1, None))

        for l2 in other.lessons:
            found_equal = False
            found_different = False
            for l1 in self.lessons:
                c_result = compare_lessons(l1, l2)
                if c_result == LessonCompareResult.DIFFERENT:
                    found_different = True
                    break
                elif c_result == LessonCompareResult.EQUALS:
                    found_equal = True
                    break
            if not found_equal and not found_different:
                output.append(LessonDelta(None, l2))

        return LessonPlanComparison(lesson_deltas=output)
