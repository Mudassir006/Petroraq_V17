from odoo import api, models


class ApprovalInterceptor(models.AbstractModel):
    _name = "approval.interceptor"
    _description = "Approval Method Interceptor"

    @api.model
    def _register_hook(self):
        result = super()._register_hook()
        if getattr(api, "_approval_engine_wrapped", False):
            return result

        original_call_kw = api.call_kw

        def call_kw_with_approval(model, method, args, kwargs):
            kwargs = kwargs or {}
            context = model.env.context
            if not context.get("bypass_approval_enforcement"):
                protected = not method.startswith("_") and model._name not in {
                    "approval.workflow",
                    "approval.workflow.line",
                    "approval.request",
                    "approval.request.line",
                    "approval.reject.wizard",
                    "approval.enforcement.rule",
                }
                if protected:
                    records = model
                    if args and isinstance(args[0], list) and args[0] and all(isinstance(x, int) for x in args[0]):
                        records = model.browse(args[0])
                    if records and records.exists():
                        model.env["approval.enforcement.rule"].check_method_call(records, method)
            return original_call_kw(model, method, args, kwargs)

        api.call_kw = call_kw_with_approval
        api._approval_engine_wrapped = True
        return result
