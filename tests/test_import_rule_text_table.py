"""排课说明.xlsx 降级为纯规则文本表——按「姓名+学科」匹配，不再提供任教班/周课时。

对应 CLAUDE.md「多年级操作流程重构」子项目5：正则解析永远跑一遍、是真正生效
的规则来源；AI 客户端给定时额外跑复核，只用来发现分歧，不单独产出规则。
"""
from pathlib import Path

import openpyxl
import pytest

from scheduler.core.config import load_config
from scheduler.core.importer import (
    import_rule_text_table, merge_teacher_facts_into_teaching_yaml,
    write_rules_generated_yaml_for_grade,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def _write_rule_sheet(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['占位表头行，程序从第3行起读'])
    ws.append(['姓名', '任教年级', '学科', '职务', '固定节次', '不能排课节次', '排课要求', '备注'])
    for row in rows:
        ws.append(row)
    wb.save(path)


class FakeAiClient:
    """返回跟正则完全一致的解析结果——用来验证「一致时不标记 mismatch」。"""

    def __init__(self, not_available=None, fixed_slots=None, requirement=None, remark=None):
        self._payload = {
            'not_available': not_available or [],
            'fixed_slots': fixed_slots or [],
            'requirement': requirement or [],
            'remark': remark or [],
        }

    class _Msg:
        def __init__(self, text):
            self.content = [type('C', (), {'text': text})()]

    @property
    def messages(self):
        import json
        payload = self._payload
        outer = self

        class _M:
            def create(self, **kwargs):
                return outer._Msg(json.dumps(payload))
        return _M()


def test_forbid_slots_rule_generated_from_not_available_column(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['李琼', '初三', '语文', '班主任', '', '周二上午不排课', '', '']])
    result = import_rule_text_table(path, cfg, grade='初三')
    forbid = next(r for r in result.rules if r['type'] == 'forbid_slots' and r['scope'].get('teacher') == '李琼')
    assert forbid['params']['slots'] == [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]]


def test_pin_window_rule_generated_from_fixed_slots_column(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['赵老师', '初三', '体育', '', '周二第8、9节', '', '', '']])
    result = import_rule_text_table(path, cfg, grade='初三')
    pin = next(r for r in result.rules if r['type'] == 'pin_window' and r['scope'].get('course') == '体育')
    assert pin['params']['slots'] == [[1, 8], [1, 9]]


def test_requirement_and_remark_columns_produce_scoped_rules(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [
        ['孙老师', '初三', '物理', '', '', '', '保证每天有1节', ''],
        ['陈老师', '初三', '数学', '', '', '', '', '两个班之间要隔开1节'],
    ])
    result = import_rule_text_table(path, cfg, grade='初三')
    daily_min = next(r for r in result.rules if r['type'] == 'daily_min')
    assert daily_min['scope']['family'] == cfg.family_of('初三', '物理')
    spacing = next(r for r in result.rules if r['type'] == 'spacing')
    assert spacing['scope']['course'] == '数学'
    assert spacing['mode'] == 'soft'


def test_teacher_facts_carry_duties_and_forbidden(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['李琼', '初三', '语文', '班主任', '', '周二上午不排课', '', '']])
    result = import_rule_text_table(path, cfg, grade='初三')
    fact = next(f for f in result.teacher_facts if f['name'] == '李琼')
    assert fact['duties'] == ['班主任']
    assert fact['forbidden'] == [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]]


def test_rejects_a_course_not_in_the_grade_catalog(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['某老师', '初三', '不存在的课', '', '', '', '', '']])
    with pytest.raises(ValueError, match='不在.*课程目录里'):
        import_rule_text_table(path, cfg, grade='初三')


def test_ai_review_matching_regex_result_is_not_flagged_as_mismatch(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['李琼', '初三', '语文', '', '', '周二上午不排课', '', '']])
    ai_client = FakeAiClient(not_available=[[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]])
    result = import_rule_text_table(path, cfg, grade='初三', ai_client=ai_client)
    echo = result.rule_echo['不能排课节次'][0]
    assert echo['mismatch'] is False
    assert echo['ai_parsed'] == echo['parsed']


def test_ai_review_disagreeing_with_regex_is_flagged_as_mismatch(tmp_path, cfg):
    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['李琼', '初三', '语文', '', '', '周二上午不排课', '', '']])
    ai_client = FakeAiClient(not_available=[[1, 1]])   # 只解析出1节，跟正则的整个上午不一致
    result = import_rule_text_table(path, cfg, grade='初三', ai_client=ai_client)
    echo = result.rule_echo['不能排课节次'][0]
    assert echo['mismatch'] is True
    assert echo['ai_parsed'] != echo['parsed']


def test_ai_review_failure_falls_back_to_regex_with_a_warning(tmp_path, cfg):
    class BrokenClient:
        @property
        def messages(self):
            raise RuntimeError('boom')

    path = tmp_path / '排课说明.xlsx'
    _write_rule_sheet(path, [['李琼', '初三', '语文', '', '', '周二上午不排课', '', '']])
    result = import_rule_text_table(path, cfg, grade='初三', ai_client=BrokenClient())
    assert any('AI 复核失败' in w for w in result.warnings)
    forbid = next(r for r in result.rules if r['type'] == 'forbid_slots' and r['scope'].get('teacher') == '李琼')
    assert forbid['params']['slots'] == [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]]


def test_write_rules_generated_yaml_for_grade_only_replaces_that_grade(tmp_path):
    path = tmp_path / 'rules.generated.yaml'
    write_rules_generated_yaml_for_grade(
        [{'type': 'forbid_slots', 'scope': {'grade': '初三', 'teacher': 'A'}, 'params': {'slots': []}, 'mode': 'hard'}],
        '初三', path)
    write_rules_generated_yaml_for_grade(
        [{'type': 'forbid_slots', 'scope': {'grade': '初一', 'teacher': 'B'}, 'params': {'slots': []}, 'mode': 'hard'}],
        '初一', path)
    import yaml
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    grades = {r['scope']['grade'] for r in data['rules']}
    assert grades == {'初三', '初一'}

    write_rules_generated_yaml_for_grade(
        [{'type': 'forbid_slots', 'scope': {'grade': '初三', 'teacher': 'C'}, 'params': {'slots': []}, 'mode': 'hard'}],
        '初三', path)
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    teachers = {r['scope']['teacher'] for r in data['rules']}
    assert teachers == {'C', 'B'}   # 初三的 A 被新一批（C）整体替换，初一的 B 不受影响


def test_merge_teacher_facts_preserves_teachers_not_mentioned(tmp_path):
    import yaml
    path = tmp_path / 'teaching.yaml'
    path.write_text(yaml.safe_dump({
        'grade': '初三', 'classes': [1],
        'teachers': [{'name': '徐仪涵', 'duties': [], 'forbidden': []}],
        'tasks': [],
    }, allow_unicode=True), encoding='utf-8')

    merge_teacher_facts_into_teaching_yaml(
        [{'name': '李琼', 'duties': ['班主任'], 'forbidden': [[1, 1]]}], '初三', path)

    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    by_name = {t['name']: t for t in data['teachers']}
    assert by_name['李琼']['duties'] == ['班主任']
    assert by_name['徐仪涵']['duties'] == []   # 没提到的教师原样保留


def test_merge_teacher_facts_rejects_a_grade_mismatch(tmp_path):
    import yaml
    path = tmp_path / 'teaching.yaml'
    path.write_text(yaml.safe_dump({'grade': '初三', 'classes': [], 'teachers': [], 'tasks': []},
                                   allow_unicode=True), encoding='utf-8')
    with pytest.raises(ValueError, match='年级'):
        merge_teacher_facts_into_teaching_yaml([{'name': 'X', 'duties': [], 'forbidden': []}], '初一', path)


def test_merge_teacher_facts_requires_teaching_yaml_to_exist_first(tmp_path):
    path = tmp_path / 'teaching.yaml'
    with pytest.raises(ValueError, match='任课表'):
        merge_teacher_facts_into_teaching_yaml([{'name': 'X', 'duties': [], 'forbidden': []}], '初三', path)
