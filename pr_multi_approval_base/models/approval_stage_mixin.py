from odoo import models


class ApprovalStageMixin(models.AbstractModel):
    _name = "approval.stage.mixin"
    _description = "Reusable Multi-Stage Approval Helpers"

    def _approval_get_stages(self):
        """Return ordered approval stage dictionaries for the current record.

        Expected stage keys:
          - key: unique stage key (e.g. 'pm')
          - field: boolean field storing completion
          - group: XMLID of approver group for the stage
          - label: human-readable stage label for chatter messages
        """
        self.ensure_one()
        return []

    def _approval_get_pending_stage_index(self, stages):
        self.ensure_one()
        for idx, stage in enumerate(stages):
            if not getattr(self, stage["field"]):
                return idx
        return False

    def _approval_get_last_consecutive_stage_index(self, stages, start_idx, user):
        self.ensure_one()
        last_idx = start_idx
        next_idx = start_idx + 1
        while next_idx < len(stages):
            stage = stages[next_idx]
            if stage.get("state"):
                can_approve = self._approval_is_user_allowed_for_state_stage(stage, user)
            else:
                can_approve = user.has_group(stage["group"])
            if can_approve:
                last_idx = next_idx
                next_idx += 1
                continue
            break
        return last_idx

    def _approval_get_visible_stage(self, stages, user):
        """Return the stage that should be shown/actioned for the current user."""
        self.ensure_one()
        pending_idx = self._approval_get_pending_stage_index(stages)
        if pending_idx is False:
            return False
        if not user.has_group(stages[pending_idx]["group"]):
            return False
        last_idx = self._approval_get_last_consecutive_stage_index(stages, pending_idx, user)
        return stages[last_idx]

    # State-driven helpers (for workflows like draft -> to_manager -> to_md -> approved)
    def _approval_get_state_stages(self):
        """Return ordered state-approval stages.

        Expected stage keys:
          - state: the current waiting state for this stage (e.g. 'to_manager')
          - group: XMLID of approver group for the stage
          - next_state: state after approval for this stage
          - label: human-readable stage label for chatter messages (optional)
        """
        self.ensure_one()
        return []

    def _approval_get_state_field_name(self):
        self.ensure_one()
        return "approval_state"

    def _approval_get_state_stage_index(self, stages, state_value):
        self.ensure_one()
        for idx, stage in enumerate(stages):
            if stage["state"] == state_value:
                return idx
        return False

    def _approval_is_user_allowed_for_state_stage(self, stage, user):
        self.ensure_one()
        group_xmlid = stage.get("group")
        return bool(group_xmlid and user.has_group(group_xmlid))

    def _approval_get_visible_state_stage(self, stages, user, state_field=None):
        self.ensure_one()
        state_field = state_field or self._approval_get_state_field_name()
        current_state = self[state_field]
        idx = self._approval_get_state_stage_index(stages, current_state)
        if idx is False:
            return False
        if not self._approval_is_user_allowed_for_state_stage(stages[idx], user):
            return False
        last_idx = self._approval_get_last_consecutive_stage_index(stages, idx, user)
        return stages[last_idx]
