"""M7 合排：把多个年级的 CP-SAT 子问题放进同一个模型联合求解。

跟 test_cross_grade.py 一样，构造两个作息形状不同的日历，确保跨年级的
教师/场地约束是按真实钟点换算的，不是巧合对齐"第几节"。
"""
from ortools.sat.python import cp_model

from scheduler.core.config import SchedulerConfig
from scheduler.core.merge_solver import _renumber_tasks, compile_merged_model, solve_merged
from scheduler.core.models import Course, Dataset, GradeCalendar, Teacher, TeachingTask, Venue

# 初三：9 节/天。七年级：8 节/天，第一节起步更早——跟 test_cross_grade.py
# 用的是同一套日历，第1节真实重叠（08:00-08:15），其余节次基本错开。
CAL_9 = GradeCalendar(
    days=['周一', '周二', '周三', '周四', '周五'], periods_per_day=9, midday_break_after=5,
    clock_times=[('08:00', '08:45'), ('08:55', '09:40'), ('09:50', '10:35'), ('10:45', '11:30'),
                ('11:40', '12:25'), ('14:00', '14:45'), ('14:55', '15:40'), ('15:50', '16:35'),
                ('16:45', '17:30')],
)
CAL_8 = GradeCalendar(
    days=['周一', '周二', '周三', '周四', '周五'], periods_per_day=8, midday_break_after=4,
    clock_times=[('07:30', '08:15'), ('08:25', '09:10'), ('09:20', '10:05'), ('10:15', '11:00'),
                ('11:10', '11:55'), ('14:00', '14:45'), ('14:55', '15:40'), ('15:50', '16:35')],
)


def _cfg(venues=None):
    return SchedulerConfig(courses={
        '初三': {'语文': Course(name='语文', family='语文'),
                '体育': Course(name='体育', family='体育', venue='操场')},
        '七年级': {'语文': Course(name='语文', family='语文'),
                  '体育': Course(name='体育', family='体育', venue='操场')},
    }, plans={}, venues=venues or {}, reserved_slots={})


def _dataset(grade, calendar, teacher='语文', course='语文', class_id=1, periods=1):
    task = TeachingTask(id=0, grade=grade, class_id=class_id, course=course, teacher=teacher, periods=periods)
    return Dataset(grade=grade, classes=[class_id], teachers={teacher: Teacher(name=teacher)},
                   tasks=[task], calendar=calendar)


def test_renumber_tasks_produces_globally_unique_ids():
    a = _dataset('初三', CAL_9, teacher='张老师')
    b = _dataset('七年级', CAL_8, teacher='张老师')
    renumbered, id_map = _renumber_tasks({'初三': a, '七年级': b})
    ids = [t.id for ds in renumbered.values() for t in ds.tasks]
    assert len(ids) == len(set(ids))   # 全局唯一
    assert id_map['初三'][renumbered['初三'].tasks[0].id] == 0
    assert id_map['七年级'][renumbered['七年级'].tasks[0].id] == 0


def test_shared_teacher_across_grades_cannot_double_book_overlapping_real_time():
    """两个年级都只有王老师这一门课，且周课时=该年级全部格数——老师整周
    每一格都在上课，不管求解器怎么排，两个年级里王老师的课必然会有真实
    时间重叠（比如两边都覆盖了周一第1节对应的真实钟点），合排必须 INFEASIBLE。
    """
    cal_9_one_task = _dataset('初三', CAL_9, teacher='王老师', periods=CAL_9.n_slots)
    cal_8_one_task = _dataset('七年级', CAL_8, teacher='王老师', periods=CAL_8.n_slots)
    cfg = _cfg()
    merged = compile_merged_model(
        {'初三': cal_9_one_task, '七年级': cal_8_one_task}, cfg, {'初三': [], '七年级': []})

    solver = cp_model.CpSolver()
    status = solver.Solve(merged.model)
    assert status == cp_model.INFEASIBLE


def test_different_teachers_across_grades_are_unaffected():
    a = _dataset('初三', CAL_9, teacher='张老师')
    b = _dataset('七年级', CAL_8, teacher='李老师')
    cfg = _cfg()
    solutions = solve_merged({'初三': a, '七年级': b}, cfg, {'初三': [], '七年级': []})
    assert solutions['初三'].status in ('OPTIMAL', 'FEASIBLE')
    assert solutions['七年级'].status in ('OPTIMAL', 'FEASIBLE')


def test_solve_merged_remaps_placements_back_to_the_callers_original_task_ids():
    a = _dataset('初三', CAL_9, teacher='张老师')
    b = _dataset('七年级', CAL_8, teacher='李老师')
    cfg = _cfg()
    solutions = solve_merged({'初三': a, '七年级': b}, cfg, {'初三': [], '七年级': []})
    assert solutions['初三'].placements[0].task_id == a.tasks[0].id
    assert solutions['七年级'].placements[0].task_id == b.tasks[0].id


def test_shared_venue_capacity_is_enforced_across_grades():
    """操场共享容量 1，两个年级的体育课周课时=该年级全部格数（教师不同，
    不会被教师约束卡住）——不管怎么排，两个年级用操场的时间必然有真实
    重叠，容量 1 放不下 2 个班同时用，合排必须 INFEASIBLE。"""
    a = _dataset('初三', CAL_9, teacher='体育老师A', course='体育', periods=CAL_9.n_slots)
    b = _dataset('七年级', CAL_8, teacher='体育老师B', course='体育', periods=CAL_8.n_slots)
    cfg = _cfg(venues={'操场': Venue(name='操场', capacity=1)})
    merged = compile_merged_model({'初三': a, '七年级': b}, cfg, {'初三': [], '七年级': []})
    solver = cp_model.CpSolver()
    status = solver.Solve(merged.model)
    assert status == cp_model.INFEASIBLE


def test_venue_with_a_grade_specific_allocation_is_not_shared_across_grades():
    """操场对初三单独分配了 1 个位置——即使容量总数只有 1，这个场地对初三
    不算跨年级共享，七年级用同一个场地不受影响，两边都能正常求解。"""
    a = _dataset('初三', CAL_9, teacher='体育老师A', course='体育')
    b = _dataset('七年级', CAL_8, teacher='体育老师B', course='体育')
    cfg = _cfg(venues={'操场': Venue(name='操场', capacity=1, grade_capacity={'初三': 1})})
    solutions = solve_merged({'初三': a, '七年级': b}, cfg, {'初三': [], '七年级': []})
    assert solutions['初三'].status in ('OPTIMAL', 'FEASIBLE')
    assert solutions['七年级'].status in ('OPTIMAL', 'FEASIBLE')


def test_single_grade_merge_degrades_to_a_plain_single_grade_solve():
    """合排的年级集合只有 1 个时，跨年级约束天然是空操作，行为应该跟直接
    调 compile_model 一样（用来确认合排不会给单年级场景引入任何副作用）。"""
    a = _dataset('初三', CAL_9, teacher='张老师')
    cfg = _cfg()
    solutions = solve_merged({'初三': a}, cfg, {'初三': []})
    assert solutions['初三'].status in ('OPTIMAL', 'FEASIBLE')
    assert len(solutions) == 1


def test_within_grade_constraints_still_apply_inside_a_merged_solve():
    """合排不能绕过原有的单年级内部约束——同一个年级内两位老师抢同一个班
    的同一节课依然不可行（跟不合排时的行为一致）。"""
    calendar = CAL_9
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='张老师', periods=45),
        TeachingTask(id=1, grade='初三', class_id=1, course='语文', teacher='李老师', periods=45),
    ]
    ds = Dataset(grade='初三', classes=[1], teachers={'张老师': Teacher(name='张老师'), '李老师': Teacher(name='李老师')},
                tasks=tasks, calendar=calendar)
    cfg = _cfg()
    solutions = solve_merged({'初三': ds}, cfg, {'初三': []})
    assert solutions['初三'].status == 'INFEASIBLE'
