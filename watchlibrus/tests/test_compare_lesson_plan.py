import importlib.resources
import json
from typing import Tuple, List

import pytest

from watchlibrus.tests.resources import lesson_plan_comparisons
from watchlibrus.lessonplan import LessonPlan, LessonPlanComparison


def load_lesson_plan_compare_test_cases() -> List[Tuple[LessonPlan, LessonPlan, LessonPlanComparison]]:
    _dir = importlib.resources.files(lesson_plan_comparisons)
    output = []
    for fp in sorted(_dir.iterdir(), key=lambda x: x.name):
        if fp.name.endswith('.json'):
            with fp.open() as f:
                obj = json.load(f)
            lp1 = LessonPlan.from_dict_list(obj['lesson-plan-1'])
            lp2 = LessonPlan.from_dict_list(obj['lesson-plan-2'])
            lpc = LessonPlanComparison.from_dict_list(obj['lesson-plan-comparison'])
            output.append((lp1, lp2, lpc))
    return output


@pytest.mark.parametrize('lp1,lp2,expected', load_lesson_plan_compare_test_cases())
def test_compare_lesson_plans(lp1: LessonPlan, lp2: LessonPlan, expected: LessonPlanComparison):
    actual = lp1.compare(lp2)
    assert actual == expected
