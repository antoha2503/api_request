/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class ApiResponseDashboard extends Component {
    static template = "api_request.ApiResponseDashboard";

    setup() {
        this.state = useState({ requests: [], selectedId: null, loading: true, copied: false });
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

    get displayCode() {
        const html = this.selectedRequest?.json_code || "";
        const document = new DOMParser().parseFromString(html, "text/html");
        const responseText = document.body.textContent || html;
        try {
            return JSON.stringify(JSON.parse(responseText), null, 4);
        } catch {
            return responseText;
        }
    }

    onRequestChange(event) {
        this.state.selectedId = Number(event.target.value) || null;
        this.state.copied = false;
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
}

registry.category("actions").add("api_request.response_dashboard", ApiResponseDashboard);
