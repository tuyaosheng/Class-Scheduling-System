from pathlib import Path

import pytest

from scheduler.cli import main, render_import_report
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / '任课与排课说明.xlsx'
CONFIG_DIR = ROOT / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def report():
    from scheduler.cli import _read_rows
    cfg = load_config(CONFIG_DIR)
    result = import_excel(EXCEL, cfg, grade='初三')
    return render_import_report(result, rows=_read_rows(EXCEL))


def test_report_shows_headline_numbers(report):
    assert '教师 121' in report
    assert '班级 32' in report
    assert '任务 544' in report


def test_report_echoes_original_text_next_to_parse_result(report):
    """教务要能一眼核对：原文在左，译出的节次在右。"""
    assert '周二上午，周五第4，5节不排课' in report
    assert '周五 4,5' in report          # 逗号被正确当成数字分隔符
    assert '周二 1,2,3,4,5' in report


def test_report_covers_all_22_forbid_variants(report):
    section = report.split('不能排课节次')[1].split('固定节次')[0]
    assert section.count('->') == 22


def test_report_shows_fixed_window_semantics(report):
    assert '周二第8、9节' in report
    assert '周二 8,9' in report


def test_dry_run_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    code = main(['import', str(EXCEL), '--grade', '初三'])
    assert code == 0
    assert '教师 121' in capsys.readouterr().out


def test_write_flag_creates_both_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    code = main(['import', str(EXCEL), '--grade', '初三',
                 '--write', '--out-dir', str(tmp_path)])
    assert code == 0
    assert (tmp_path / 'teaching.yaml').exists()
    assert (tmp_path / 'rules.generated.yaml').exists()
