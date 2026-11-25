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
        """Download the selected API response as a formatted Excel table."""
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

        columns, rows = self._to_table(response_data)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('API Response')
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#6F5A9B',
            'font_color': '#FFFFFF',
            'text_wrap': True,
            'valign': 'top',
        })
        worksheet.freeze_panes(1, 0)

        for column_index, column_name in enumerate(columns):
            worksheet.write_string(0, column_index, str(column_name), header_format)

        for row_index, row in enumerate(rows, start=1):
            for column_index, value in enumerate(row):
                # Write API values as text so values beginning with '=' are not treated as formulas.
                worksheet.write_string(row_index, column_index, self._cell_text(value))

        if columns:
            worksheet.autofilter(0, 0, max(len(rows), 0), len(columns) - 1)
            for column_index, column_name in enumerate(columns):
                sample_width = max(
                    [len(str(column_name))]
                    + [len(self._cell_text(row[column_index])) for row in rows[:100]]
                )
                worksheet.set_column(column_index, column_index, min(max(sample_width + 2, 12), 50))

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
    def _to_table(data):
        """Use the same simple row/column layout as the dashboard table."""
        if isinstance(data, list):
            if data and all(isinstance(item, dict) for item in data):
                columns = list(dict.fromkeys(key for item in data for key in item))
                if not columns:
                    return ['Значение'], [[json.dumps(item, ensure_ascii=False)] for item in data]
                return columns, [[item.get(column) for column in columns] for item in data]
            return ['Значение'], [[item] for item in data]

        if isinstance(data, dict):
            return ['Поле', 'Значение'], [[key, value] for key, value in data.items()]

        return ['Ответ'], [[data]]

    @staticmethod
    def _cell_text(value):
        """Convert nested JSON values to safe, readable Excel cell text."""
        if value is None:
            return ''
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
