import pytest
from watchlibrus.lessonplan import Lesson, LessonPlan

def test_compare_single_day_no_changes():
    """Test that comparing identical schedules reports no changes."""
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert not compare_result.is_change()

def test_compare_single_day_with_change():
    """Test that comparing schedules with changes reports the differences correctly."""
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Chemistry", time="08:50 - 09:35", teacher="Brown", classroom="LAB2"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert compare_result.is_change()
    assert len(compare_result.lesson_deltas) == 1
    delta = compare_result.lesson_deltas[0]
    assert delta.l1.name == "Physics"
    assert delta.l2.name == "Chemistry"
    assert delta.l1.teacher == "Johnson"
    assert delta.l2.teacher == "Brown"
    assert delta.l1.classroom == "LAB1"
    assert delta.l2.classroom == "LAB2"

def test_compare_single_day_with_added_lesson():
    """Test that comparing schedules where a lesson was added reports it correctly."""
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert compare_result.is_change()
    assert len(compare_result.lesson_deltas) == 1
    delta = compare_result.lesson_deltas[0]
    assert delta.l1 is None
    assert delta.l2.name == "Physics"

def test_compare_single_day_with_removed_lesson():
    """Test that comparing schedules where a lesson was removed reports it correctly."""
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
    ])
    compare_result = old_plan.compare(new_plan)
    assert compare_result.is_change()
    assert len(compare_result.lesson_deltas) == 1
    delta = compare_result.lesson_deltas[0]
    assert delta.l1.name == "Physics"
    assert delta.l2 is None

def test_compare_single_day_with_multiple_changes():
    """Test that comparing schedules with multiple changes reports all differences correctly."""
    old_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Smith", classroom="101"),
        Lesson(day=0, hour=2, name="Physics", time="08:50 - 09:35", teacher="Johnson", classroom="LAB1"),
        Lesson(day=0, hour=3, name="English", time="09:40 - 10:25", teacher="Brown", classroom="201"),
    ])
    new_plan = LessonPlan(lessons=[
        Lesson(day=0, hour=1, name="Math", time="08:00 - 08:45", teacher="Jones", classroom="102"),  # Changed teacher and room
        Lesson(day=0, hour=3, name="French", time="09:40 - 10:25", teacher="Martin", classroom="202"),  # Complete change
        Lesson(day=0, hour=4, name="PE", time="10:30 - 11:15", teacher="Wilson", classroom="GYM"),  # Added lesson
    ])
    compare_result = old_plan.compare(new_plan)
    assert compare_result.is_change()
    assert len(compare_result.lesson_deltas) == 4  # 2 modified, 1 removed, 1 added
    
    changes = {(d.l1.name if d.l1 else None, d.l2.name if d.l2 else None) for d in compare_result.lesson_deltas}
    expected_changes = {
        ("Math", "Math"),  # Modified
        ("Physics", None),  # Removed
        ("English", "French"),  # Modified
        (None, "PE"),  # Added
    }
    assert changes == expected_changes
