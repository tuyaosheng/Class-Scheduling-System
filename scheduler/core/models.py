"""领域模型。

compiler.py 与 verifier.py 唯一允许共享的东西就是这里的数据结构 ——
不含任何约束语义。
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Course(BaseModel):
    name: str
    family: str
    venue: Optional[str] = None
    multi_class: bool = False       # 一位教师可同时面向多个班（体比/体选）
    alternate: Optional[str] = None  # '单周' | '双周' | None


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
