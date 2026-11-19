from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import xml.etree.ElementTree as ET
import re
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ApiRequest(models.Model):
    _name = 'api.request'
    _description = 'Our API Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char("Name", required=True)
    url = fields.Char("URL", required=True)
    api_key = fields.Char("API Key", required=False)
    action = fields.Boolean("Action", required=True, default=True, store=True, readonly=False)
    status = fields.Selection([('draft','Draft'),
                               ('no_connection','No connection'),
                               ('connection','Connection'),],
                              string="Status", required=True, default='draft' )

    json_code = fields.Html("JSON/XML Code", readonly=True, compute='_compute_json_code')
    columns_name = fields.Html("Columns Name", readonly=True, compute="_compute_col_name")

    @api.depends('url', 'api_key')
    def _compute_json_code(self):
        for record in self:
            record.json_code = "<p style='color: gray;'>Очікування на запис URL...</p>"

            url = str(record.url).strip()
            if not url.startswith(('http://', 'https://')):
                record.json_code = "<p>Некоректний URL</p>"
                continue

            headers = {
                "Accept": "application/json, application/xml, text/xml, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            # ЕСЛИ ПОЛЬЗОВАТЕЛЬ ВВЕЛ КЛЮЧ: добавляем веерную авторизацию
            if record.api_key:
                api_key = str(record.api_key).strip()
                headers.update({
                    "Authorization": api_key,
                    "X-API-Key": api_key,
                    "X-Auth-Token": api_key,
                    "api-key": api_key,
                    "technician_key": api_key,
                    "authtoken": api_key,
                    "apikey": api_key
                })
            try:
                response = requests.get(url=url, headers=headers, timeout=10, verify=False)
                if response.status_code == 200:
                    try:
                        raw_json = response.json()
                        pretty_json = json.dumps(raw_json, indent=4, ensure_ascii=False)
                        record.json_code = pretty_json[:3000]
                    except (requests.exceptions.JSONDecodeError, ValueError):
                        raw_text = response.text if response.text else "[Порожня відповідь від сервера]"
                        record.json_code = f"<div style='background-color: #fff3cd; color: #856404; padding: 10px; border: 1px solid #ffeeba; border-radius: 4px; font-family: monospace;'><p><b>Увага: Сервер повернув не JSON формат!</b></p><pre>{raw_text[:1000]}</pre></div>"

                    try:
                        # Парсим строку в XML-дерево
                        root = ET.fromstring(response.content)
                        # Превращаем обратно в строку, но с красивыми отступами (в Python 3.9+ доступно ET.indent)
                        ET.indent(root, space="    ")
                        pretty_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
                        # Экранируем спецсимволы < и >, чтобы Odoo не посчитала их за HTML-теги!
                        safe_xml = pretty_xml.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        record.json_code = f"<pre style='background-color: #f0f4f8; padding: 10px; border: 1px solid #b3c6ff; border-radius: 4px; font-family: monospace;'>{safe_xml}</pre>"
                        continue
                    except ET.ParseError:
                        pass
                else:
                    record.json_code = f"<p style='color:red;'>Ошибка сервера: {response.status_code}</p>"
                    # ГЛОВЕРНАЯ ЛОВУШКА ДЛЯ СЕТЕВЫХ ОШИБОК (Сюда прилетит NameResolutionError)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as net_err:
                    record.json_code = f"<div style='color: red; background-color: #fde8e8; padding: 10px; border: 1px solid #f8b4b4; border-radius: 4px;'><b>Невірний URL або відсутнє мережеве з'єднання!</b><br/><small>{str(net_err)}</small></div>"

                # Ловушка для любых других непредвиденных сбоев
            except Exception as e:
                record.json_code = f"<p style='color:orange;'>Помилка запиту: {str(e)}</p>"

    @api.depends('url', 'api_key')
    def _compute_col_name(self):
        for record in self:
            record.columns_name = "<p style='color: gray;'>Очікування налаштувань URL...</p>"

            # ШАГ 2: Делаем проверки
            if not record.url:
                continue

            url = str(record.url).strip()
            if not url.startswith(('http://', 'https://')):
                record.columns_name = "<p style='color: red;'>Некоректний URL</p>"
                continue

            headers = {
                "Accept": "application/json, application/xml, text/xml, */*",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            if record.api_key:
                headers.update({
                    "Authorization": str(record.api_key).strip(),
                    "X-API-Key": str(record.api_key).strip(),
                    "X-Auth-Token": str(record.api_key).strip(),
                    "authtoken": str(record.api_key).strip(),
                    "apikey": str(record.api_key).strip(),
                    "api-key": str(record.api_key).strip(),
                    "technician_key": str(record.api_key).strip()
                })
            try:
                response = requests.get(url=url, headers=headers, timeout=10, verify=False)

                all_keys = set()
                # Внутренняя рекурсивная функция для сканирования JSON
                def extract_keys_json(data, current_path=""):
                    # Ситуация 1: Элемент является словарем (dict)
                    if isinstance(data, dict):
                        for key, value in data.items():
                            # Формируем путь через точку, например: requests.requester
                            new_path = f"{current_path}.{key}" if current_path else key
                            all_keys.add(new_path)
                            # Рекурсивно идем глубже
                            extract_keys_json(value, new_path)
                    # Ситуация 2: Элемент является списком (list)
                    elif isinstance(data, list):
                        for item in data:
                            # Сканируем объекты внутри списка (не меняя путь, так как индекс [0] нам в названии не нужен)
                            extract_keys_json(item, current_path)

                # Внутренняя рекурсивная функция для сканирования XML
                def extract_keys_xml(element, current_path=""):
                    tag_name = element.tag
                    if '}' in tag_name:
                        tag_name = tag_name.split('}', 1)[1]
                    # Формируем чистый путь через точку
                    new_path = f"{current_path}.{tag_name}" if current_path else tag_name
                    all_keys.add(new_path)
                    # Перебираем все дочерние подтеги (вложенность)
                    for child in element:
                        extract_keys_xml(child, new_path)

                # Запускаем рекурсию передав туда корневой JSON
                # Проверяем, что именно нам прилетело, и запускаем нужный обходчик
                try:
                    # Пробуем как JSON
                    json_data = response.json()
                    extract_keys_json(json_data)
                except (requests.exceptions.JSONDecodeError, ValueError):
                    try:
                        # Пробуем как XML
                        xml_root = ET.fromstring(response.content)
                        extract_keys_xml(xml_root)
                    except ET.ParseError:
                        # Если вообще не поддается парсингу
                        record.columns_name = "<p style='color:orange;'>Текст відповіді не містить структурних колонок (не JSON і не XML)</p>"

                # Сортируем ключи по алфавиту для красоты
                sorted_keys = sorted(list(all_keys))

                # Формируем красивый HTML-вывод со списком
                html_result = "<div style='font-family: monospace; background-color: #fafafa; padding: 10px; border: 1px solid #eee; border-radius: 4px; max-height: 400px; overflow-y: auto;'>"
                for k in sorted_keys:
                    # Считаем количество точек, чтобы сделать визуальный отступ для вложенных элементов
                    dots_count = k.count('.')
                    padding = dots_count * 15  # 15px отступа за каждый уровень вложенности

                    # Подсвечиваем самый глубокий элемент или выводим путь целиком
                    display_name = k.split('.')[-1] if dots_count > 0 else k
                    prefix = "└─ " if dots_count > 0 else "• "

                    # html_result += f"<div style='padding-left: {padding}px; color: {'#2980b9' if dots_count > 0 else '#2c3e50'};'><b>{prefix}<label><input type='radio' name='{display_name}'>{display_name}</label></b> <span style='color: #aaa; font-size: 0.85em;'>{k}</span></div>"
                    html_result +=f"<div><span style='color: #aaa; font-size: 0.85em;'>({k})</span></div>"
                html_result += "</div>"
                record.columns_name = html_result

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as net_err:
                record.columns_name = f"<div style='color: red; background-color: #fde8e8; padding: 10px; border: 1px solid #f8b4b4; border-radius: 4px;'><b>Невірний URL або відсутнє мережеве з'єднання!</b><br/><small>{str(net_err)}</small></div>"

            # Ловушка для любых других непредвиденных сбоев
            except Exception as e:
                record.columns_name = f"<p style='color:orange;'>Помилка запиту: {str(e)}</p>"


    def test_connection(self):
        url = str(self.url).strip()
        result_re = re.search(r'(https?://[a-zA-Z0-9:_-]+)', url)

        if not result_re:
            self.status = 'no_connection'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Failed',
                    'message': 'It is not url. Format https://(http://....)',
                    'type': 'danger',
                    'sticky': False,
                }
            }
        else:
            self.status = 'connection'

        headers = {
            "Accept": "application/json, application/xml, text/xml, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # ЕСЛИ ПОЛЬЗОВАТЕЛЬ ВВЕЛ КЛЮЧ: добавляем веерную авторизацию
        if self.api_key:
            api_key = str(self.api_key).strip()
            headers.update({
                "Authorization": api_key,
                "X-API-Key": api_key,
                "X-Auth-Token": api_key,
                "authtoken": api_key,
                "api-key": api_key,
                "technician_key": api_key,
                "apikey": api_key
            })
        try:
            response = requests.get(url=url, headers=headers, timeout=10, verify=False)
            response.raise_for_status()
            self.status = 'connection'

            raw_text = response.text if response.text else "[Порожня відповідь від сервера]"
            self.json_code = f"<div style='background-color: #fff3cd; color: #856404; padding: 10px; border: 1px solid #ffeeba; border-radius: 4px; font-family: monospace;'><p><b>Увага: Сервер повернув не JSON формат!</b></p><pre>{raw_text[:1000]}</pre></div>"
            # self.json_code = response.text

        except requests.exceptions.HTTPError as http_err:
            self.status = 'no_connection'
            server_response = response.text[:500]
            raise UserError(f"Помилка HTTP {http_err.response.status_code}. Відповідь сервера: {str(server_response)}")

        except ET.ParseError:
            # Если вообще не поддается парсингу
            self.status = 'no_connection'
            self.columns_name = "<p style='color:orange;'>Текст відповіді не містить структурних колонок (не JSON і не XML)</p>"

        except requests.exceptions.ConnectionError as connection_err:
            self.status = 'no_connection'
            self.columns_name = f"неверный URL - {connection_err}"

        except Exception as e:
            self.status = 'no_connection'
            raise UserError(f"Помилка з'єднання: {str(e)}")

