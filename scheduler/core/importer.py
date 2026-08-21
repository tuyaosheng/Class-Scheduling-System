"""Excel 任课表导入。

关键口径（见计划文档「三处口径」）：
  1. 「不能排课节次」按教师取并集 —— 空白行不代表该课可排在会议时段。
  2. 「固定节次」是窗口不是钉死。
  3. 「周课时 0.5」转成 1 节 + 周次奇偶标记。
"""
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import openpyxl
import yaml
from pydantic import BaseModel

from .models import Dataset, Teacher, TeachingTask
from .ruletext import parse_fixed_slots, parse_remark, parse_requirement, parse_time_expr

COLUMNS = {
    '姓名': 0, '任教年级': 1, '学科': 2, '任教班': 3, '周课时': 4,
    '职务': 5, '固定节次': 6, '不能排课节次': 7, '排课要求': 8, '备注': 9,
}
FIRST_DATA_ROW = 3

# 规则片段的 scope 维度：daily_* 按学科系统计，连堂/间隔按具体课程
_FAMILY_SCOPED = {'daily_min', 'daily_max', 'weekday_exact'}
_COURSE_SCOPED = {'consecutive', 'spacing'}


class ImportResult(BaseModel):
    dataset: Dataset
    rules: List[dict]
    warnings: List[str]


def _cell(row, name):
    value = row[COLUMNS[name]]
    return '' if value is None else str(value).strip()


def _class_ids(text):
    return [int(x) for x in text.split(',') if x.strip()]


def import_excel(path, cfg, grade='初三') -> ImportResult:
    wb = openpyxl.load_workbook(path, data_only=True)
    rows = [r for r in wb[wb.sheetnames[0]].iter_rows(min_row=FIRST_DATA_ROW, values_only=True)
            if r and r[COLUMNS['姓名']]]

    # ---- 第一遍：教师级信息聚合 ----
    forbidden = defaultdict(set)
    duties = defaultdict(set)
    for row in rows:
        name = _cell(row, '姓名')
        forbidden[name] |= parse_time_expr(_cell(row, '不能排课节次'))
        for duty in _cell(row, '职务').split(','):
            if duty.strip():
                duties[name].add(duty.strip())

    teachers = {
        name: Teacher(name=name,
                      duties=sorted(duties[name]),
                      forbidden=sorted([d, p] for d, p in forbidden[name]))
        for name in forbidden
    }

    # ---- 第二遍：教学任务 ----
    tasks: List[TeachingTask] = []
    classes = set()
    for row in rows:
        name, course = _cell(row, '姓名'), _cell(row, '学科')
        if course not in cfg.courses:
            raise ValueError('Excel 中的学科 %r 不在课程目录里' % course)
        hours = float(_cell(row, '周课时'))
        parity = None
        if hours == 0.5:
            parity = cfg.courses[course].alternate
            if not parity:
                raise ValueError('%s 周课时 0.5 但课程目录未声明 alternate' % course)
            periods = 1
        else:
            if hours != int(hours):
                raise ValueError('%s %s 周课时 %s 既不是整数也不是 0.5' % (name, course, hours))
            periods = int(hours)
        for class_id in _class_ids(_cell(row, '任教班')):
            classes.add(class_id)
            tasks.append(TeachingTask(id=len(tasks), grade=grade, class_id=class_id,
                                      course=course, teacher=name,
                                      periods=periods, parity=parity))

    dataset = Dataset(grade=grade, classes=sorted(classes),
                      teachers=teachers, tasks=tasks)
    rules = _build_rules(rows, cfg, grade)
    warnings = _check_class_loads(dataset, cfg, grade)
    return ImportResult(dataset=dataset, rules=rules, warnings=warnings)


def _build_rules(rows, cfg, grade) -> List[dict]:
    rules: List[dict] = []

    # 教师禁排：按教师取并集
    forbidden = defaultdict(set)
    for row in rows:
        forbidden[_cell(row, '姓名')] |= parse_time_expr(_cell(row, '不能排课节次'))
    for name in sorted(forbidden):
        if not forbidden[name]:
            continue
        rules.append({
            'type': 'forbid_slots',
            'scope': {'grade': grade, 'teacher': name},
            'params': {'slots': sorted([d, p] for d, p in forbidden[name])},
            'mode': 'hard',
        })

    # 固定节次：按课程去重
    pins = defaultdict(set)
    for row in rows:
        slots = parse_fixed_slots(_cell(row, '固定节次'))
        if slots:
            pins[_cell(row, '学科')] |= slots
    for course in sorted(pins):
        rules.append({
            'type': 'pin_window',
            'scope': {'grade': grade, 'course': course},
            'params': {'slots': sorted([d, p] for d, p in pins[course])},
            'mode': 'hard',
        })

    # 排课要求与备注：按 (类型, 作用域键, 参数) 去重
    seen = set()
    for row in rows:
        course = _cell(row, '学科')
        fragments = (parse_requirement(_cell(row, '排课要求'))
                     + parse_remark(_cell(row, '备注')))
        for frag in fragments:
            rtype, params = frag['type'], frag['params']
            if rtype in _FAMILY_SCOPED:
                scope = {'grade': grade, 'family': cfg.family_of(course)}
            elif rtype in _COURSE_SCOPED:
                scope = {'grade': grade, 'course': course}
            else:                       # alternate_weeks 等年级级规则
                scope = {'grade': grade}
                params = {k: v for k, v in params.items() if k != 'self_parity'}
            key = (rtype, tuple(sorted(scope.items())),
                   yaml.safe_dump(params, sort_keys=True, allow_unicode=True))
            if key in seen:
                continue
            seen.add(key)
            rules.append({'type': rtype, 'scope': scope, 'params': params,
                          'mode': 'hard' if rtype != 'spacing' else 'soft'})

    for rule in rules:
        if rule['mode'] == 'soft':
            rule.setdefault('enabled', True)
            rule.setdefault('weight', 5)
    return rules


def _check_class_loads(dataset, cfg, grade) -> List[str]:
    plan_total = sum((cfg.plans.get(grade) or {}).values())
    used = defaultdict(int)
    for task in dataset.tasks:
        if task.consumes_slot:
            used[task.class_id] += task.periods
    warnings = []
    for class_id in sorted(used):
        if plan_total and used[class_id] != plan_total:
            warnings.append('%d班占 %d 格，课程计划为 %d 格'
                            % (class_id, used[class_id], plan_total))
    return warnings


def write_teaching_yaml(result: ImportResult, path) -> None:
    data = {
        'grade': result.dataset.grade,
        'classes': result.dataset.classes,
        'teachers': [t.model_dump() for t in result.dataset.teachers.values()],
        'tasks': [t.model_dump() for t in result.dataset.tasks],
    }
    Path(path).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')


def write_rules_yaml(result: ImportResult, path) -> None:
    Path(path).write_text(
        yaml.safe_dump({'rules': result.rules}, allow_unicode=True, sort_keys=False),
        encoding='utf-8')
