"""跨年级统一校验：按真实钟点区间比对教师跨年级冲突，不能比较"第几节"。

对应 CLAUDE.md「多年级操作流程重构」子项目7。构造两个作息形状不同的年级
（节数不同、钟点表不同）来确保比较逻辑真的是按钟点算的，不是碰巧对齐。
"""
from scheduler.core.cross_grade import find_cross_grade_conflicts
from scheduler.core.models import Dataset, GradeCalendar, Teacher, TeachingTask
from scheduler.core.solver import Placement, Solution

# 初三：9 节/天，午休在第5节后。第1节 08:00-08:45，第2节 08:55-09:40。
CAL_9 = GradeCalendar(
    days=['周一', '周二', '周三', '周四', '周五'], periods_per_day=9, midday_break_after=5,
    clock_times=[('08:00', '08:45'), ('08:55', '09:40'), ('09:50', '10:35'), ('10:45', '11:30'),
                ('11:40', '12:25'), ('14:00', '14:45'), ('14:55', '15:40'), ('15:50', '16:35'),
                ('16:45', '17:30')],
)

# 七年级：8 节/天，第一节起步更早（07:30），跟初三的钟点表完全错位——
# 用来验证"同一节次编号"在两个年级根本不是同一个真实时间。
CAL_8 = GradeCalendar(
    days=['周一', '周二', '周三', '周四', '周五'], periods_per_day=8, midday_break_after=4,
    clock_times=[('07:30', '08:15'), ('08:25', '09:10'), ('09:20', '10:05'), ('10:15', '11:00'),
                ('11:10', '11:55'), ('14:00', '14:45'), ('14:55', '15:40'), ('15:50', '16:35')],
)


def _dataset(grade, calendar, teacher='王老师'):
    task = TeachingTask(id=0, grade=grade, class_id=1, course='语文', teacher=teacher, periods=1)
    return Dataset(grade=grade, classes=[1], teachers={teacher: Teacher(name=teacher)},
                   tasks=[task], calendar=calendar)


def _solution(class_id, course, slot, teacher='王老师'):
    return Solution(status='OPTIMAL', wall_time=0.0,
                    placements=[Placement(task_id=0, class_id=class_id, course=course,
                                          teacher=teacher, slot=slot, parity=None)])


def test_no_conflict_when_clock_times_do_not_overlap():
    # 初三周一第1节 08:00-08:45；七年级周一第6节 14:00-14:45——完全不重叠。
    entries = {
        '初三': (_dataset('初三', CAL_9), _solution(1, '语文', slot=0)),
        '七年级': (_dataset('七年级', CAL_8), _solution(2, '语文', slot=5)),
    }
    conflicts, skipped = find_cross_grade_conflicts(entries)
    assert conflicts == []
    assert skipped == []


def test_detects_overlap_at_different_period_numbers_on_different_calendars():
    """核心场景：初三第1节（08:00-08:45）和七年级第1节（07:30-08:15）虽然
    都叫"第1节"，但真实钟点有重叠（08:00-08:15）——必须按钟点判，不能
    因为"都是第1节"就当作理所当然冲突，也不能因为"节次编号相同就是同一
    时间"这种简化假设而误判或漏判。"""
    entries = {
        '初三': (_dataset('初三', CAL_9), _solution(1, '语文', slot=0)),
        '七年级': (_dataset('七年级', CAL_8), _solution(2, '语文', slot=0)),
    }
    conflicts, skipped = find_cross_grade_conflicts(entries)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.teacher == '王老师'
    assert c.day == '周一'
    assert {c.grade_a, c.grade_b} == {'初三', '七年级'}


def test_same_grade_conflicts_are_not_reported_here():
    """同年级内部的教师分身已经由各自的 verify() 保证不存在——这一层不重复报。"""
    task_a = TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='王老师', periods=1)
    task_b = TeachingTask(id=1, grade='初三', class_id=2, course='数学', teacher='王老师', periods=1)
    dataset = Dataset(grade='初三', classes=[1, 2], teachers={'王老师': Teacher(name='王老师')},
                      tasks=[task_a, task_b], calendar=CAL_9)
    solution = Solution(status='OPTIMAL', wall_time=0.0, placements=[
        Placement(task_id=0, class_id=1, course='语文', teacher='王老师', slot=0, parity=None),
        Placement(task_id=1, class_id=2, course='数学', teacher='王老师', slot=0, parity=None),
    ])
    conflicts, skipped = find_cross_grade_conflicts({'初三': (dataset, solution)})
    assert conflicts == []
    assert skipped == []


def test_different_teachers_never_conflict():
    entries = {
        '初三': (_dataset('初三', CAL_9, teacher='张老师'), _solution(1, '语文', slot=0, teacher='张老师')),
        '七年级': (_dataset('七年级', CAL_8, teacher='李老师'), _solution(2, '语文', slot=0, teacher='李老师')),
    }
    conflicts, skipped = find_cross_grade_conflicts(entries)
    assert conflicts == []


def test_grade_without_clock_times_is_skipped_not_silently_ignored():
    no_clock_cal = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                                 periods_per_day=9, midday_break_after=5)
    entries = {
        '初三': (_dataset('初三', CAL_9), _solution(1, '语文', slot=0)),
        '八年级': (_dataset('八年级', no_clock_cal), _solution(2, '语文', slot=0)),
    }
    conflicts, skipped = find_cross_grade_conflicts(entries)
    assert conflicts == []   # 八年级没法参与比较
    assert skipped == ['八年级']
