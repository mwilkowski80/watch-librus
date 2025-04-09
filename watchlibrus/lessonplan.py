import enum
from dataclasses import dataclass
from typing import List, Optional

from watchlibrus.librus import Lesson as LibrusLesson


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
            name=input_['name'],
            day=input_['day'],
            hour=input_['hour'],
            time=input_['time'],
            classroom=input_['classroom'],
            teacher=input_['teacher']
        )


@dataclass
class LessonDelta(object):
    l1: Optional[Lesson]  # Previous lesson
    l2: Optional[Lesson]  # New lesson

    def __init__(self, l1: Optional[Lesson], l2: Optional[Lesson]) -> None:
        if not l1 and not l2:
            raise ValueError('Either l1 or l2 must not be None')
        self.l1 = l1
        self.l2 = l2

    def __eq__(self, other):
        def _eq_l1_l2(a: Optional[Lesson], b: Optional[Lesson]) -> bool:
            if a and b:
                return compare_lessons(a, b) == LessonCompareResult.EQUALS
            return (a is None) and (b is None)
        return _eq_l1_l2(self.l1, other.l1) and _eq_l1_l2(self.l2, other.l2)

    @staticmethod
    def from_dict(dict_: dict) -> 'LessonDelta':
        d1 = dict_.get('lesson-1')
        l1 = Lesson.from_dict(d1) if d1 else None
        d2 = dict_.get('lesson-2')
        l2 = Lesson.from_dict(d2) if d2 else None
        return LessonDelta(l1=l1, l2=l2)


@dataclass
class LessonPlanComparison(object):
    lesson_deltas: List[LessonDelta]

    @staticmethod
    def from_dict_list(dict_list: List[dict]) -> 'LessonPlanComparison':
        return LessonPlanComparison(
            lesson_deltas=[LessonDelta.from_dict(d) for d in dict_list]
        )

    def is_change(self) -> bool:
        return len(self.lesson_deltas) > 0


class LessonCompareResult(enum.Enum):
    DIFFERENT = 1
    EQUALS = 2
    OTHER = 3


def compare_lessons(l1: Lesson, l2: Lesson) -> LessonCompareResult:
    """Compare two lessons based on their attributes.
    
    Returns:
        EQUALS if lessons are at the same time and have same content
        DIFFERENT if lessons are at the same time but content differs
        OTHER if lessons are at different times
    """
    if (l1.day, l1.hour) == (l2.day, l2.hour):
        if (l1.time, l1.name, l1.teacher, l1.classroom) == (l2.time, l2.name, l2.teacher, l2.classroom):
            return LessonCompareResult.EQUALS
        return LessonCompareResult.DIFFERENT
    return LessonCompareResult.OTHER


@dataclass
class LessonPlan(object):
    lessons: List[Lesson]

    def to_list(self) -> List[dict]:
        return [lesson.to_dict() for lesson in self.lessons]

    @staticmethod
    def from_dict_list(lessons: List[dict]) -> 'LessonPlan':
        return LessonPlan([Lesson.from_dict(d) for d in lessons])

    def filter_by_day(self, day: int) -> 'LessonPlan':
        """Returns a new LessonPlan containing only lessons for the specified day."""
        return LessonPlan([l for l in self.lessons if l.day == day])

    def compare(self, other: 'LessonPlan') -> LessonPlanComparison:
        """Compare this lesson plan with another one.
        
        Returns a LessonPlanComparison object containing:
        - Lessons that exist in both plans but are different
        - Lessons that exist only in this plan (l1=lesson, l2=None)
        - Lessons that exist only in the other plan (l1=None, l2=lesson)
        """
        output = []
        
        # Find modified and removed lessons
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
                output.append(LessonDelta(l1, None))  # Lesson was removed

        # Find added lessons
        for l2 in other.lessons:
            found_equal = False
            found_different = False
            for l1 in self.lessons:
                c_result = compare_lessons(l1, l2)
                if c_result in (LessonCompareResult.DIFFERENT, LessonCompareResult.EQUALS):
                    found_equal = True
                    break
            if not found_equal and not found_different:
                output.append(LessonDelta(None, l2))  # Lesson was added

        return LessonPlanComparison(lesson_deltas=output)
