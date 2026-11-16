"""Produce scoped inventory reports and audited CSV exports."""
import csv
import io

from fastapi import HTTPException

from app.admin.repository import AdminRepository
from app.applications.repository import ApplicationRepository
from app.applications.schema import Application
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schema import Portfolio

MAX_EXPORT_ROWS = 10000


def csv_cell(value: object) -> str:
    """Make text safe to open in spreadsheet applications."""
    text = '' if value is None else str(value)
    if isinstance(value, str) and (text.lstrip(' ').startswith(('\t', '\r', '\n')) or text.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + text
    return text


async def export_report(repo: ApplicationRepository | PortfolioRepository, actor: dict, query: dict, kind: str) -> str:
    """Export all matching rows within a fixed cap and persist an audit event."""
    rows, total = await repo.list_page(query, 100, 0)
    if total > MAX_EXPORT_ROWS:
        raise HTTPException(422, 'Too many rows to export; narrow the filters')
    for offset in range(100, total, 100):
        page, current_total = await repo.list_page(query, 100, offset)
        if current_total > MAX_EXPORT_ROWS:
            raise HTTPException(422, 'Too many rows to export; narrow the filters')
        rows.extend(page)
    columns = list((Application if kind == 'applications' else Portfolio).model_fields)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([csv_cell(row.get(key)) for key in columns])
    await AdminRepository(repo.db).audit(actor, 'export', kind[:-1], None, f'{kind.title()} report exported')
    return output.getvalue()
