from scheduler.core.adjust import apply_and_prune
from scheduler.core.config import SchedulerConfig
from scheduler.core.models import Dataset, GradeCalendar, Teacher, TeachingTask
from scheduler.core.solver import Placement

CAL = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                    periods_per_day=9, midday_break_after=5)


def _dataset():
    """两个班、五个任务：1 班的语文/数学/历史，2 班的语文（跟 1 班语文同一位
    老师，制造教师冲突用）、英语。位置任意——测试里直接摆 Placement，不走
    求解器。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='张老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=1, course='数学', teacher='李老师', periods=1),
        TeachingTask(id=2, grade='初三', class_id=2, course='语文', teacher='张老师', periods=1),
        TeachingTask(id=3, grade='初三', class_id=2, course='英语', teacher='王老师', periods=1),
        TeachingTask(id=4, grade='初三', class_id=1, course='历史', teacher='赵老师', periods=1),
    ]
    teachers = {name: Teacher(name=name) for name in ('张老师', '李老师', '王老师', '赵老师')}
    return Dataset(grade='初三', classes=[1, 2], teachers=teachers, tasks=tasks, calendar=CAL)


def _cfg():
    return SchedulerConfig(courses={}, plans={}, venues={}, reserved_slots={})


def _placements():
    return [
        Placement(task_id=0, class_id=1, course='语文', teacher='张老师', slot=0, parity=None),
        Placement(task_id=1, class_id=1, course='数学', teacher='李老师', slot=1, parity=None),
        Placement(task_id=2, class_id=2, course='语文', teacher='张老师', slot=10, parity=None),
        Placement(task_id=3, class_id=2, course='英语', teacher='王老师', slot=11, parity=None),
        Placement(task_id=4, class_id=1, course='历史', teacher='赵老师', slot=30, parity=None),
    ]


def test_empty_moves_returns_placements_unchanged():
    result = apply_and_prune(_placements(), {}, _dataset(), _cfg(), [])
    assert result.applied == []
    assert result.reverted == []
    assert result.placements == _placements()


def test_clean_move_is_applied_without_revert():
    placements = _placements()
    # 1 班数学（task 1）从 slot 1 挪到一个完全空着的格子（slot 20）——
    # 不撞任何人，应该直接生效。
    result = apply_and_prune(placements, {1: 20}, _dataset(), _cfg(), [])
    assert result.applied == [1]
    assert result.reverted == []
    moved = next(p for p in result.placements if p.task_id == 1)
    assert moved.slot == 20


def test_single_conflicting_move_is_fully_reverted():
    placements = _placements()
    # task 0（张老师，1 班语文）挪到 slot 10——张老师已经在 slot 10 教 2 班
    # 语文（task 2），制造教师分身。
    result = apply_and_prune(placements, {0: 10}, _dataset(), _cfg(), [])
    assert result.applied == []
    assert len(result.reverted) == 1
    assert result.reverted[0].task_id == 0
    assert result.placements == placements  # 完全退回原状


def test_multi_move_only_reverts_the_culprit():
    placements = _placements()
    moves = {
        0: 10,   # 冲突：张老师分身（同上）
        1: 20,   # 干净：挪到空格子
    }
    result = apply_and_prune(placements, moves, _dataset(), _cfg(), [])
    assert result.applied == [1]
    assert [r.task_id for r in result.reverted] == [0]

    by_id = {p.task_id: p for p in result.placements}
    assert by_id[0].slot == 0    # 肇事的那个被退回原位
    assert by_id[1].slot == 20   # 没问题的那个照常生效


def test_entangled_moves_degrade_to_full_revert():
    placements = _placements()
    # task 0 和 task 4 都挪到 slot 1——那是 task 1（没在这批改动里、固定
    # 不动）已经占着的格子。三个人挤一个格子：单独退 task 0 或单独退
    # task 4，格子里依然剩 task 1 + 另一个，违规数原地不动（还是 1 处），
    # 贪心找不到"退一个能改善"的选择，只能整体回退两个。
    moves = {0: 1, 4: 1}
    result = apply_and_prune(placements, moves, _dataset(), _cfg(), [])
    assert result.applied == []
    assert {r.task_id for r in result.reverted} == {0, 4}
    assert all(r.reason == '与其他改动互相牵连，已整体撤销' for r in result.reverted)
    assert result.placements == placements
