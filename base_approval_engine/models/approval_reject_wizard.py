from odoo import fields, models


class ApprovalRejectWizard(models.TransientModel):
    _name = "approval.reject.wizard"
    _description = "Approval Reject Wizard"

    reason = fields.Text(required=True)

    def action_confirm(self):
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        if active_model and active_id:
            record = self.env[active_model].browse(active_id).exists()
            if record and hasattr(record, "action_reject_document"):
                record.action_reject_document(self.reason)
        return {"type": "ir.actions.act_window_close"}
