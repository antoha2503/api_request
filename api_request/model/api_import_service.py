from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class ApiRequestImportService(models.Model):
    _inherit = 'api.request'

    _IMPORTABLE_TYPES = {
        'boolean', 'char', 'date', 'datetime', 'float', 'html', 'integer',
        'monetary', 'selection', 'text',
    }
    _BLOCKED_MODELS = {
        'api.request', 'res.company', 'res.config.settings', 'res.groups', 'res.users',
    }

    @api.model
    def get_import_target_models(self):
        """List business models the current user is allowed to create records in."""
        results = []
        metadata = self.env['ir.model'].sudo().search([], order='name')
        for item in metadata:
            model_name = item.model
            if not model_name or model_name.startswith(('ir.', 'mail.', 'base.', 'api.')):
                continue
            if model_name in self._BLOCKED_MODELS or model_name not in self.env.registry.models:
                continue
            target = self.env[model_name]
            if getattr(target, '_transient', False) or getattr(target, '_abstract', False):
                continue
            try:
                can_create = target.check_access_rights('create', raise_exception=False)
            except AccessError:
                can_create = False
            if can_create:
                results.append({
                    'model': model_name,
                    'label': f"{item.name} ({model_name})",
                })
        return results

    @api.model
    def get_import_target_fields(self, model_name):
        """Return writable scalar fields for a model the user can create in."""
        target = self._get_import_target(model_name)
        field_info = target.fields_get(attributes=['string', 'type', 'required', 'readonly', 'selection'])
        return [
            {
                'name': name,
                'label': description.get('string') or name,
                'type': description.get('type'),
                'required': description.get('required', False),
                'selection': description.get('selection') or [],
            }
            for name, description in field_info.items()
            if name not in {'id', 'create_uid', 'create_date', 'write_uid', 'write_date'}
            and description.get('type') in self._IMPORTABLE_TYPES
            and not description.get('readonly')
        ]

    @api.model
    def import_json_records(self, model_name, records, field_mapping):
        """Create Odoo records from flat JSON objects using the chosen field mapping."""
        target = self._get_import_target(model_name)
        if not isinstance(records, list) or not records:
            raise UserError("В выбранном разделе JSON нет записей для импорта.")
        if len(records) > 5000:
            raise UserError("За один раз можно импортировать не более 5000 записей.")
        if not isinstance(field_mapping, dict) or not field_mapping:
            raise UserError("Сопоставьте хотя бы одно поле JSON с полем целевой модели.")

        allowed_fields = {
            item['name']: item
            for item in self.get_import_target_fields(model_name)
        }
        selected_fields = [
            field_name for field_name in field_mapping.values()
            if field_name
        ]
        if len(selected_fields) != len(set(selected_fields)):
            raise UserError("Одно поле Odoo нельзя сопоставить сразу с несколькими полями JSON.")
        for field_name in selected_fields:
            if field_name not in allowed_fields:
                raise UserError(f"Поле «{field_name}» нельзя заполнять через импорт.")

        values_to_create = []
        for row_number, source_row in enumerate(records, start=1):
            if not isinstance(source_row, dict):
                raise UserError(f"Запись JSON № {row_number} должна быть объектом с полями.")
            values = {}
            for source_key, target_field in field_mapping.items():
                if not target_field or source_key not in source_row:
                    continue
                field_description = allowed_fields[target_field]
                values[target_field] = self._convert_import_value(
                    source_row[source_key], field_description, row_number, source_key
                )
            if not values:
                raise UserError(f"Для записи JSON № {row_number} не выбрано ни одного значения для импорта.")
            values_to_create.append(values)

        # Create in one ORM call so access rules and model constraints stay in force.
        target.create(values_to_create)
        return {'count': len(values_to_create), 'model': model_name}

    @api.model
    def _get_import_target(self, model_name):
        """Validate a requested business model and recheck the user's create access."""
        if not isinstance(model_name, str) or model_name not in self.env.registry.models:
            raise UserError("Выбрана неизвестная модель Odoo.")
        if model_name.startswith(('ir.', 'mail.', 'base.', 'api.')) or model_name in self._BLOCKED_MODELS:
            raise AccessError("Импорт в технические модели Odoo запрещён.")

        target = self.env[model_name]
        if getattr(target, '_transient', False) or getattr(target, '_abstract', False):
            raise AccessError("Импорт в служебные или временные модели Odoo запрещён.")
        target.check_access_rights('create')
        return target

    @api.model
    def _convert_import_value(self, value, field_description, row_number, source_key):
        """Convert JSON scalars to the target field type and reject nested values."""
        field_type = field_description['type']
        if isinstance(value, (dict, list)):
            raise UserError(
                f"Поле «{source_key}» в записи № {row_number} содержит вложенные данные. "
                "Выберите соответствующий вложенный список как источник импорта."
            )
        if value is None:
            return False
        if field_type in {'char', 'text', 'html'}:
            return str(value)
        if field_type == 'boolean':
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {'false', '0', 'no', 'off', ''}:
                    return False
                if normalized in {'true', '1', 'yes', 'on'}:
                    return True
            return bool(value)
        if field_type == 'integer':
            try:
                converted = int(value)
                if isinstance(value, float) and not value.is_integer():
                    raise ValueError
                return converted
            except (TypeError, ValueError):
                raise UserError(f"Значение «{value}» в поле «{source_key}» записи № {row_number} не является целым числом.")
        if field_type in {'float', 'monetary'}:
            try:
                return float(value)
            except (TypeError, ValueError):
                raise UserError(f"Значение «{value}» в поле «{source_key}» записи № {row_number} не является числом.")
        if field_type == 'date':
            try:
                return fields.Date.to_string(fields.Date.to_date(value))
            except (TypeError, ValueError):
                raise UserError(f"Значение «{value}» в поле «{source_key}» записи № {row_number} не является датой.")
        if field_type == 'datetime':
            try:
                parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return fields.Datetime.to_string(parsed)
            except (TypeError, ValueError):
                raise UserError(f"Значение «{value}» в поле «{source_key}» записи № {row_number} не является датой и временем.")
        if field_type == 'selection':
            selection = field_description.get('selection') or []
            allowed_values = {str(key) for key, _label in selection}
            converted = str(value)
            if converted not in allowed_values:
                raise UserError(
                    f"Значение «{value}» не входит в варианты поля «{source_key}» записи № {row_number}."
                )
            return converted
        return value
