/* @odoo-module */
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart } from "@odoo/owl";
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
        this.rpc = useService('rpc');
        this.actionService = useService("action");

         onWillStart(async () => {
            await this.userService.hasGroup('hr_holidays.group_hr_holidays_manager').then(hasGroup => {
                this.manager = hasGroup;
            })
    });
}
    async printPdfReport() {
        const duration = $(this.__owl__.bdom.el.querySelectorAll("#duration")).val();
        return this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "de_hr_workspace_leave_management.hr_leave_report",
            report_file: "de_hr_workspace_leave_management.hr_leave_report",
            data: {
                'duration': duration,
                'all_validated_leaves': this.props.all_validated_leaves,
                }
        });
    }
    }
ApprovalStatusCard.template = 'de_hr_workspace_leave_management.ApprovalStatusCard';
ApprovalStatusCard.props = ['id','name','approval_status_count','child_ids',
'children', 'all_validated_leaves'];
