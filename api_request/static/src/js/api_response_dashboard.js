/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class ApiResponseDashboard extends Component {
    static template = "api_request.ApiResponseDashboard";

    setup() {
        // Состояние хранит список API, выбранное подключение и активную вкладку.
        this.state = useState({
            requests: [], selectedId: null, loading: true, copied: false, activeTab: "table",
        });
        this.orm = this.env.services.orm;
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
                    rows: objectRows.map((item) =>
                        columns.map((column) => this.formatCell(item[column]))
                    ),
                };
            }
            return {
                columns: ["Значение"],
                rows: value.map((item) => [this.formatCell(item)]),
            };
        }

        if (value !== null && typeof value === "object") {
            return {
                columns: ["Поле", "Значение"],
                rows: Object.entries(value).map(([key, item]) => [key, this.formatCell(item)]),
            };
        }

        return { columns: ["Ответ"], rows: [[this.formatCell(value)]] };
    }

    // Делает вложенные значения JSON читаемыми ячейками таблицы.
    formatCell(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return typeof value === "object" ? JSON.stringify(value) : String(value);
    }

    // Форматирует JSON отступами, а остальные ответы оставляет без изменений.
    get displayCode() {
        const parsed = this.parsedResponse;
        return parsed.isJson ? JSON.stringify(parsed.value, null, 4) : this.responseText;
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

registry.category("actions").add("api_request.response_dashboard", ApiResponseDashboard);
