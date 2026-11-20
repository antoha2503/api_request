/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class ApiResponseDashboard extends Component {
    static template = "api_request.ApiResponseDashboard";

    setup() {
        this.state = useState({ requests: [], selectedId: null, loading: true });
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
}

registry.category("actions").add("api_request.response_dashboard", ApiResponseDashboard);
