from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class CustomPR(models.Model):
    _name = 'custom.pr'
    _description = 'Custom Purchase Requisition'

    name = fields.Char(string="PR Number", readonly=True, copy=False)
    pr_type = fields.Selection(
        [('standard', 'PR'), ('cash', 'Cash PR')],
        string="Type",
        default='standard',
        required=True,
    )
    requested_by = fields.Char(string="Requested By")
    requested_user_id = fields.Many2one('res.users', string="Requested User", readonly=True)
    date_request = fields.Datetime(string="Request Date", default=fields.Datetime.now, required=True, readonly=True)
    description = fields.Text(string="Description")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="supervisor_partner_id")
    required_date = fields.Date(string="Required Date", required=True, readonly=True)
    priority = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
        string="Priority",
        required=True,
        default="medium",
    )
    cost_center_id = fields.Many2one(
        'account.analytic.account',
        string="Cost Center",
        required=True,
    )
    comments = fields.Text(string="Comments")
    notes = fields.Text(string="Notes")
    rejection_reason = fields.Text(string="Reason for Rejection")
    approval = fields.Selection(
        [("pending", "Pending"), ("rejected", "Rejected"), ("approved", "Approved")],
        default="pending",
        string="Approval",
    )

    total_excl_vat = fields.Float(
        string="Total Amount",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    vat_amount = fields.Float(
        string="VAT (15%)",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    total_incl_vat = fields.Float(
        string="Total Incl. VAT",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    has_valid_project = fields.Boolean(
        string="Has Valid Project", compute="_compute_has_valid_project", store=False
    )
    pr_created = fields.Boolean(string="PR Created", default=False)
    line_ids = fields.One2many('custom.pr.line', 'pr_id', string="PR Lines")
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('rfq_sent', 'RFQ Sent'),
            ('pending', 'Pending'),
            ('purchase', 'Purchase Order'),
            ('cancel', 'Cancelled'),
        ],
        string="Status",
        default='draft',
        tracking=True,
    )

    def _required_date_from_priority(self, priority):
        today = fields.Date.context_today(self)
        offsets = {
            'low': 30,
            'medium': 10,
            'high': 3,
            'urgent': 0,
        }
        return today + relativedelta(days=offsets.get(priority, 0))

    @api.onchange('priority')
    def _onchange_priority_set_required_date(self):
        for rec in self:
            if rec.priority:
                rec.required_date = rec._required_date_from_priority(rec.priority)

    @api.depends('line_ids.total_price')
    def _compute_totals(self):
        for rec in self:
            subtotal = sum(line.total_price for line in rec.line_ids)
            rec.total_excl_vat = subtotal
            rec.vat_amount = subtotal * 0.15
            rec.total_incl_vat = subtotal + rec.vat_amount

    @api.model
    def create(self, vals):
        if vals.get('priority'):
            vals['required_date'] = self._required_date_from_priority(vals['priority'])
        if vals.get('pr_type') == 'cash':
            vals['name'] = self.env['ir.sequence'].next_by_code('custom.cash.pr') or '/'
        else:
            vals['name'] = self.env['ir.sequence'].next_by_code('custom.pr') or '/'
        return super(CustomPR, self).create(vals)

    @api.model
    def default_get(self, fields_list):
        res = super(CustomPR, self).default_get(fields_list)

        # Get current user
        user = self.env.user
        employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)

        if employee:
            res.update({
                'requested_by': employee.name,
                'requested_user_id': user.id,
                'department': employee.department_id.name if employee.department_id else False,
                'supervisor': employee.parent_id.name if employee.parent_id else False,
                'supervisor_partner_id': employee.parent_id.user_id.partner_id.id if employee.parent_id and employee.parent_id.user_id else False,
            })
        else:
            res.update({
                'requested_by': user.name,
                'requested_user_id': user.id,
            })

        return res

    def action_create_pr(self):
        self.ensure_one()
        rec = self

        # Check required fields
        if not rec.line_ids:
            raise ValidationError("You must add at least one line before submitting the Purchase Requisition.")

        # Check if related project exists
        cost_center = rec.cost_center_id.sudo()
        if not cost_center:
            raise ValidationError("Please select a valid cost center.")

        # Budget validation
        if rec.total_excl_vat > cost_center.budget_left:
            raise ValidationError(
                f"You are out of budget! Total amount ({rec.total_excl_vat}) exceeds remaining budget ({cost_center.budget_left})."
            )

        # Validation: prevent 0 amount PR
        if rec.total_excl_vat == 0.00:
            raise ValidationError("Add Unit Price First.")

        # Check if an old PR exists for this record name

        # SIDISSUE1
        existing_pr = self.env['purchase.requisition'].sudo().search([('name', '=', rec.name)], limit=1)
        if existing_pr:
            existing_pr.sudo().unlink()

        # Create new Purchase Requisition
        requester = rec.requested_user_id.sudo() if rec.requested_user_id else self.env.user.sudo()
        supervisor_user = requester.supervisor_user_id if requester else False
        supervisor_name = rec.supervisor or (supervisor_user.name if supervisor_user else False)
        supervisor_partner_id = rec.supervisor_partner_id or (
            supervisor_user.partner_id.id if supervisor_user and supervisor_user.partner_id else False)

        requisition = self.env['purchase.requisition'].sudo().create({
            'name': rec.name,
            'date_request': rec.date_request,
            'requested_by': rec.requested_by,
            'department': rec.department,
            'supervisor': supervisor_name,
            'supervisor_partner_id': supervisor_partner_id,
            'required_date': rec.required_date,
            'priority': rec.priority,
            'cost_center_id': rec.cost_center_id.id,
            'notes': rec.notes,
            'comments': rec.comments,
            'pr_type': 'cash' if rec.pr_type == 'cash' else 'pr',
        })

        # Create Lines
        for line in rec.line_ids:
            self.env['purchase.requisition.line'].sudo().create({
                'requisition_id': requisition.id,
                'description': line.description.id,
                'type': line.type,
                'quantity': line.quantity,
                'unit': line.unit.name,
                'unit_price': line.unit_price,
            })

        rec.pr_created = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Success",
                'message': f"PR {requisition.name} has been created (old one replaced if existed).",
                'sticky': False,
            }
        }

    def write(self, vals):
        if vals.get('priority'):
            vals['required_date'] = self._required_date_from_priority(vals['priority'])
        return super(CustomPR, self).write(vals)

    @api.depends('cost_center_id')
    def _compute_has_valid_project(self):
        for rec in self:
            rec.has_valid_project = False
            if rec.cost_center_id and rec.cost_center_id.budget_left > 0:
                rec.has_valid_project = True


class CustomPRLine(models.Model):
    _name = 'custom.pr.line'
    _description = 'Custom PR Line'

    pr_id = fields.Many2one('custom.pr', string="Purchase Requisition", ondelete="cascade")
    description = fields.Many2one(
        'product.product',
        string="Product",
        required=True,
        ondelete="restrict",
        context={'display_default_code': False},
    )

    type = fields.Selection(
        [
            ('material', 'Material'),
            ('service', 'Service')
        ],
        string="Type",
        default='material',
        required=True
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    # unit = fields.Selection(
    #     [
    #         ('Kilogram', 'Kilogram'),
    #         ('Gram', 'Gram'),
    #         ('Litre', 'Litre'),
    #         ('Millilitre', 'Millilitre'),
    #         ('Meter', 'Metre'),
    #         ('Each', 'Each'),
    #     ],
    #     string="Unit",
    #     required=True,
    # )
    unit = fields.Many2one(
        'uom.uom',
        string="Unit of Measure"
    )

    unit_price = fields.Float(string="Unit Price")
    total_price = fields.Float(string="Total", compute="_compute_total", store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_total(self):
        for line in self:
            line.total_price = line.quantity * line.unit_price

    @api.onchange('description')
    def _onchange_description(self):
        for rec in self:
            if rec.description:
                rec.unit = rec.description.uom_id

    @api.constrains('quantity', 'unit_price')
    def _check_non_negative_values(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError('Quantity cannot be negative.')
            if rec.unit_price < 0:
                raise ValidationError('Unit Price cannot be negative.')


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    pr_name = fields.Char(string="PR Name", readonly=True)

    def _update_pr_state(self):
        """Helper to sync PR state with the highest PO state for the same pr_name"""
        for order in self:
            if order.pr_name:
                pr = self.env['custom.pr'].sudo().search([('name', '=', order.pr_name)], limit=1)
                if pr:
                    all_pos = self.env['purchase.order'].sudo().search([('pr_name', '=', order.pr_name)])
                    priority = {'draft': 1, 'sent': 2, 'pending': 3, 'purchase': 4, 'cancel': 5}
                    best_po = max(all_pos, key=lambda po: priority.get(po.state, 0))

                    # Update PR state
                    mapping = {
                        'draft': 'draft',
                        'sent': 'rfq_sent',
                        'pending': 'pending',
                        'purchase': 'purchase',
                        'cancel': 'cancel',
                    }
                    pr.state = mapping.get(best_po.state, pr.state)

    @api.model
    def create(self, vals):
        order = super().create(vals)
        # When PO is created, immediately set PR → pending
        if order.pr_name:
            pr = self.env['custom.pr'].sudo().search([('name', '=', order.pr_name)], limit=1)
            if pr:
                pr.state = 'pending'
        return order

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:
            self._update_pr_state()
        return res

    def print_quotation(self):
        """Override Print RFQ to use custom PetroRaq Draft Invoice report"""
        return self.env.ref('custom_pr_system.action_report_petroraq_draft_invoice').report_action(self)
