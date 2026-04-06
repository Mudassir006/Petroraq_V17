/* @odoo-module */
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
export class TimeOffEmpCard extends Component {}
TimeOffEmpCard.template = 'de_hr_workspace_leave_management.TimeOffEmpCard';
TimeOffEmpCard.props = ['name', 'id', 'department_id', 'job_position',
'children', 'image_1920', 'work_email', 'work_phone', 'company', 'resource_calendar_id'];
//Exports a class TimeOffEmpOrgChart that extends the Component class.
//It is a custom component used for managing an employee organization
//chart in the context of time off and holidays.
export class TimeOffEmpOrgChart extends Component {
    setup() {
         super.setup();
        this.props;
        this.userService = useService('user');
          onWillStart(async () => {
            this.manager = await this.userService.hasGroup("hr_holidays.group_hr_holidays_manager");
        });

    }
}
TimeOffEmpOrgChart.template = 'de_hr_workspace_leave_management.hr_org_chart';
TimeOffEmpOrgChart.props = ['name', 'id', 'department_id', 'job_position', 'children'];
export class EmpDepartmentCard extends Component {}
EmpDepartmentCard.template = 'de_hr_workspace_leave_management.EmpDepartmentCard';
EmpDepartmentCard.props = ['name', 'id', 'department_id', 'child_all_count',
'children', 'absentees', 'current_shift', 'upcoming_holidays'];
//Exports a class ApprovalStatusCard that extends the Component class.
//It is a custom component used for managing the approval status of
//a card, possibly related to HR leave requests.
export class ApprovalStatusCard extends Component {
        setup() {
         super.setup();
          this.userService = useService('user');
        this.props;

         onWillStart(async () => {
            await this.userService.hasGroup('hr_holidays.group_hr_holidays_manager').then(hasGroup => {
                this.manager = hasGroup;
            })
    });
}
}
ApprovalStatusCard.template = 'de_hr_workspace_leave_management.ApprovalStatusCard';
ApprovalStatusCard.props = ['id','name','approval_status_count','child_ids',
'children', 'all_validated_leaves'];

export class PeriodAbsenteesCard extends Component {
    setup() {
        super.setup();
        this.orm = useService('orm');
        this.actionService = useService("action");
        this.state = useState({
            duration: 'this_month',
            rows: [],
        });
        onWillStart(async () => {
            await this.loadRows();
        });
    }

    async loadRows() {
        const rows = await this.orm.call(
            'hr.leave',
            'get_period_absentees',
            [this.state.duration],
            {
                context: {
                    employee_id: this.props.id,
                    show_all_leave_dashboard: true,
                },
            }
        );
        this.state.rows = rows.map((row, index) => ({ ...row, row_key: `${row.employee_id || 0}-${index}` }));
    }

    async onChangeDuration(ev) {
        this.state.duration = ev.target.value;
        await this.loadRows();
    }

    exportPdf() {
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "de_hr_workspace_leave_management.period_absentees_pdf",
            report_file: "de_hr_workspace_leave_management.period_absentees_pdf",
            data: {
                duration: this.state.duration,
            },
        });
    }

    exportXlsx() {
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "xlsx",
            report_name: "de_hr_workspace_leave_management.period_absentees_xlsx",
            report_file: "period_absentees",
            data: {
                duration: this.state.duration,
            },
        });
    }
}
PeriodAbsenteesCard.template = 'de_hr_workspace_leave_management.PeriodAbsenteesCard';
PeriodAbsenteesCard.props = ['id'];

export class PeriodLeavesCard extends Component {
    setup() {
        super.setup();
        this.orm = useService('orm');
        this.actionService = useService("action");
        this.state = useState({
            duration: 'this_month',
            rows: [],
        });
        onWillStart(async () => {
            await this.loadRows();
        });
    }

    async loadRows() {
        const rows = await this.orm.call('hr.leave', 'get_period_leaves', [this.state.duration], {
            context: { employee_id: this.props.id, show_all_leave_dashboard: true },
        });
        this.state.rows = rows.map((row, index) => ({ ...row, row_key: `${row.employee_id || 0}-${index}` }));
    }

    async onChangeDuration(ev) {
        this.state.duration = ev.target.value;
        await this.loadRows();
    }

    exportPdf() {
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "de_hr_workspace_leave_management.period_absentees_pdf",
            report_file: "de_hr_workspace_leave_management.period_absentees_pdf",
            data: { duration: this.state.duration },
        });
    }

    exportXlsx() {
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "xlsx",
            report_name: "de_hr_workspace_leave_management.period_absentees_xlsx",
            report_file: "period_absentees",
            data: { duration: this.state.duration },
        });
    }
}
PeriodLeavesCard.template = 'de_hr_workspace_leave_management.PeriodLeavesCard';
PeriodLeavesCard.props = ['id'];

export class LeaveTypeMetricsCard extends Component {
    setup() {
        super.setup();
        this.orm = useService('orm');
        this.state = useState({
            duration: 'this_month',
            rows: [],
        });
        onWillStart(async () => {
            await this.loadRows();
        });
    }

    async loadRows() {
        this.state.rows = await this.orm.call('hr.leave', 'get_period_leave_type_metrics', [this.state.duration], {
            context: { employee_id: this.props.id, show_all_leave_dashboard: true },
        });
    }

    async onChangeDuration(ev) {
        this.state.duration = ev.target.value;
        await this.loadRows();
    }
}
LeaveTypeMetricsCard.template = 'de_hr_workspace_leave_management.LeaveTypeMetricsCard';
LeaveTypeMetricsCard.props = ['id'];
