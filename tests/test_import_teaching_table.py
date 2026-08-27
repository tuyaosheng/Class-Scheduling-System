"""任课表（矩阵）单独导入——不依赖排课说明.xlsx，周课时来自课程计划。

对应 CLAUDE.md「任课表 vs 排课说明.xlsx 的分工」：任课表是"谁教谁"的
唯一来源，周课时改由课程与学科系步骤的课程计划提供，不再靠 Excel 每行
的"周课时"列或 0.5 课时探测。
"""
from pathlib import Path

import openpyxl
import pytest

from scheduler.core.config import load_config
from scheduler.core.importer import build_dataset_from_pivot, import_teaching_table
from scheduler.core.models import Teacher

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def _write_teaching_table(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['初三'])
    ws.append(['班别', '语文', '数学'])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_periods_come_from_the_grade_plan_not_the_excel(tmp_path, cfg):
    """初三课程计划里语文=7节、数学=5节（plans.yaml）——任课表本身不含课时数字。"""
    path = tmp_path / '任课表.xlsx'
    _write_teaching_table(path, [[1, '李琼', '徐仪涵'], [2, '郑艳秀', '徐仪涵']])

    result = import_teaching_table(path, cfg, grade='初三')
    by_key = {(t.class_id, t.course): t for t in result.dataset.tasks}
    assert by_key[(1, '语文')].periods == 7
    assert by_key[(1, '数学')].periods == 5
    assert by_key[(1, '语文')].teacher == '李琼'
    assert by_key[(2, '语文')].teacher == '郑艳秀'


def test_no_rules_are_generated_from_this_import_path(tmp_path, cfg):
    """规则由 rules.yaml/rules.generated.yaml 在求解时另行加载，不是这条导入路径的产物。"""
    path = tmp_path / '任课表.xlsx'
    _write_teaching_table(path, [[1, '李琼', '徐仪涵']])
    result = import_teaching_table(path, cfg, grade='初三')
    assert result.rules == []


def test_teachers_have_no_forbidden_slots_from_this_path(tmp_path, cfg):
    """任课表本身不含"不能排课节次"这类信息——那是排课说明.xlsx 的职责（子项目5）。"""
    path = tmp_path / '任课表.xlsx'
    _write_teaching_table(path, [[1, '李琼', '徐仪涵']])
    result = import_teaching_table(path, cfg, grade='初三')
    assert result.dataset.teachers['李琼'].forbidden == []


def test_external_courses_are_skipped_even_if_present_in_the_table(tmp_path, cfg):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['初三'])
    ws.append(['班别', '语文', '班会'])   # 班会是 external 占位课程
    ws.append([1, '李琼', '某班主任'])
    path = tmp_path / '任课表.xlsx'
    wb.save(path)

    result = import_teaching_table(path, cfg, grade='初三')
    assert [t.course for t in result.dataset.tasks] == ['语文']


def test_rejects_a_course_with_no_periods_configured_in_the_plan(cfg):
    """课程目录里有这门课、但课程计划没给周课时——用户还没在"课程与学科系"设置好。"""
    from scheduler.core.models import Course

    cfg2 = cfg.model_copy(deep=True)
    cfg2.courses['初三'] = dict(cfg2.courses['初三'])
    cfg2.courses['初三']['冷门课'] = Course(name='冷门课', family='冷门课')

    with pytest.raises(ValueError, match='没有在.*课程计划里设置周课时'):
        build_dataset_from_pivot({(1, '冷门课'): '某老师'}, cfg2, grade='初三')


def test_existing_teacher_duties_and_forbidden_slots_survive_a_teaching_table_save(cfg):
    """真实发生过的数据丢失（浏览器实测中招过一次）：编辑任课表单个格子并保存，
    曾经会把该教师之前从排课说明.xlsx 导入算出来的 duties/forbidden 整体清空，
    因为这条路径本身不产生这类信息、之前是每次都新建一个空白 Teacher。"""
    existing = {'李琼': Teacher(name='李琼', duties=['班主任'], forbidden=[[1, 1], [2, 3]])}
    result = build_dataset_from_pivot({(1, '语文'): '李琼'}, cfg, grade='初三', existing_teachers=existing)
    assert result.dataset.teachers['李琼'].duties == ['班主任']
    assert result.dataset.teachers['李琼'].forbidden == [[1, 1], [2, 3]]


def test_a_genuinely_new_teacher_not_in_existing_teachers_gets_a_blank_record(cfg):
    result = build_dataset_from_pivot({(1, '语文'): '新老师'}, cfg, grade='初三', existing_teachers={})
    assert result.dataset.teachers['新老师'].duties == []
    assert result.dataset.teachers['新老师'].forbidden == []


def test_build_dataset_from_pivot_matches_import_teaching_table(tmp_path, cfg):
    """编辑页面直接提交 pivot、和上传文件走 parse_teaching_table，两条路径
    产出的 Dataset 必须一致——共用同一个构建函数才有意义。"""
    path = tmp_path / '任课表.xlsx'
    _write_teaching_table(path, [[1, '李琼', '徐仪涵']])
    via_file = import_teaching_table(path, cfg, grade='初三')
    via_pivot = build_dataset_from_pivot({(1, '语文'): '李琼', (1, '数学'): '徐仪涵'}, cfg, grade='初三')
    assert via_file.dataset.tasks == via_pivot.dataset.tasks
