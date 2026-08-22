from pathlib import Path

import pytest

from scheduler.cli import main, render_import_report
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / '任课与排课说明.xlsx'
CONFIG_DIR = ROOT / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def result():
    cfg = load_config(CONFIG_DIR)
    return import_excel(EXCEL, cfg, grade='初三')


@pytest.fixture(scope='module')
def report(result):
    from scheduler.cli import _read_rows
    return render_import_report(result, rows=_read_rows(EXCEL))


def test_report_shows_headline_numbers(report):
    assert '教师 121' in report
    assert '班级 32' in report
    assert '任务 384' in report


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


def test_report_without_rows_omits_echo_section(result):
    """rows=None 时不输出回显段，但概览部分不受影响（brief Step 4 说明的两种路径之一）。"""
    bare = render_import_report(result)
    assert '中文规则解析回显' not in bare
    assert '教师 121' in bare


def test_dry_run_writes_nothing(tmp_path, capsys):
    """不带 --write 时，配置目录里不应新增 teaching.yaml / rules.generated.yaml。"""
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    for name in ('calendar.yaml', 'courses.yaml', 'plans.yaml', 'venues.yaml'):
        (config_dir / name).write_text(
            (CONFIG_DIR / name).read_text(encoding='utf-8'), encoding='utf-8')

    code = main(['import', str(EXCEL), '--grade', '初三', '--config-dir', str(config_dir)])
    assert code == 0
    assert '教师 121' in capsys.readouterr().out
    assert not (config_dir / 'teaching.yaml').exists()
    assert not (config_dir / 'rules.generated.yaml').exists()


def test_write_flag_creates_both_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    code = main(['import', str(EXCEL), '--grade', '初三',
                 '--write', '--out-dir', str(tmp_path)])
    assert code == 0
    assert (tmp_path / 'teaching.yaml').exists()
    assert (tmp_path / 'rules.generated.yaml').exists()
