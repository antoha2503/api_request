import io
import json
from html.parser import HTMLParser
import re

import xlsxwriter

from odoo import http
from odoo.http import content_disposition, request


class _ResponseTextParser(HTMLParser):
    """Extract readable response text from the HTML field stored by Odoo."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return ''.join(self.parts).strip()


class ApiResponseExportController(http.Controller):
    @http.route('/api_request/export_xlsx', type='http', auth='user', methods=['GET'])
    def export_xlsx(self, request_id=None, **kwargs):
        """Download the selected API response as a workbook with nested data sheets."""
        try:
            request_id = int(request_id)
        except (TypeError, ValueError):
            return request.not_found()

        # Search with the current user's environment so normal model access rules apply.
        record = request.env['api.request'].search([('id', '=', request_id)], limit=1)
        if not record:
            return request.not_found()

        text_parser = _ResponseTextParser()
        text_parser.feed(record.json_code or '')
        try:
            response_data = json.loads(text_parser.get_text())
        except json.JSONDecodeError:
            error_response = request.make_response(
                'The selected response is not valid JSON and cannot be exported as a table.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
            )
            error_response.status_code = 400
            return error_response

        tables = self._collect_tables(response_data)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#6F5A9B',
            'font_color': '#FFFFFF',
            'text_wrap': True,
            'valign': 'top',
        })

        # Create one worksheet per nested JSON path and include parent row references.
        for table_path, table in tables.items():
            worksheet = workbook.add_worksheet(table['sheet_name'])
            has_parent = table_path != ''
            headers = (
                ['Родительский лист', 'Строка родителя'] if has_parent else []
            ) + table['columns']
            worksheet.freeze_panes(1, 0)

            for column_index, header in enumerate(headers):
                worksheet.write_string(0, column_index, str(header), header_format)

            for row_index, entry in enumerate(table['rows'], start=1):
                column_offset = 0
                if has_parent:
                    worksheet.write_string(row_index, 0, entry['parent_sheet'])
                    worksheet.write_number(row_index, 1, entry['parent_row'])
                    column_offset = 2

                for column_index, column_name in enumerate(table['columns']):
                    value = entry['values'].get(column_name)
                    cell_text = self._cell_text(value)
                    if isinstance(value, (dict, list)):
                        nested_path = f"{table_path}.{column_name}" if table_path else str(column_name)
                        nested_sheet = tables[nested_path]['sheet_name']
                        cell_text = f"Данные находятся на листе: {nested_sheet}"
                    # Write all API values as text so values beginning with '=' stay inert.
                    worksheet.write_string(row_index, column_index + column_offset, cell_text)

            if headers:
                worksheet.autofilter(0, 0, max(len(table['rows']), 0), len(headers) - 1)
                for column_index, header in enumerate(headers):
                    sample_values = [str(header)]
                    if has_parent and column_index == 0:
                        sample_values.extend(entry['parent_sheet'] for entry in table['rows'][:100])
                    elif has_parent and column_index == 1:
                        sample_values.extend(str(entry['parent_row']) for entry in table['rows'][:100])
                    else:
                        data_index = column_index - column_offset
                        column_name = table['columns'][data_index]
                        for entry in table['rows'][:100]:
                            value = entry['values'].get(column_name)
                            if isinstance(value, (dict, list)):
                                nested_path = f"{table_path}.{column_name}" if table_path else str(column_name)
                                value = f"Данные находятся на листе: {tables[nested_path]['sheet_name']}"
                            else:
                                value = self._cell_text(value)
                            sample_values.append(value)
                    width = min(max(max(map(len, sample_values)) + 2, 12), 50)
                    worksheet.set_column(column_index, column_index, width)

        workbook.close()

        safe_name = re.sub(r'[^\w.-]+', '_', record.name or 'api_response').strip('._')
        filename = f'{safe_name or "api_response"}.xlsx'
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ],
        )

    @staticmethod
    def _root_rows(data):
        """Convert any valid JSON root value into rows for the first worksheet."""
        if isinstance(data, list):
            if data and all(isinstance(item, dict) for item in data):
                return [item or {'Значение': '{}'} for item in data]
            return [{'Значение': item} for item in data]
        if isinstance(data, dict):
            return [data or {'Значение': '{}'}]
        return [{'Ответ': data}]

    @classmethod
    def _nested_rows(cls, value):
        """Convert a nested object or list into rows in its own worksheet."""
        if isinstance(value, dict):
            return [value or {'Значение': '{}'}]
        if isinstance(value, list):
            if not value:
                return [{'Значение': '(пустой список)'}]
            if all(isinstance(item, dict) for item in value):
                return [item or {'Значение': '{}'} for item in value]
            return [{'Значение': item} for item in value]
        return [{'Значение': value}]

    @classmethod
    def _collect_tables(cls, data):
        """Gather every nested list/object and map it to a parent worksheet row."""
        tables = {}
        sheet_names = {'': 'API Response'}
        used_sheet_names = {'api response'}

        def get_sheet_name(path):
            if path in sheet_names:
                return sheet_names[path]
            candidate = re.sub(r'[\\/?*\[\]:]', '_', path).strip("'_") or 'Nested data'
            candidate = candidate[:31]
            unique_candidate = candidate
            suffix_number = 2
            while unique_candidate.casefold() in used_sheet_names:
                suffix = f'_{suffix_number}'
                unique_candidate = f'{candidate[:31 - len(suffix)]}{suffix}'
                suffix_number += 1
            sheet_names[path] = unique_candidate
            used_sheet_names.add(unique_candidate.casefold())
            return unique_candidate

        def collect(path, rows, parent_sheet=None, parent_row=None):
            table = tables.setdefault(path, {
                'sheet_name': get_sheet_name(path),
                'rows': [],
                'columns': [],
            })
            for values in rows:
                excel_row = len(table['rows']) + 2
                table['rows'].append({
                    'values': values,
                    'parent_sheet': parent_sheet,
                    'parent_row': parent_row,
                })
                for column_name, value in values.items():
                    if isinstance(value, (dict, list)):
                        nested_path = f"{path}.{column_name}" if path else str(column_name)
                        collect(nested_path, cls._nested_rows(value), table['sheet_name'], excel_row)

            table['columns'] = list(dict.fromkeys(
                column for entry in table['rows'] for column in entry['values']
            )) or ['Значение']

        collect('', cls._root_rows(data))
        return tables

    @staticmethod
    def _cell_text(value):
        """Convert scalar JSON values into safe, readable Excel cell text."""
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (dict, list)):
            return ''
        return str(value)
