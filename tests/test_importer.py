from pathlib import Path

import pytest

from scheduler.core.config import load_config
from scheduler.core.importer import import_excel

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / '任课与排课说明.xlsx'
CONFIG_DIR = ROOT / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def result():
    cfg = load_config(CONFIG_DIR)
    return import_excel(EXCEL, cfg, grade='初三')


def test_teacher_count_is_121(result):
    """设计文档 §15：121 位教师。心美合并时按 (课程,班集合) 去重会误记为 119。"""
    assert len(result.dataset.teachers) == 121


def test_task_count_is_544(result):
    """227 行 × 各自班数 = 544 个 (教师,课程,班) 三元组。"""
    assert len(result.dataset.tasks) == 544


def test_slot_consuming_task_count_is_512(result):
    """扣掉 32 个双周（心理）任务，得到设计文档实测的 512。"""
    assert sum(1 for t in result.dataset.tasks if t.consumes_slot) == 512


def test_32_classes_each_with_17_courses(result):
    assert sorted(result.dataset.classes) == list(range(1, 33))
    from collections import Counter
    per_class = Counter(t.class_id for t in result.dataset.tasks)
    assert set(per_class.values()) == {17}


def test_every_class_occupies_41_slots(result):
    from collections import Counter
    used = Counter()
    for t in result.dataset.tasks:
        if t.consumes_slot:
            used[t.class_id] += t.periods
    assert set(used.values()) == {41}


def test_no_warnings_on_real_data(result):
    assert result.warnings == []


# ---- 教师级禁排合并：本计划的核心正确性点 ----

def test_forbidden_is_unioned_across_a_teachers_rows(result):
    """陈芬的综实1 行禁排为空，但她本人周四下午在开会。"""
    chen = result.dataset.teachers['陈芬']
    forbidden = chen.forbidden_slots()
    for period in (6, 7, 8, 9):
        assert (3, period) in forbidden, '周四下午应对陈芬的全部课程生效'
    zongshi1 = [t for t in result.dataset.tasks if t.teacher == '陈芬' and t.course == '综实1']
    assert zongshi1, '陈芬应有综实1 任务'


def test_homeroom_teacher_monday_meeting_applies_to_all_her_courses(result):
    """李琼班会行禁排为空，但周一4、5节班主任会对她全部课程生效。"""
    forbidden = result.dataset.teachers['李琼'].forbidden_slots()
    assert (0, 4) in forbidden and (0, 5) in forbidden
    assert (4, 1) in forbidden   # 周五上午语文科组会


def test_119_teachers_have_forbidden_slots(result):
    n = sum(1 for t in result.dataset.teachers.values() if t.forbidden)
    assert n == 119


def test_duties_are_collected(result):
    assert '班主任' in result.dataset.teachers['李琼'].duties


# ---- 0.5 课时转换 ----

def test_half_period_becomes_one_period_with_parity(result):
    art = [t for t in result.dataset.tasks if t.course == '美术']
    psy = [t for t in result.dataset.tasks if t.course == '心理']
    assert len(art) == 32 and len(psy) == 32
    assert all(t.periods == 1 and t.parity == '单周' for t in art)
    assert all(t.periods == 1 and t.parity == '双周' for t in psy)


def test_art_and_psych_teachers_both_survive(result):
    """梁艳红与郭泽琪键相同，简化去重会丢掉一位 —— 见设计文档 §3.3。"""
    names = set(result.dataset.teachers)
    assert {'梁艳红', '胡美玲', '郭泽琪', '胡义城'} <= names


# ---- 生成的规则 ----

def rules_of(result, rtype):
    return [r for r in result.rules if r['type'] == rtype]


def test_forbid_slots_rule_per_teacher(result):
    assert len(rules_of(result, 'forbid_slots')) == 119
    rule = next(r for r in rules_of(result, 'forbid_slots')
                if r['scope']['teacher'] == '陈芬')
    assert rule['mode'] == 'hard'
    assert [3, 6] in rule['params']['slots']


def test_pin_window_rules(result):
    pins = {r['scope']['course']: r for r in rules_of(result, 'pin_window')}
    assert set(pins) == {'班会', '综实2', '校本1', '体比', '体选'}
    assert pins['班会']['params']['slots'] == [[0, 9]]
    assert sorted(pins['体比']['params']['slots']) == [[1, 8], [1, 9]]
    assert sorted(pins['校本1']['params']['slots']) == [[2, 8], [2, 9]]


def test_daily_min_rules_use_family_scope(result):
    """必须是学科系 —— 写成 course 会让物理 4 节配 5 天，直接无解。"""
    fams = {r['scope']['family'] for r in rules_of(result, 'daily_min')}
    assert fams == {'语文', '数学', '英语', '物理'}
    assert all(r['params']['n'] == 1 for r in rules_of(result, 'daily_min'))


def test_daily_max_rules(result):
    fams = {r['scope']['family'] for r in rules_of(result, 'daily_max')}
    assert fams == {'化学', '道法', '历史', '音乐'}
    assert all(r['params']['n'] == 1 for r in rules_of(result, 'daily_max'))


def test_weekday_exact_rule_for_pe(result):
    rules = rules_of(result, 'weekday_exact')
    assert len(rules) == 1
    assert rules[0]['scope']['family'] == '体育'
    assert rules[0]['params'] == {'weekdays': ['周一', '周三', '周四'], 'n': 1}


def test_alternate_rule_is_deduplicated_to_one(result):
    rules = rules_of(result, 'alternate_weeks')
    assert len(rules) == 1
    assert rules[0]['params']['pair'] == ['美术', '心理']


def test_consecutive_and_spacing_scoped_to_course_not_family(result):
    cons = rules_of(result, 'consecutive')
    assert len(cons) == 1
    assert cons[0]['scope']['course'] == '语文'
    assert 'family' not in cons[0]['scope']
    assert rules_of(result, 'spacing')[0]['params']['min_gap'] == 1


def test_every_rule_has_grade_scope(result):
    assert all(r['scope'].get('grade') == '初三' for r in result.rules)


def test_yaml_roundtrip(tmp_path, result):
    import yaml
    from scheduler.core.importer import write_teaching_yaml, write_rules_yaml
    tpath, rpath = tmp_path / 'teaching.yaml', tmp_path / 'rules.generated.yaml'
    write_teaching_yaml(result, tpath)
    write_rules_yaml(result, rpath)
    teaching = yaml.safe_load(tpath.read_text(encoding='utf-8'))
    rules = yaml.safe_load(rpath.read_text(encoding='utf-8'))
    assert len(teaching['tasks']) == 544
    assert len(teaching['teachers']) == 121
    assert len(rules['rules']) == len(result.rules)
