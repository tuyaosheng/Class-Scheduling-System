"""课表导出为 Excel。"""
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font

from . import calendar as cal


_RESERVED_LABEL = '（教务固定安排）'


def _write_grid(ws, columns, cell_text, reserved_slots=()):
    ws.cell(row=1, column=1, value='星期').font = Font(bold=True)
    ws.cell(row=1, column=2, value='节次').font = Font(bold=True)
    for col, name in enumerate(columns, start=3):
        ws.cell(row=1, column=col, value=name).font = Font(bold=True)
    for slot in range(cal.N_SLOTS):
        day, period = cal.slot_of(slot)
        row = slot + 2
        ws.cell(row=row, column=1, value=cal.DAYS[day])
        ws.cell(row=row, column=2, value=period)
        for col, name in enumerate(columns, start=3):
            text = cell_text(name, slot) or (_RESERVED_LABEL if slot in reserved_slots else '')
            if text:
                cell = ws.cell(row=row, column=col, value=text)
                cell.alignment = Alignment(horizontal='center')
    ws.freeze_panes = 'C2'


def export_excel(solution, dataset, path, cfg=None) -> None:
    by_class = defaultdict(list)
    by_teacher = defaultdict(list)
    for p in solution.placements:
        by_class[(p.class_id, p.slot)].append(p)
        by_teacher[(p.teacher, p.slot)].append(p)

    reserved = cfg.reserved_slot_indices(dataset.grade) if cfg else set()

    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = '班级课表'
    _write_grid(
        ws, dataset.classes,
        lambda class_id, slot: '/'.join(
            '%s%s' % (p.course, '(%s)' % p.parity if p.parity else '')
            for p in by_class.get((class_id, slot), [])),
        reserved_slots=reserved)

    ws2 = wb.create_sheet('教师课表')
    _write_grid(
        ws2, sorted(dataset.teachers),
        lambda teacher, slot: '/'.join(
            '%d班%s' % (p.class_id, p.course)
            for p in by_teacher.get((teacher, slot), [])))

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
