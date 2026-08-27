"""领域模型。

compiler.py 与 verifier.py 唯一允许共享的东西就是这里的数据结构 ——
不含任何约束语义。
"""
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


def _default_grade_calendar() -> 'GradeCalendar':
    """匹配 calendar.py 现有全局常量的默认日历——5 天、9 节、午休 5/6 节间。

    这是本次年级参数化改动的关键兼容手段：所有没有显式传 calendar= 的
    现有 Dataset(...) 构造调用（尤其是测试里的 make_dataset/ds 辅助函数）
    自动获得和改动前完全一致的行为，不需要批量修改测试。
    """
    return GradeCalendar(
        days=['周一', '周二', '周三', '周四', '周五'],
        periods_per_day=9,
        midday_break_after=5,
    )


class GradeCalendar(BaseModel):
    """一个年级的时间格形状：天数、每天节数、午休边界。

    slot_index/slot_of 的换算公式依赖 periods_per_day，一旦按年级不同就
    不能再是全局函数——这是把 calendar.py 的自由函数改成本类方法的原因。
    """
    days: List[str]
    periods_per_day: int
    midday_break_after: int
    clock_times: Optional[List[Tuple[str, str]]] = None
    reserved_slots: List[dict] = Field(default_factory=list)

    @property
    def n_slots(self) -> int:
        return len(self.days) * self.periods_per_day

    @property
    def morning(self) -> range:
        return range(1, self.midday_break_after + 1)

    @property
    def afternoon(self) -> range:
        return range(self.midday_break_after + 1, self.periods_per_day + 1)

    def day_index(self, name: str) -> int:
        try:
            return self.days.index(name)
        except ValueError:
            raise ValueError('未知星期：%r，仅支持 %s' % (name, self.days))

    def slot_index(self, day: int, period: int) -> int:
        if not 0 <= day < len(self.days):
            raise ValueError('星期序号越界：%s' % day)
        if not 1 <= period <= self.periods_per_day:
            raise ValueError('节次越界：%s' % period)
        return day * self.periods_per_day + (period - 1)

    def slot_of(self, index: int) -> Tuple[int, int]:
        if not 0 <= index < self.n_slots:
            raise ValueError('时间格索引越界：%s' % index)
        return index // self.periods_per_day, index % self.periods_per_day + 1

    def section_period(self, section: Optional[str], n: int) -> int:
        if section == '上午':
            if n not in self.morning:
                raise ValueError('上午只有 1-%d 节，收到第 %s 节' % (self.midday_break_after, n))
            return n
        if section == '下午':
            afternoon_len = self.periods_per_day - self.midday_break_after
            if not 1 <= n <= afternoon_len:
                raise ValueError('下午只有 1-%d 节，收到第 %s 节' % (afternoon_len, n))
            return self.midday_break_after + n
        if section is None:
            if not 1 <= n <= self.periods_per_day:
                raise ValueError('节次越界：%s' % n)
            return n
        raise ValueError('未知时段：%r' % section)

    def adjacent_pairs(self) -> List[Tuple[int, int]]:
        """一天之内可构成连堂的节次对，排除午休边界。

        【铁律4】仅供 compiler.py 使用。verifier.py 必须独立从 midday_break_after
        推导相邻性，不得调用本方法——见 CLAUDE.md「铁律 4 的能力边界」一节的历史教训。
        """
        return [(p, p + 1) for p in range(1, self.periods_per_day)
                if p != self.midday_break_after]


class GradeInfo(BaseModel):
    """年级管理页声明的年级——名字任意、数量不限。

    这里只记"有哪些年级、每个年级几个班"，供 UI 在导入任何 Excel 之前
    先把年级/班级骨架搭起来；求解链路仍然读 Dataset.classes（从实际导入
    的任课表算出来），两者不是同一件事——这里是声明与校验用的骨架。
    """
    name: str
    classes: int


class Course(BaseModel):
    name: str
    family: str
    venue: Optional[str] = None
    alternate: Optional[str] = None  # '单周' | '双周' | None
    external: bool = False          # 教务已固定安排，不生成任务、不进求解器


class Venue(BaseModel):
    name: str
    capacity: Optional[int] = None   # None = 不限制


class Teacher(BaseModel):
    name: str
    duties: List[str] = Field(default_factory=list)
    # 教师级禁排，[day, period] 对。必须是该教师全部行的并集，见导入器。
    forbidden: List[List[int]] = Field(default_factory=list)

    def forbidden_slots(self):
        return {(d, p) for d, p in self.forbidden}


class TeachingTask(BaseModel):
    """一个「班级 × 课程」的教学任务，是求解的最小单位。"""
    id: int
    grade: str
    class_id: int
    course: str
    teacher: str
    periods: int                     # 本任务每周占几格（0.5 课时已转成 1）
    parity: Optional[str] = None     # None=每周 | '单周' | '双周'

    @property
    def consumes_slot(self) -> bool:
        """双周任务与其单周伙伴共用同一格，不额外占班级课表的格。"""
        return self.parity != '双周'


class Dataset(BaseModel):
    """一次求解的全部输入。"""
    grade: str
    classes: List[int]
    teachers: Dict[str, Teacher]
    tasks: List[TeachingTask]
    calendar: GradeCalendar = Field(default_factory=_default_grade_calendar)
