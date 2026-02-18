from odoo import _, http
from odoo.http import request
from odoo.exceptions import ValidationError
from datetime import datetime
import logging
import json

_logger = logging.getLogger(__name__)


class PortalPR(http.Controller):

    @staticmethod
    def _get_default_org_fallbacks():
        icp = request.env["ir.config_parameter"].sudo()

        department_name = "General"
        supervisor_name = "Unassigned Supervisor"
        supervisor_partner_id = ""

        department_id = icp.get_param("custom_user_portal.pr_default_department_id")
        if department_id and str(department_id).isdigit():
            department = request.env["hr.department"].sudo().browse(int(department_id))
            if department.exists() and department.name:
                department_name = department.name

        supervisor_id = icp.get_param("custom_user_portal.pr_default_supervisor_id")
        if supervisor_id and str(supervisor_id).isdigit():
            supervisor = request.env["hr.employee"].sudo().browse(int(supervisor_id))
            if supervisor.exists():
                supervisor_name = supervisor.name or supervisor_name
                if supervisor.user_id and supervisor.user_id.partner_id:
                    supervisor_partner_id = supervisor.user_id.partner_id.id

        return {
            "department": department_name,
            "supervisor": supervisor_name,
            "supervisor_partner_id": supervisor_partner_id,
        }

    # showing page and getting manager name with id
    @http.route("/my/purchase-request/create", type="http", auth="user", website=True)
    def create_purchase_request(self, **kwargs):
        req_type = kwargs.get("type", "pr")
        fallback_values = self._get_default_org_fallbacks()

        user = request.env.user
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", user.id)], limit=1)
        )

        supervisor_name = fallback_values["supervisor"]
        supervisor_partner_id = fallback_values["supervisor_partner_id"]
        if employee and employee.parent_id:
            supervisor = employee.parent_id
            if supervisor.user_id and supervisor.user_id.partner_id:
                supervisor_name = supervisor.user_id.partner_id.name
                supervisor_partner_id = supervisor.user_id.partner_id.id

        seq_code = "cash.purchase.requisition" if req_type == "cash" else "purchase.requisition"
        sequence = request.env["ir.sequence"].sudo().search([("code", "=", seq_code)], limit=1)

        if sequence:
            # Peek the next number, do not consume it
            prefix = sequence.prefix or ""
            next_number = sequence.number_next_actual
            pr_number_preview = f"{prefix}{str(next_number).zfill(sequence.padding)}"
        else:
            pr_number_preview = "New"


        values = {
            "page_name": "create_pr",
            "requested_by": employee.name if employee else user.name,
            "department": (
                employee.department_id.name
                if employee and employee.department_id
                else fallback_values["department"]
            ),
            "supervisor": supervisor_name,
            "supervisor_partner_id": supervisor_partner_id,
            "pr_number_preview": pr_number_preview,
            "req_type": req_type,
        }
        return request.render("custom_user_portal.portal_pr_form_template", values)

    # getting all the products in inventory
    @http.route("/products", auth="public", type="json", website=True)
    def get_all_products(self, **kwargs):
        try:
            products = request.env["product.template"].sudo().search([])
            product_list = [
                {
                    "id": p.id,
                    "name": p.name,
                    "price": p.list_price,
                    "type": p.type,
                }
                for p in products
            ]

            if not product_list:
                product_list = [
                    {"id": 1, "name": "Pieces", "price": 0.0, "type": "consu"},
                    {"id": 2, "name": "Units", "price": 0.0, "type": "consu"},
                    {"id": 3, "name": "Boxes", "price": 0.0, "type": "consu"},
                    {"id": 4, "name": "Kilos", "price": 0.0, "type": "consu"},
                    {"id": 5, "name": "Liters", "price": 0.0, "type": "consu"},
                ]

            return {"products": product_list}
        except Exception as e:
            return {"products": [], "error": str(e)}

    # getting the requested_by user and show all PR on portal
    @http.route("/my/purchase-request", type="http", auth="user", website=True)
    def portal_pr_list(self, **kwargs):
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )

        pr_records = (
            request.env["purchase.requisition"]
            .sudo()
            .search([("requested_by", "=", employee.name)])
        )

        pending_count = sum(1 for pr in pr_records if pr.approval == "pending")
        approved_count = sum(1 for pr in pr_records if pr.approval == "approved")
        rejected_count = sum(1 for pr in pr_records if pr.approval == "rejected")

        return request.render(
            "custom_user_portal.portal_purchase_request_list",
            {
                "prs": pr_records,
                "page_name": "purchase_request",
                "pending_count": pending_count,
                "approved_count": approved_count,
                "rejected_count": rejected_count,
            },
        )

    # budget Check
    @http.route("/check_budget", type="http", auth="user", methods=["POST"], csrf=False)
    def check_budget(self, **post):
        data = json.loads(request.httprequest.data or "{}")
        budget_type = data.get("budget_type")
        budget_code = data.get("budget_code")

        if not budget_type or not budget_code:
            return request.make_response(
                json.dumps(
                    {"success": False, "message": "Missing budget type or budget code."}
                ),
                headers=[("Content-Type", "application/json")],
            )

        budget_status = request.env["purchase.requisition"].sudo().validate_budget_for_amount(
            budget_type,
            budget_code,
            0.0,
        )

        return request.make_response(
            json.dumps(
                {
                    "success": budget_status.get("success"),
                    "budget_left": budget_status.get("budget_left", 0.0),
                    "message": budget_status.get("message"),
                    "source": budget_status.get("source"),
                }
            ),
            headers=[("Content-Type", "application/json")],
        )

    # PR view
    @http.route("/my/purchase_requisition/<int:pr_id>", auth="user", website=True)
    def portal_purchase_requisition_detail(self, pr_id, **kwargs):
        pr = request.env["purchase.requisition"].sudo().browse(pr_id)
        if not pr.exists():
            return request.not_found()
        return request.render(
            "custom_user_portal.portal_purchase_requisition_detail",
            {
                "pr": pr,
                "page_name": "purchase_requisition_detail",
            },
        )

    # Form submission
    @http.route(
        "/my/purchase-request/submit",
        type="http",
        auth="user",
        methods=["POST"],
        csrf=True,
        website=True,
    )
    def submit_purchase_request(self, **post):
        fallback_values = self._get_default_org_fallbacks()
        employee = (
            request.env["hr.employee"]
            .sudo()
            .search([("user_id", "=", request.env.user.id)], limit=1)
        )

        department = post.get("department") or fallback_values["department"]
        supervisor = post.get("supervisor") or fallback_values["supervisor"]
        supervisor_partner_id = (
            post.get("supervisor_partner_id")
            or fallback_values["supervisor_partner_id"]
            or 0
        )

        line_items = []
        index = 1
        subtotal = 0.0
        while f"item_description_{index}" in post:
            item = {
                "description": post.get(f"item_description_{index}"),
                "type": post.get(f"item_type_{index}"),
                "quantity": float(post.get(f"quantity_{index}") or 0),
                "unit": post.get(f"unit_{index}"),
                "unit_price": float(post.get(f"unit_price_{index}") or 0),
            }
            subtotal += item["quantity"] * item["unit_price"]
            line_items.append(item)
            index += 1

        budget_status = request.env["purchase.requisition"].sudo().validate_budget_for_amount(
            post.get("budget_type_selector"),
            post.get("budget_input_field"),
            subtotal,
        )
        if not budget_status.get("success"):
            raise ValidationError(_(budget_status.get("message")))

        requisition = (
            request.env["purchase.requisition"]
            .sudo()
            .create(
                {
                    "requested_by": post.get("requested_by"),
                    "department": department,
                    "supervisor": supervisor,
                    "supervisor_partner_id": int(supervisor_partner_id),
                    "required_date": post.get("required_date"),
                    "priority": post.get("priority"),
                    "budget_type": post.get("budget_type_selector"),
                    "budget_details": post.get("budget_input_field"),
                    "notes": post.get("notes"),
                    "pr_type": post.get("pr_type") or "pr",
                }
            )
        )

        for item in line_items:
            request.env["purchase.requisition.line"].sudo().create(
                {"requisition_id": requisition.id, **item}
            )

        manager = employee.parent_id if employee else False
        current_date = datetime.today().strftime("%Y-%m-%d")

        if manager and manager.work_email:
            line_rows = ""
            subtotal = 0
            for i, item in enumerate(line_items, 1):
                total_price = item["quantity"] * item["unit_price"]
                subtotal += total_price
                line_rows += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{item['description']}</td>
                        <td>{item['type']}</td>
                        <td>{item['quantity']}</td>
                        <td>{item['unit']}</td>
                        <td>{item['unit_price']}</td>
                        <td>{total_price:.2f}</td>
                    </tr>
                """

            vat = subtotal * 0.15
            total = subtotal + vat

        if manager and manager.work_email:
            subject = f"New Purchase Requisition from {employee.name}"
            body_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
                <p>Dear {manager.name},</p>

                <p><strong>{employee.name}</strong> has submitted a new <strong>Purchase Requisition</strong>.</p>
                <p><strong>Date of Request:</strong> {current_date}</p>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr><td><strong>Requested By:</strong></td><td>{post.get('requested_by')}</td></tr>
                    <tr><td><strong>Department:</strong></td><td>{post.get('department')}</td></tr>
                    <tr><td><strong>Supervisor:</strong></td><td>{post.get('supervisor')}</td></tr>
                    <tr><td><strong>Required Date:</strong></td><td>{post.get('required_date')}</td></tr>
                    <tr><td><strong>Priority:</strong></td><td>{post.get('priority')}</td></tr>
                    <tr><td><strong>Budget Type:</strong></td><td>{post.get('budget_type_selector')}</td></tr>
                    <tr><td><strong>Budget Details:</strong></td><td>{post.get('budget_input_field')}</td></tr>
                </table>

                <h4>Requested Items</h4>
                <table style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">
                    <thead>
                        <tr style="background-color: #f2f2f2;">
                            <th style="border: 1px solid #ccc; padding: 8px;">#</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Item</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Type</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Qty</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Unit</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Unit Price</th>
                            <th style="border: 1px solid #ccc; padding: 8px;">Total</th>
                        </tr>
                    </thead>
                    <tbody>{line_rows}</tbody>
                    <tfoot>
                        <tr>
                            <td colspan="6" style="text-align:right; padding: 8px;"><strong>Subtotal</strong></td>
                            <td style="padding: 8px;">{subtotal:.2f}</td>
                        </tr>
                        <tr>
                            <td colspan="6" style="text-align:right; padding: 8px;"><strong>VAT (15%)</strong></td>
                            <td style="padding: 8px;">{vat:.2f}</td>
                        </tr>
                        <tr>
                            <td colspan="6" style="text-align:right; padding: 8px;"><strong>Total</strong></td>
                            <td style="padding: 8px;">{total:.2f}</td>
                        </tr>
                    </tfoot>
                </table>

                <p><strong>Additional Notes:</strong><br/>{post.get('notes') or 'N/A'}</p>

                <p style="margin-top: 20px;">Please log in to Odoo to view and approve the request.</p>
                <p>Best regards,<br/>Odoo Portal</p>
            </div>
            """

            # Send email
            request.env["mail.mail"].sudo().create(
                {
                    "subject": subject,
                    "body_html": body_html,
                    "email_to": manager.work_email,
                    "email_from": request.env.user.email or "noreply@yourcompany.com",
                }
            ).send()

        return request.redirect("/my/purchase-request?pr_submitted=1")

class QuotationPortal(http.Controller):

    @http.route('/custom/quotation/form', type='http', auth='user')
    def quotation_form(self, **kwargs):
        return request.render("custom_user_portal.quotation_form_template", {})
