from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    display_cc_recipients = fields.Boolean(
        string='Display CC Recipients (Partners)',
        default=True,
    )
    display_bcc_recipients = fields.Boolean(
        string='Display BCC Recipients (Partners)',
        default=True,
    )
    display_cc = fields.Boolean(string='Display CC (Emails)', default=True)
    display_bcc = fields.Boolean(string='Display BCC (Emails)', default=True)
    default_cc = fields.Char(string='Default CC (Emails)')
    default_bcc = fields.Char(string='Default BCC (Emails)')


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    email_bcc = fields.Char(
        string='BCC (Emails)',
        help='Blind carbon copy message recipients (emails).',
        default=lambda self: self._get_default_bcc(),
    )
    email_cc = fields.Char(
        string='CC (Emails)',
        help='Carbon copy message recipients (emails).',
        default=lambda self: self._get_default_cc(),
    )
    cc_recipient_ids = fields.Many2many(
        'res.partner',
        'mail_compose_message_res_partner_cc_rel',
        'wizard_id',
        'partner_id',
        string='CC (Partners)',
    )
    bcc_recipient_ids = fields.Many2many(
        'res.partner',
        'mail_compose_message_res_partner_bcc_rel',
        'wizard_id',
        'partner_id',
        string='BCC (Partners)',
    )
    display_cc = fields.Boolean(default=lambda self: self.env.company.display_cc)
    display_bcc = fields.Boolean(default=lambda self: self.env.company.display_bcc)
    display_cc_recipients = fields.Boolean(
        default=lambda self: self.env.company.display_cc_recipients
    )
    display_bcc_recipients = fields.Boolean(
        default=lambda self: self.env.company.display_bcc_recipients
    )
    email_to = fields.Text('To', help='Message recipients (emails).')

    @api.model
    def _get_default_cc(self):
        return self.env.company.default_cc if self.env.company.display_cc else False

    @api.model
    def _get_default_bcc(self):
        return self.env.company.default_bcc if self.env.company.display_bcc else False

    @staticmethod
    def _merge_emails(*email_values):
        emails = []
        for value in email_values:
            if not value:
                continue
            if isinstance(value, str):
                parts = [item.strip() for item in value.split(',') if item.strip()]
                emails.extend(parts)
            else:
                emails.extend([item.strip() for item in value if item and item.strip()])
        seen = set()
        ordered_unique = []
        for email in emails:
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered_unique.append(email)
        return ','.join(ordered_unique) if ordered_unique else False

    def get_mail_values(self, res_ids):
        self.ensure_one()
        mail_values = super().get_mail_values(res_ids)

        partner_cc_emails = self.cc_recipient_ids.mapped('email')
        partner_bcc_emails = self.bcc_recipient_ids.mapped('email')

        merged_cc = self._merge_emails(self.email_cc, partner_cc_emails)
        merged_bcc = self._merge_emails(self.email_bcc, partner_bcc_emails)

        for res_id in res_ids:
            values = mail_values.get(res_id, {})
            values.update({
                'email_to': self.email_to or values.get('email_to'),
                'email_cc': merged_cc,
                'email_bcc': merged_bcc,
            })
            mail_values[res_id] = values

        return mail_values


class Message(models.Model):
    _inherit = 'mail.message'

    email_bcc = fields.Char(string='BCC (Emails)')
    email_cc = fields.Char(string='CC (Emails)')
    cc_recipient_ids = fields.Many2many(
        'res.partner',
        'mail_message_res_partner_cc_rel',
        'message_id',
        'partner_id',
        string='CC (Partners)',
    )
    bcc_recipient_ids = fields.Many2many(
        'res.partner',
        'mail_message_res_partner_bcc_rel',
        'message_id',
        'partner_id',
        string='BCC (Partners)',
    )
    email_to = fields.Text(string='To')
