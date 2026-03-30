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
            ["#1C77C3", "#39A9DB"],
            ["#5AA9E6", "#7FC8F8"],
            ["#A0D2DB", "#BEE7E8"],
            ["#838791", "#AAC0AF"],
            ["#D3FAD6", "#D1EFB5"],
            ["#F7E3AF", "#F3EEC3"],
            ["#227C9D", "#17C3B2"],
            ["#0B4F6E", "#145C9E"],
            ["#EFECCA", "#A9CBB7"],
            ["#1E3888", "#47A8BD"],
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