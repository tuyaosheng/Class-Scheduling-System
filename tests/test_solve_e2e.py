from collections import Counter, defaultdict
from pathlib import Path

import pytest

from scheduler.core import calendar as cal
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel
from scheduler.core.rules import load_rules
from scheduler.core.solver import solve

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'
EXCEL = ROOT / '任课与排课说明.xlsx'


@pytest.fixture(scope='module')
def solved():
    cfg = load_config(CONFIG_DIR)
    result = import_excel(EXCEL, cfg, grade='初三')
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    solution = solve(result.dataset, cfg, rules, max_seconds=30)
    return cfg, result.dataset, solution


def test_grade3_is_feasible(solved):
    _, _, solution = solved
    assert solution.feasible, '初三 32 班应可排，状态=%s' % solution.status


def test_solve_time_is_interactive(solved):
    """设计文档实测 0.6 秒。明显慢于此说明建模有问题，不要靠调大超时掩盖。"""
    _, _, solution = solved
    assert solution.wall_time < 5.0, '耗时 %.1fs，远超基线 0.6s' % solution.wall_time


def test_placement_count_matches_total_periods(solved):
    _, dataset, solution = solved
    assert len(solution.placements) == sum(t.periods for t in dataset.tasks)


def test_every_class_uses_41_distinct_slots(solved):
    _, dataset, solution = solved
    by_class = defaultdict(set)
    for p in solution.placements:
        if p.parity != '双周':
            by_class[p.class_id].add(p.slot)
    assert set(Counter({c: len(s) for c, s in by_class.items()}).values()) == {41}


def test_no_class_double_booked(solved):
    _, _, solution = solved
    for parity in ('单周', '双周'):
        seen = Counter((p.class_id, p.slot) for p in solution.placements
                       if p.parity in (None, parity))
        assert max(seen.values()) == 1


def test_no_teacher_double_booked(solved):
    cfg, _, solution = solved
    for parity in ('单周', '双周'):
        seen = Counter((p.teacher, p.slot) for p in solution.placements
                       if p.parity in (None, parity)
                       and not cfg.courses[p.course].multi_class)
        assert max(seen.values()) == 1


def test_art_and_psych_share_slots(solved):
    _, _, solution = solved
    art = {(p.class_id, p.slot) for p in solution.placements if p.course == '美术'}
    psy = {(p.class_id, p.slot) for p in solution.placements if p.course == '心理'}
    assert art == psy and len(art) == 32


def test_banhui_pinned_to_monday_period9(solved):
    _, _, solution = solved
    banhui = [p for p in solution.placements if p.course == '班会']
    assert len(banhui) == 32
    assert all(cal.slot_of(p.slot) == (0, 9) for p in banhui)


def test_physics_family_every_day(solved):
    cfg, _, solution = solved
    by_class_day = defaultdict(int)
    for p in solution.placements:
        if cfg.family_of(p.course) == '物理':
            by_class_day[(p.class_id, cal.slot_of(p.slot)[0])] += 1
    for class_id in range(1, 33):
        for day in range(5):
            assert by_class_day[(class_id, day)] >= 1, '%d班周%d没有物理系课程' % (class_id, day + 1)


def test_export_excel(tmp_path, solved):
    import openpyxl
    from scheduler.core.exporter import export_excel
    _, dataset, solution = solved
    path = tmp_path / '课表.xlsx'
    export_excel(solution, dataset, path)
    wb = openpyxl.load_workbook(path)
    assert '班级课表' in wb.sheetnames and '教师课表' in wb.sheetnames
    ws = wb['班级课表']
    assert ws.max_row == cal.N_SLOTS + 1        # 表头 + 45 格
    assert ws.max_column == 32 + 2              # 星期、节次 + 32 个班


def test_cli_solve(tmp_path, monkeypatch, capsys):
    from scheduler.cli import main
    monkeypatch.chdir(ROOT)
    out = tmp_path / '课表.xlsx'
    assert main(['solve', '--out', str(out), '--max-seconds', '30']) == 0
    assert out.exists()
    out_text = capsys.readouterr().out
    assert 'OPTIMAL' in out_text or 'FEASIBLE' in out_text
