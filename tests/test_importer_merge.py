from pathlib import Path

import openpyxl
import pytest

from scheduler.core.config import load_config
from scheduler.core.importer import parse_teaching_table

CONFIG_DIR = Path(__file__).resolve().parents[1] / "scheduler" / "config"


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_DIR)


def _write_teaching_table(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["初三"])
    ws.append(["班别", "语文", "数学"])
    ws.append([1, "李琼", "徐仪涵"])
    ws.append([2, "郑艳秀", "徐仪涵"])
    wb.save(path)


def test_parse_teaching_table_builds_class_course_to_teacher_map(tmp_path, cfg):
    path = tmp_path / "任课表.xlsx"
    _write_teaching_table(path)
    pivot = parse_teaching_table(path, cfg)
    assert pivot[(1, "语文")] == "李琼"
    assert pivot[(1, "数学")] == "徐仪涵"
    assert pivot[(2, "语文")] == "郑艳秀"
    assert pivot[(2, "数学")] == "徐仪涵"
    assert len(pivot) == 4


def test_parse_teaching_table_rejects_unknown_course(tmp_path, cfg):
    path = tmp_path / "任课表.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["初三"])
    ws.append(["班别", "不存在的课"])
    ws.append([1, "某老师"])
    wb.save(path)
    with pytest.raises(ValueError, match="不在课程目录里"):
        parse_teaching_table(path, cfg)
