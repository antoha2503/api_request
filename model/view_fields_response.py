from odoo import models, fields, api
import json

class ViewFieldsResponse(models.TransientModel):
    _name = 'view.fields.response'

    api_request_id = fields.Many2one('api.request', string='Связанный запрос', domain="[('action', '=', True), ('status', '=', 'connection')]")
    name_request = fields.Char(string='Name Request', related='api_request_id.name')
    code_request = fields.Html(string='Code Request', related='api_request_id.json_code')
    table_code_request = fields.Html(string='Table result', compute='_compute_bild_table')

    @api.depends('api_request_id')
    def _compute_bild_table(self):
        for record in self:
            record.table_code_request = "<div class='text-muted'>Будь ласка, оберіть підключення...</div>"

            if not record.api_request_id or not record.api_request_id.json_code:
                continue
            result = record.api_request_id.json_code
            json_result = dict(result)
            # json_result = json.loads(result)

            # width_json = []
            # for i in result:
            #     width_json.append(len(result[i]))
            #
            # index_max_value = width_json.index(max(width_json))
            # if isinstance(result, dict):
            #
            #     name_max_value = list(result.keys())[index_max_value]
            #     rows = list(result[name_max_value][0].keys())
            #     data = []
            #     for i in range(len(result[name_max_value])):
            #         data.append(list(result[name_max_value][i].values()))

                # record.table_code_request = f'{result}\nDone- {data}\n{rows}'
            record.table_code_request =f"<pre>{json_result}</pre>\nЭто словарь! Можно брать элементы по индексу."
            if isinstance(result, list):
                record.table_code_request = "Это список! Можно брать элементы по индексу."
                # Например: first_item = result[0]
            if isinstance(result, tuple):
                record.table_code_request = "Это кортеж!"
