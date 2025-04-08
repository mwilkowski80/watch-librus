import pytest
from watchlibrus.lessonplan import Lesson, LessonPlan

def test_compare_single_day_no_changes():
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Edu", time="08:00 - 08:45", teacher="A", classroom="33"),
        Lesson(day=0, hour=2, name="WF", time="08:50 - 09:35", teacher="B", classroom="SGIM"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Edu", time="08:00 - 08:45", teacher="A", classroom="33"),
        Lesson(day=0, hour=2, name="WF", time="08:50 - 09:35", teacher="B", classroom="SGIM"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert not compare_result.is_change()

def test_compare_single_day_with_change():
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Edu", time="08:00 - 08:45", teacher="A", classroom="33"),
        Lesson(day=0, hour=2, name="WF", time="08:50 - 09:35", teacher="B", classroom="SGIM"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Edu", time="08:00 - 08:45", teacher="A", classroom="33"),
        Lesson(day=0, hour=2, name="Rel", time="08:50 - 09:35", teacher="C", classroom="5"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert compare_result.is_change()
    assert len(compare_result.lesson_deltas) == 1
    delta = compare_result.lesson_deltas[0]
    assert delta.l1.name == "WF"
    assert delta.l2.name == "Rel"
