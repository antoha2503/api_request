from html import escape
import json
import re
import xml.etree.ElementTree as ET

import requests
import urllib3

from odoo import api, fields, models
from odoo.exceptions import UserError


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ApiRequest(models.Model):
    _name = 'api.request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Our API Request'

    name = fields.Char("Name", required=True)
    url = fields.Char("URL", required=True)
    api_key = fields.Char("API Key")
    action = fields.Boolean("Action", required=True, default=True, store=True, readonly=False)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('no_connection', 'No connection'),
        ('connection', 'Connection'),
    ], string="Status", required=True, default='draft')

    json_code = fields.Html("JSON/XML Code", readonly=True, compute='_compute_api_data', store=True)
    columns_name = fields.Html("Columns Name", readonly=True, compute="_compute_api_data", store=True)

    def _request_headers(self):
        headers = {
            "Accept": "application/json, application/xml, text/xml, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        if self.api_key:
            key = self.api_key.strip()
            headers.update({
                "Authorization": key,
                "X-API-Key": key,
                "X-Auth-Token": key,
                "api-key": key,
                "technician_key": key,
                "authtoken": key,
                "apikey": key,
            })
        return headers

    def _fetch_api_response(self):
        self.ensure_one()
        url = (self.url or '').strip()
        if not url.startswith(('http://', 'https://')):
            raise ValueError("Некорректный URL. Адрес должен начинаться с http:// или https://")
        return requests.get(url, headers=self._request_headers(), timeout=10, verify=False)

    @staticmethod
    def _extract_json_keys(value, path=""):
        keys = set()
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                keys.add(child_path)
                keys.update(ApiRequest._extract_json_keys(child, child_path))
        elif isinstance(value, list):
            for child in value:
                keys.update(ApiRequest._extract_json_keys(child, path))
        return keys

    @staticmethod
    def _extract_xml_keys(element, path=""):
        tag = element.tag.rsplit('}', 1)[-1]
        current_path = f"{path}.{tag}" if path else tag
        keys = {current_path}
        for child in element:
            keys.update(ApiRequest._extract_xml_keys(child, current_path))
        return keys

    def _set_fields_from_response(self, response):
        """Build both displayed fields from the same HTTP response."""
        self.ensure_one()
        content = response.text or "[Пустой ответ от сервера]"

        try:
            data = response.json()
            pretty_json = json.dumps(data, indent=4, ensure_ascii=False)
            self.json_code = f"<pre>{escape(pretty_json[:3000])}</pre>"
            keys = self._extract_json_keys(data)
        except (ValueError, requests.exceptions.JSONDecodeError):
            try:
                root = ET.fromstring(response.content)
                ET.indent(root, space="    ")
                pretty_xml = ET.tostring(root, encoding='unicode')
                self.json_code = f"<pre>{escape(pretty_xml[:3000])}</pre>"
                keys = self._extract_xml_keys(root)
            except ET.ParseError:
                self.json_code = (
                    "<div class='alert alert-warning'>Сервер вернул не JSON и не XML.</div>"
                    f"<pre>{escape(content[:1000])}</pre>"
                )
                keys = set()

        if keys:
            key_rows = ''.join(f"<div>({escape(key)})</div>" for key in sorted(keys))
            self.columns_name = (
                "<div style='font-family: monospace; max-height: 400px; overflow-y: auto;'>"
                f"{key_rows}</div>"
            )
        else:
            self.columns_name = "<p class='text-muted'>Структурированные поля не найдены.</p>"

    @api.depends('url', 'api_key')
    def _compute_api_data(self):
        """Fetch once, then use that response to calculate both fields."""
        for record in self:
            if not record.url:
                record.json_code = "<p class='text-muted'>Укажите URL подключения.</p>"
                record.columns_name = "<p class='text-muted'>Поля появятся после получения ответа.</p>"
                continue
            try:
                response = record._fetch_api_response()
                if response.ok:
                    record._set_fields_from_response(response)
                else:
                    message = f"Ошибка сервера: HTTP {response.status_code}"
                    record.json_code = f"<p class='text-danger'>{escape(message)}</p>"
                    record.columns_name = f"<p class='text-danger'>{escape(message)}</p>"
            except (requests.exceptions.RequestException, ValueError) as error:
                message = escape(str(error))
                record.json_code = f"<p class='text-danger'>Ошибка запроса: {message}</p>"
                record.columns_name = f"<p class='text-danger'>Ошибка запроса: {message}</p>"

    def test_connection(self):
        self.ensure_one()
        url = (self.url or '').strip()
        if not re.match(r'^https?://[^/]+', url):
            self.status = 'no_connection'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Failed',
                    'message': 'Некорректный URL. Используйте формат https://... или http://...',
                    'type': 'danger',
                    'sticky': False,
                },
            }

        try:
            response = self._fetch_api_response()
            response.raise_for_status()
            self.status = 'connection'
            self._set_fields_from_response(response)
        except requests.exceptions.HTTPError as error:
            self.status = 'no_connection'
            response_text = error.response.text[:500] if error.response is not None else ''
            raise UserError(f"Ошибка HTTP: {error}. Ответ сервера: {response_text}") from error
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            self.status = 'no_connection'
            raise UserError(f"Не удалось подключиться к серверу: {error}") from error
        except requests.exceptions.RequestException as error:
            self.status = 'no_connection'
            raise UserError(f"Ошибка запроса: {error}") from error

        return True
