"""YAML 配置加载与一致性校验。"""
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel

from .models import Course, GradeCalendar, GradeInfo, Venue


class ConfigError(ValueError):
    """配置不自洽。"""


class SchedulerConfig(BaseModel):
    courses: Dict[str, Course]
    plans: Dict[str, Dict[str, int]]
    venues: Dict[str, Venue]
    reserved_slots: Dict[str, List[List[int]]] = {}   # 年级 -> 教务固定占位的 [day, period] 列表
    calendars: Dict[str, GradeCalendar] = {}
    grades: List[GradeInfo] = []   # 年级管理页声明的年级骨架，见 GradeInfo 文档

    def calendar_of(self, grade: str) -> GradeCalendar:
        try:
            return self.calendars[grade]
        except KeyError:
            raise ConfigError('年级 %r 没有对应的日历配置（calendars.yaml）' % grade)

    def reserved_slot_indices(self, grade: str) -> set:
        slots = self.reserved_slots.get(grade, [])
        if not slots:
            return set()
        calendar = self.calendar_of(grade)
        return {calendar.slot_index(d, p) for d, p in slots}

    def family_of(self, course_name: str) -> str:
        try:
            return self.courses[course_name].family
        except KeyError:
            raise ConfigError('课程目录中没有 %r' % course_name)

    def courses_in_family(self, family: str) -> List[str]:
        return [c.name for c in self.courses.values() if c.family == family]

    def resolve_plan_key(self, key: str) -> List[str]:
        """把课程计划的键展开为课程名列表。

        单双周家族（心美）在计划里记 1 节，实际对应美术+心理两门课。
        """
        if key in self.courses:
            return [key]
        members = [c for c in self.courses.values() if c.family == key and c.alternate]
        if members:
            order = {'单周': 0, '双周': 1}
            return [c.name for c in sorted(members, key=lambda c: order[c.alternate])]
        raise ConfigError('课程计划里的 %r 既不是课程名，也不是单双周学科系' % key)

    def validate_plan(self, grade: str) -> None:
        plan = self.plans.get(grade) or {}
        for key in plan:
            self.resolve_plan_key(key)          # 未知项在这里抛错
        total = sum(plan.values())
        if total == 0:
            return                              # 空计划（如初一/初二待补）不需要该年级的日历配置
        n_slots = self.calendar_of(grade).n_slots
        available = n_slots - len(self.reserved_slots.get(grade, ()))
        if total > available:
            raise ConfigError(
                '%s 每班周课时 %d 超出可用 %d 格（每周 %d 格，教务固定占位 %d 格）'
                % (grade, total, available, n_slots, n_slots - available))


def _read(path: Path, key: str):
    if not path.exists():
        raise ConfigError('缺少配置文件：%s' % path)
    with path.open(encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    if key not in data:
        raise ConfigError('%s 缺少顶层键 %r' % (path.name, key))
    return data[key]


def load_config(config_dir) -> SchedulerConfig:
    config_dir = Path(config_dir)
    courses = {c['name']: Course(**c) for c in _read(config_dir / 'courses.yaml', 'courses')}
    venues = {v['name']: Venue(**v) for v in _read(config_dir / 'venues.yaml', 'venues')}
    plans = _read(config_dir / 'plans.yaml', 'plans') or {}
    plans_path = config_dir / 'plans.yaml'
    reserved_slots = {}
    if plans_path.exists():
        raw = yaml.safe_load(plans_path.read_text(encoding='utf-8')) or {}
        reserved_slots = raw.get('reserved_slots') or {}

    calendars_path = config_dir / 'calendars.yaml'
    calendars = {}
    if calendars_path.exists():
        raw_calendars = yaml.safe_load(calendars_path.read_text(encoding='utf-8')) or {}
        calendars = {g: GradeCalendar(**c) for g, c in (raw_calendars.get('grade_calendars') or {}).items()}

    for course in courses.values():
        if course.venue and course.venue not in venues:
            raise ConfigError('课程 %s 引用了未声明的场地 %r' % (course.name, course.venue))

    grades_path = config_dir / 'grades.yaml'
    grades: List[GradeInfo] = []
    if grades_path.exists():
        raw_grades = yaml.safe_load(grades_path.read_text(encoding='utf-8')) or {}
        grades = [GradeInfo(**g) for g in (raw_grades.get('grades') or [])]

    cfg = SchedulerConfig(courses=courses, plans={g: (p or {}) for g, p in plans.items()},
                          venues=venues, reserved_slots=reserved_slots, calendars=calendars,
                          grades=grades)
    for grade in cfg.plans:
        cfg.validate_plan(grade)
    return cfg
