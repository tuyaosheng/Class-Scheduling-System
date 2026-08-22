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


from scheduler.core.importer import ImportResult, merge_teaching_and_rules


def _write_rules_sheet(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["占位表头行，程序从第3行起读"])
    ws.append(["姓名", "任教年级", "学科", "任教班", "周课时", "职务",
               "固定节次", "不能排课节次", "排课要求", "备注"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_merge_builds_tasks_when_both_sources_agree(tmp_path, cfg):
    teaching_path = tmp_path / "任课表.xlsx"
    _write_teaching_table(teaching_path)
    rules_path = tmp_path / "排课说明.xlsx"
    _write_rules_sheet(rules_path, [
        ["李琼", "初三", "语文", "1", 6, None, None, None, "保证每天有1节", None],
        ["郑艳秀", "初三", "语文", "2", 6, None, None, None, "保证每天有1节", None],
        ["徐仪涵", "初三", "数学", "1,2", 5, None, None, None, None, None],
    ])
    result = merge_teaching_and_rules(teaching_path, rules_path, cfg, grade="初三")
    assert isinstance(result, ImportResult)
    assert result.conflicts == []
    by_key = {(t.class_id, t.course): t.teacher for t in result.dataset.tasks}
    assert by_key[(1, "语文")] == "李琼"
    assert by_key[(2, "数学")] == "徐仪涵"


def test_merge_flags_teacher_mismatch_as_conflict(tmp_path, cfg):
    teaching_path = tmp_path / "任课表.xlsx"
    _write_teaching_table(teaching_path)   # 1班语文=李琼
    rules_path = tmp_path / "排课说明.xlsx"
    _write_rules_sheet(rules_path, [
        ["王老师", "初三", "语文", "1", 6, None, None, None, None, None],   # 排课说明说是王老师
        ["郑艳秀", "初三", "语文", "2", 6, None, None, None, None, None],   # 2班语文与任课表一致，隔离出唯一的冲突场景
        ["徐仪涵", "初三", "数学", "1,2", 5, None, None, None, None, None],
    ])
    result = merge_teaching_and_rules(teaching_path, rules_path, cfg, grade="初三")
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict["class_id"] == 1 and conflict["course"] == "语文"
    assert conflict["from_teaching_table"] == "李琼"
    assert conflict["from_rules_sheet"] == "王老师"
    by_key = {(t.class_id, t.course): t.teacher for t in result.dataset.tasks}
    assert (1, "语文") not in by_key


def test_merge_flags_missing_rules_row_as_conflict(tmp_path, cfg):
    teaching_path = tmp_path / "任课表.xlsx"
    _write_teaching_table(teaching_path)   # 任课表里有 1班数学=徐仪涵
    rules_path = tmp_path / "排课说明.xlsx"
    _write_rules_sheet(rules_path, [
        ["李琼", "初三", "语文", "1", 6, None, None, None, None, None],
        # 数学没有对应行——任课表说 1班数学是徐仪涵，排课说明查不到周课时
    ])
    result = merge_teaching_and_rules(teaching_path, rules_path, cfg, grade="初三")
    missing = [c for c in result.conflicts if c["course"] == "数学"]
    assert len(missing) >= 1
    assert missing[0]["from_teaching_table"] == "徐仪涵"
    assert missing[0]["from_rules_sheet"] is None


def test_merge_builds_rule_echo_for_review(tmp_path, cfg):
    teaching_path = tmp_path / "任课表.xlsx"
    _write_teaching_table(teaching_path)
    rules_path = tmp_path / "排课说明.xlsx"
    _write_rules_sheet(rules_path, [
        ["李琼", "初三", "语文", "1", 6, None, None, "周五上午不排课", "保证每天有1节", None],
        ["徐仪涵", "初三", "数学", "1,2", 5, None, None, None, None, None],
    ])
    result = merge_teaching_and_rules(teaching_path, rules_path, cfg, grade="初三")
    echo = result.rule_echo["不能排课节次"]
    assert any(item["raw"] == "周五上午不排课" for item in echo)
    req_echo = result.rule_echo["排课要求"]
    assert any(item["raw"] == "保证每天有1节" for item in req_echo)


def test_merge_ai_engine_uses_parse_row_ai(tmp_path, cfg):
    import json
    from types import SimpleNamespace

    class FakeMessages:
        def create(self, **kwargs):
            payload = {
                "not_available": [], "fixed_slots": [],
                "requirement": [{"type": "daily_min", "params": {"n": 1}}],
                "remark": [],
            }
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])

    class FakeClient:
        messages = FakeMessages()

    teaching_path = tmp_path / "任课表.xlsx"
    _write_teaching_table(teaching_path)
    rules_path = tmp_path / "排课说明.xlsx"
    _write_rules_sheet(rules_path, [
        ["李琼", "初三", "语文", "1", 6, None, None, None, "保证每天有1节", None],
        ["徐仪涵", "初三", "数学", "1,2", 5, None, None, None, None, None],
    ])
    result = merge_teaching_and_rules(teaching_path, rules_path, cfg, grade="初三",
                                      rule_engine="ai", ai_client=FakeClient())
    daily_min = [r for r in result.rules if r["type"] == "daily_min"]
    assert len(daily_min) >= 1
