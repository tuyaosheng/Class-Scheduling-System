"""Excel 任课表导入。

关键口径（见计划文档「三处口径」）：
  1. 「不能排课节次」按教师取并集 —— 空白行不代表该课可排在会议时段。
  2. 「固定节次」是窗口不是钉死。
  3. 「周课时 0.5」转成 1 节 + 周次奇偶标记。
"""
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

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
        if cfg.courses[course].external:
            for class_id in _class_ids(_cell(row, '任教班')):
                classes.add(class_id)
            continue
        hours = float(_cell(row, '周课时'))
        base_parity = None
        if hours == 0.5:
            base_parity = cfg.courses[course].alternate
            if not base_parity:
                raise ValueError('%s 周课时 0.5 但课程目录未声明 alternate' % course)
            periods = 1
        else:
            if hours != int(hours):
                raise ValueError('%s %s 周课时 %s 既不是整数也不是 0.5' % (name, course, hours))
            periods = int(hours)
        for class_id in _class_ids(_cell(row, '任教班')):
            classes.add(class_id)
            parity = base_parity
            if base_parity and class_id % 2 == 0:
                # 按班号奇偶各半翻转单双周，否则该老师整学期只在单周（或双周）
                # 有课，负荷忽高忽低；翻转后每周教的班数固定，见坑 3。
                parity = '双周' if base_parity == '单周' else '单周'
            tasks.append(TeachingTask(id=len(tasks), grade=grade, class_id=class_id,
                                      course=course, teacher=name,
                                      periods=periods, parity=parity))

    dataset = Dataset(grade=grade, classes=sorted(classes),
                      teachers=teachers, tasks=tasks)
    rules = _build_rules(rows, cfg, grade, forbidden)
    warnings = _check_class_loads(dataset, cfg, grade)
    return ImportResult(dataset=dataset, rules=rules, warnings=warnings)


def _build_rules(rows, cfg, grade, forbidden) -> List[dict]:
    """forbidden 由调用方（import_excel 的第一遍）算好传入 ——

    教师禁排并集只应算一次；这里不再重新遍历 rows 推导它，
    避免与 Teacher.forbidden 各自独立计算导致悄悄分叉（见 review Important）。
    """
    rules: List[dict] = []

    # 教师禁排：来自 import_excel 已聚合好的并集
    for name in sorted(forbidden):
        if not forbidden[name]:
            continue
        rules.append({
            'type': 'forbid_slots',
            'scope': {'grade': grade, 'teacher': name},
            'params': {'slots': sorted([d, p] for d, p in forbidden[name])},
            'mode': 'hard',
        })

    # 固定节次：按课程去重。教务已固定安排的课程（external）不生成任务，
    # 也就不需要 pin_window——它们的窗口改由 reserved_slots 统一挖空处理。
    pins = defaultdict(set)
    for row in rows:
        course = _cell(row, '学科')
        if cfg.courses[course].external:
            continue
        slots = parse_fixed_slots(_cell(row, '固定节次'))
        if slots:
            pins[course] |= slots
    for course in sorted(pins):
        rules.append({
            'type': 'pin_window',
            'scope': {'grade': grade, 'course': course},
            'params': {'slots': sorted([d, p] for d, p in pins[course])},
            'mode': 'hard',
        })

    # 教务固定占位的时段：整体从求解器可用格位里挖空，禁止任何常规任务占用
    reserved = cfg.reserved_slots.get(grade) or []
    if reserved:
        rules.append({
            'type': 'forbid_slots',
            'scope': {'grade': grade},
            'params': {'slots': sorted([d, p] for d, p in reserved)},
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


TEACHING_TABLE_HEADER_ROW = 2
TEACHING_TABLE_FIRST_DATA_ROW = 3


def parse_teaching_table(path, cfg) -> Dict[Tuple[int, str], str]:
    """解析『班别 × 学科』矩阵版式的任课表，返回 (班级,课程) -> 教师。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    header = [c.value for c in ws[TEACHING_TABLE_HEADER_ROW]]
    courses = header[1:]
    for course in courses:
        if course and course not in cfg.courses:
            raise ValueError("任课表中的学科 %r 不在课程目录里" % course)

    pivot: Dict[Tuple[int, str], str] = {}
    for row in ws.iter_rows(min_row=TEACHING_TABLE_FIRST_DATA_ROW, values_only=True):
        if not row or row[0] is None:
            continue
        class_id = int(row[0])
        for course, teacher in zip(courses, row[1:]):
            if course and teacher:
                pivot[(class_id, course)] = str(teacher).strip()
    return pivot
