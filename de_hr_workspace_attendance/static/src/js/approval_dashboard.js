/** @odoo-module */

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

class ApprovalDashboard extends Component {
    static template = "de_hr_workspace_attendance.ApprovalDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            tiles: [],
            loading: true,
            userName: session.user_name || session.name || session.username || "",
        });

        onWillStart(async () => {
            await this.loadTiles();
        });
    }

    async loadTiles() {
        this.state.loading = true;
        const tiles = await this.orm.call("de.hr.approval.dashboard.service", "get_tiles", []);
        this.state.tiles = tiles.map((tile) => ({ ...tile, gradient: this.randomGradient() }));
        this.state.loading = false;
    }

    openTile(ev) {
        const actionId = Number(ev.currentTarget.dataset.actionId || 0);
        if (actionId) {
            this.action.doAction(actionId);
        }
    }

    async refresh() {
        await this.loadTiles();
    }


    get salutation() {
        const hour = new Date().getHours();
        if (hour < 12) {
            return "Good Morning";
        }
        if (hour < 17) {
            return "Good Afternoon";
        }
        return "Good Evening";
    }

    get greetingText() {
        const name = (this.state.userName || "").trim();
        return name ? `${this.salutation}, Mr. ${name}` : this.salutation;
    }


    randomGradient() {
        const gradients = [
            ["#1d4ed8", "#2563eb"],
            ["#0f766e", "#14b8a6"],
            ["#7c3aed", "#a855f7"],
            ["#be123c", "#e11d48"],
            ["#ea580c", "#f97316"],
            ["#0369a1", "#0ea5e9"],
            ["#166534", "#22c55e"],
            ["#4338ca", "#6366f1"],
            ["#b45309", "#f59e0b"],
            ["#0f172a", "#334155"],
        ];
        const [fromColor, toColor] = gradients[Math.floor(Math.random() * gradients.length)];
        return `linear-gradient(135deg, ${fromColor}, ${toColor})`;
    }

    tileStyle(tile) {
        return tile.gradient ? `background: ${tile.gradient};` : "";
    }

    tileClass(tile) {
        return `de-dashboard-tile de-dashboard-tile-${tile.tone || "primary"}`;
    }
}

registry.category("actions").add("de_hr_workspace_attendance.approval_dashboard", ApprovalDashboard);
