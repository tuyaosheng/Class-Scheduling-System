"""跨年级教师冲突：求解阶段就避开，按真实钟点区间换算，不能比较"第几节"。

构造两个作息形状不同的日历（节数不同、钟点表不同）来确保换算逻辑真的是
按钟点算的，不是巧合对齐。对应 CLAUDE.md「多年级操作流程重构」子项目9
（设计变更：原来的"导出前事后校验"改成"求解阶段就避开"）。
"""
from scheduler.core.cross_grade import compute_cross_grade_lock_rules
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
                ('11:10', '11:55'), ('14:00', '14:45'), ('14:55', '15:40'),
                ('17:40', '18:20')],   # 最后一节故意排在初三放学（17:30）之后，用来测"不重叠"
)


def _dataset(grade, calendar, teacher='王老师'):
    task = TeachingTask(id=0, grade=grade, class_id=1, course='语文', teacher=teacher, periods=1)
    return Dataset(grade=grade, classes=[1], teachers={teacher: Teacher(name=teacher)},
                   tasks=[task], calendar=calendar)


def _solution(class_id, course, slot, teacher='王老师'):
    return Solution(status='OPTIMAL', wall_time=0.0,
                    placements=[Placement(task_id=0, class_id=class_id, course=course,
                                          teacher=teacher, slot=slot, parity=None)])


def test_no_lock_rule_when_clock_times_do_not_overlap():
    # 七年级周二第8节 17:40-18:20；初三当天最晚的一节（第9节）17:30 就放学了
    # ——两者不重叠，不该生成任何禁排规则。
    other = {'七年级': (_dataset('七年级', CAL_8), _solution(2, '语文', slot=15))}
    rules = compute_cross_grade_lock_rules('初三', CAL_9, other)
    assert rules == []


def test_locks_the_overlapping_slot_at_different_period_numbers_on_different_calendars():
    """核心场景：七年级第1节是 07:30-08:15，初三第1节是 08:00-08:45——两者
    在 08:00-08:15 真实重叠，即使"第几节"的编号完全不能直接比较。给初三
    求解时应该把初三自己坐标系下第1节（唯一跟这段时间重叠的格子）禁排。"""
    other = {'七年级': (_dataset('七年级', CAL_8, teacher='王老师'), _solution(2, '语文', slot=0, teacher='王老师'))}
    rules = compute_cross_grade_lock_rules('初三', CAL_9, other)
    assert len(rules) == 1
    rule = rules[0]
    assert rule['type'] == 'forbid_slots'
    assert rule['scope'] == {'grade': '初三', 'teacher': '王老师'}
    assert rule['params']['slots'] == [[0, 1]]   # 周一第1节


def test_ignores_the_same_grade_entry_if_present():
    other = {
        '初三': (_dataset('初三', CAL_9), _solution(5, '语文', slot=0)),
        '七年级': (_dataset('七年级', CAL_8), _solution(2, '语文', slot=0)),
    }
    rules = compute_cross_grade_lock_rules('初三', CAL_9, other)
    # 只应该看到跟七年级老师换算出来的锁定，不该把自己年级的排课也当成"外部"。
    assert all(r['scope']['grade'] == '初三' for r in rules)


def test_different_teachers_never_produce_a_lock():
    other = {'七年级': (_dataset('七年级', CAL_8, teacher='李老师'), _solution(2, '语文', slot=0, teacher='李老师'))}
    rules = compute_cross_grade_lock_rules('初三', CAL_9, other)
    # 七年级老师是李老师，初三数据集里没有这个人——规则仍会生成（scope 是
    # teacher=李老师），但对初三求解无影响，因为初三没有李老师的任务。
    assert rules[0]['scope']['teacher'] == '李老师'


def test_own_grade_without_clock_times_returns_no_rules():
    no_clock_cal = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                                 periods_per_day=9, midday_break_after=5)
    other = {'七年级': (_dataset('七年级', CAL_8), _solution(2, '语文', slot=0))}
    rules = compute_cross_grade_lock_rules('初三', no_clock_cal, other)
    assert rules == []


def test_other_grade_without_clock_times_is_skipped_not_silently_assumed():
    no_clock_cal = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                                 periods_per_day=9, midday_break_after=5)
    other = {'八年级': (_dataset('八年级', no_clock_cal), _solution(2, '语文', slot=0))}
    rules = compute_cross_grade_lock_rules('初三', CAL_9, other)
    assert rules == []
