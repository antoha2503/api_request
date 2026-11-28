/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

// Отдельный компонент отображает вложенные объекты и списки как раскрываемые таблицы.
class JsonValueTable extends Component {
    static template = "api_request.JsonValueTable";
    // Шаблон всегда передаёт value; null и undefined обрабатываются компонентом отдельно.
    static props = ["value"];

    setup() {
        this.state = useState({ expanded: false });
    }

    get isStructured() {
        return this.props.value !== null && typeof this.props.value === "object";
    }

    // Показывает простые значения напрямую, а null — как пустое значение.
    get displayValue() {
        return this.props.value === null || this.props.value === undefined
            ? "—"
            : String(this.props.value);
    }

    get toggleLabel() {
        const count = Array.isArray(this.props.value)
            ? this.props.value.length
            : Object.keys(this.props.value || {}).length;
        const type = Array.isArray(this.props.value) ? "Список" : "Объект";
        return `${this.state.expanded ? "Скрыть" : "Показать"} ${type.toLowerCase()} (${count})`;
    }

    // Подготавливает строки вложенного списка или пары «поле — значение» объекта.
    get tableData() {
        const value = this.props.value;
        if (Array.isArray(value)) {
            const objectRows = value.filter(
                (item) => item !== null && typeof item === "object" && !Array.isArray(item)
            );
            if (objectRows.length === value.length && objectRows.length > 0) {
                const columns = [...new Set(objectRows.flatMap((item) => Object.keys(item)))];
                if (columns.length) {
                    return { columns, rows: objectRows.map((item) => columns.map((key) => item[key])) };
                }
                return {
                    columns: ["Значение"],
                    rows: objectRows.map((item) => [JSON.stringify(item)]),
                };
            }
            return { columns: ["Значение"], rows: value.map((item) => [item]) };
        }
        return {
            columns: ["Поле", "Значение"],
            rows: Object.entries(value || {}).map(([key, item]) => [key, item]),
        };
    }

    // Переключает отображение вложенной таблицы в ячейке.
    toggleExpanded() {
        this.state.expanded = !this.state.expanded;
    }
}

class ApiResponseDashboard extends Component {
    static template = "api_request.ApiResponseDashboard";

    setup() {
        // Состояние хранит список API, выбранное подключение и активную вкладку.
        this.state = useState({
            requests: [], selectedId: null, loading: true, copied: false, activeTab: "table",
            importOpen: false, importLoading: false, importModels: [], importFields: [],
            importSources: [], importSource: "", importModel: "", importMappings: [],
            importModelSearch: "", importModelDropdownOpen: false,
            importError: "", importing: false,
        });
        this.orm = this.env.services.orm;
        this.notification = this.env.services.notification;
        onWillStart(async () => {
            this.state.requests = await this.orm.searchRead(
                "api.request",
                [["action", "=", true], ["status", "=", "connection"]],
                ["name", "json_code"],
                { order: "name" }
            );
            this.state.selectedId = this.state.requests[0]?.id || null;
            this.state.loading = false;
        });
    }

    get selectedRequest() {
        return this.state.requests.find((request) => request.id === this.state.selectedId);
    }

    // Убирает HTML-обертку поля Odoo и возвращает сам текст ответа сервера.
    get responseText() {
        const html = this.selectedRequest?.json_code || "";
        const document = new DOMParser().parseFromString(html, "text/html");
        return document.body.textContent || html;
    }

    // Пробует разобрать ответ как JSON; для XML и обычного текста возвращает признак ошибки.
    get parsedResponse() {
        try {
            return { isJson: true, value: JSON.parse(this.responseText) };
        } catch {
            return { isJson: false, value: null };
        }
    }

    // Преобразует объект или массив JSON в колонки и строки для вкладки «Таблица».
    get tableData() {
        const parsed = this.parsedResponse;
        if (!parsed.isJson) {
            return null;
        }

        const value = parsed.value;
        if (Array.isArray(value)) {
            const objectRows = value.filter(
                (item) => item !== null && typeof item === "object" && !Array.isArray(item)
            );
            if (objectRows.length === value.length && objectRows.length > 0) {
                const columns = [...new Set(objectRows.flatMap((item) => Object.keys(item)))];
                if (!columns.length) {
                    return {
                        columns: ["Значение"],
                        rows: objectRows.map((item) => [JSON.stringify(item)]),
                    };
                }
                return {
                    columns,
                    rows: objectRows.map((item) => columns.map((column) => item[column])),
                };
            }
            return {
                columns: ["Значение"],
                rows: value.map((item) => [item]),
            };
        }

        if (value !== null && typeof value === "object") {
            return {
                columns: ["Поле", "Значение"],
                rows: Object.entries(value).map(([key, item]) => [key, item]),
            };
        }

        return { columns: ["Ответ"], rows: [[value]] };
    }

    // Форматирует JSON отступами, а остальные ответы оставляет без изменений.
    get displayCode() {
        const parsed = this.parsedResponse;
        return parsed.isJson ? JSON.stringify(parsed.value, null, 4) : this.responseText;
    }

    // Находит корневые записи и вложенные списки объектов, которые можно импортировать отдельно.
    getImportSources() {
        const parsed = this.parsedResponse;
        if (!parsed.isJson) {
            return [];
        }
        const data = parsed.value;
        const rootRows = Array.isArray(data) ? data : (data && typeof data === "object" ? [data] : []);
        const sources = [];
        const sourceByPath = new Map();
        if (rootRows.length && rootRows.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
            sources.push({ path: "", label: `Основной JSON (${rootRows.length} записей)`, rows: rootRows });
            sourceByPath.set("", sources[0]);
        }

        const visit = (value, path) => {
            if (Array.isArray(value)) {
                if (path && value.length && value.every(
                    (item) => item && typeof item === "object" && !Array.isArray(item)
                )) {
                    const source = sourceByPath.get(path);
                    if (source) {
                        for (const row of value) {
                            source.rows.push(row);
                        }
                    } else {
                        const nestedSource = { path, label: `${path} (${value.length} записей)`, rows: [...value] };
                        sourceByPath.set(path, nestedSource);
                        sources.push(nestedSource);
                    }
                }
                for (const item of value) {
                    if (item && typeof item === "object") {
                        visit(item, path);
                    }
                }
            } else if (value && typeof value === "object") {
                for (const [key, child] of Object.entries(value)) {
                    visit(child, path ? `${path}.${key}` : key);
                }
            }
        };
        visit(data, "");
        return sources;
    }

    // Возвращает записи выбранного корневого или вложенного JSON-списка.
    get importRows() {
        return this.state.importSources.find((source) => source.path === this.state.importSource)?.rows || [];
    }

    // Автоматически подбирает поля Odoo с теми же именами и отмечает вложенные значения.
    rebuildImportMappings() {
        const sourceKeys = [...new Set(this.importRows.flatMap((row) => Object.keys(row)))];
        this.state.importMappings = sourceKeys.map((sourceKey) => {
            const isStructured = this.importRows.some(
                (row) => row[sourceKey] !== null && typeof row[sourceKey] === "object"
            );
            const matchingField = this.state.importFields.find((field) => field.name === sourceKey);
            return {
                sourceKey,
                isStructured,
                targetField: isStructured ? "" : (matchingField?.name || ""),
            };
        });
    }

    // Загружает доступные цели импорта и открывает окно настройки сопоставлений.
    async openImport() {
        this.state.importOpen = true;
        this.state.importLoading = true;
        this.state.importError = "";
        this.state.importModel = "";
        this.state.importModelSearch = "";
        this.state.importModelDropdownOpen = false;
        this.state.importModels = [];
        this.state.importFields = [];
        this.state.importMappings = [];
        this.state.importSources = this.getImportSources();
        this.state.importSource = this.state.importSources[0]?.path || "";
        try {
            this.state.importModels = await this.orm.call(
                "api.request", "get_import_target_models", []
            );
            if (!this.state.importSources.length) {
                this.state.importError = "В ответе нет списка JSON-объектов для импорта.";
            } else if (!this.state.importModels.length) {
                this.state.importError = "Нет доступных моделей, в которые у вас есть право создавать записи.";
            }
        } catch (error) {
            this.state.importError = error.data?.message || error.message || "Не удалось загрузить список моделей Odoo.";
        } finally {
            this.state.importLoading = false;
        }
    }

    // Открывает варианты моделей, когда пользователь переходит к полю поиска.
    onImportModelFocus() {
        this.state.importModelDropdownOpen = true;
    }

    // Фильтрует модели по введённому тексту и сбрасывает старый выбор при редактировании.
    onImportModelSearch(event) {
        this.state.importModelSearch = event.target.value;
        this.state.importModel = "";
        this.state.importFields = [];
        this.state.importMappings = [];
        this.state.importError = "";
        this.state.importModelDropdownOpen = true;
    }

    // Передаёт выбранную модель в загрузчик полей с контекстом компонента.
    onImportModelOptionClick(event) {
        return this.selectImportModel(event.currentTarget.dataset.modelName);
    }

    // Загружает доступные поля выбранной модели и подготавливает автоматические соответствия.
    async selectImportModel(modelName) {
        const model = this.state.importModels.find((item) => item.model === modelName);
        if (!model) {
            return;
        }
        this.state.importModel = model.model;
        this.state.importModelSearch = model.label;
        this.state.importModelDropdownOpen = false;
        this.state.importFields = [];
        this.state.importMappings = [];
        this.state.importError = "";
        this.state.importLoading = true;
        try {
            this.state.importFields = await this.orm.call(
                "api.request", "get_import_target_fields", [model.model]
            );
            this.rebuildImportMappings();
        } catch (error) {
            this.state.importError = error.data?.message || error.message || "Не удалось загрузить поля модели.";
        } finally {
            this.state.importLoading = false;
        }
    }

    // Пересобирает список ключей при выборе другого массива в исходном JSON.
    onImportSourceChange(event) {
        this.state.importSource = event.target.value;
        this.rebuildImportMappings();
    }

    // Сохраняет выбранное пользователем соответствие одного JSON-ключа полю Odoo.
    onImportMappingChange(event) {
        const mapping = this.state.importMappings.find(
            (item) => item.sourceKey === event.target.dataset.sourceKey
        );
        if (mapping) {
            mapping.targetField = event.target.value;
        }
    }

    // Разрешает запуск только когда выбрана цель и задано хотя бы одно поле.
    get canImport() {
        return Boolean(
            this.state.importModel &&
            this.importRows.length &&
            this.state.importMappings.some((mapping) => mapping.targetField && !mapping.isStructured)
        );
    }

    // Фильтрует список доступных целей по названию модели или её техническому имени.
    get filteredImportModels() {
        const query = this.state.importModelSearch.trim().toLowerCase();
        return this.state.importModels
            .filter((model) => !query || `${model.label} ${model.model}`.toLowerCase().includes(query))
            .slice(0, 100);
    }

    // Показывает подсказку, если источник содержит вложенные объекты или списки.
    get hasStructuredMappings() {
        return this.state.importMappings.some((item) => item.isStructured);
    }

    // Отправляет выбранные JSON-строки и сопоставления в Odoo для создания записей.
    async importJsonData() {
        if (!this.canImport || this.state.importing) {
            return;
        }
        this.state.importing = true;
        this.state.importError = "";
        const mapping = Object.fromEntries(
            this.state.importMappings
                .filter((item) => item.targetField && !item.isStructured)
                .map((item) => [item.sourceKey, item.targetField])
        );
        try {
            const result = await this.orm.call(
                "api.request",
                "import_json_records",
                [this.state.importModel, this.importRows, mapping]
            );
            this.notification.add(`Импортировано записей: ${result.count}`, { type: "success" });
            this.closeImport();
        } catch (error) {
            this.state.importError = error.data?.message || error.message || "Импорт завершился с ошибкой.";
        } finally {
            this.state.importing = false;
        }
    }

    // Закрывает окно импорта и очищает его временное состояние.
    closeImport() {
        this.state.importOpen = false;
        this.state.importError = "";
    }

    onRequestChange(event) {
        this.state.selectedId = Number(event.target.value) || null;
        this.state.copied = false;
        this.state.activeTab = "table";
    }

    async copyCode() {
        const text = this.displayCode;
        try {
            await navigator.clipboard.writeText(text);
        } catch {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            textarea.remove();
        }
        this.state.copied = true;
        window.setTimeout(() => { this.state.copied = false; }, 1800);
    }

    // Запускает скачивание XLSX-файла для выбранного JSON-ответа.
    exportExcel() {
        if (!this.selectedRequest || !this.tableData) {
            return;
        }
        const query = new URLSearchParams({ request_id: String(this.selectedRequest.id) });
        window.location.href = `/api_request/export_xlsx?${query.toString()}`;
    }
}

// Регистрируем компонент ячейки для вложенного отображения и для основной таблицы.
JsonValueTable.components = { JsonValueTable };
ApiResponseDashboard.components = { JsonValueTable };

registry.category("actions").add("api_request.response_dashboard", ApiResponseDashboard);
