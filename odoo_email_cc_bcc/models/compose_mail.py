# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

import base64
import logging
import psycopg2
import re
import smtplib
import threading

from email.utils import formataddr
from odoo import api, fields, models, SUPERUSER_ID, tools, registry, _
from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from markupsafe import Markup, escape
from odoo.addons.mail.tools.discuss import Store
from odoo.tools import (clean_context, split_every, is_list_of)
_logger = logging.getLogger(__name__)


class ResCompany(models.Model):

    _inherit = 'res.company'

    display_cc_recipients = fields.Boolean(
        string="Display Recipients Cc (Partners)", default=True)
    display_bcc_recipients = fields.Boolean(
        string="Display Recipients Bcc (Partners)", default=True)
    display_cc = fields.Boolean(string="Display Cc (Emails)")
    display_bcc = fields.Boolean(string="Display Bcc (Emails)")
    display_reply_to = fields.Boolean(string="Display Reply To")
    default_cc = fields.Char(
        'Default Cc (Emails)', help='Carbon copy message recipients (Emails)')
    default_bcc = fields.Char(
        'Default Bcc (Emails)',
        help='Blind carbon copy message recipients (Emails)')
    default_reply_to = fields.Char('Default Reply To')


class MailComposer(models.TransientModel):
    """ Generic message composition wizard. You may inherit from this wizard
        at model and view levels to provide specific features.

        The behavior of the wizard depends on the composition_mode field:
        - 'comment': post on a record. The wizard is pre-populated via ``get_record_data``
        - 'mass_mail': wizard in mass mailing mode where the mail details can
            contain template placeholders that will be merged with actual data
            before being sent to each recipient.
    """
    _inherit = 'mail.compose.message'

    @api.model
    def get_default_cc_email(self):
        if self.env.company.display_cc:
            return self.env.company.default_cc
        return False

    @api.model
    def get_default_bcc_emails(self):
        if self.env.company.display_bcc:
            return self.env.company.default_bcc
        return False

    @api.model
    def get_default_reply_to(self):
        if self.env.company.display_reply_to:
            return self.env.company.default_reply_to
        return False


    email_bcc = fields.Char(
        'Bcc (Emails)', help='Blind carbon copy message (Emails)',
        default=get_default_bcc_emails)
    email_cc = fields.Char(
        'Cc (Emails)', help='Carbon copy message recipients (Emails)',
        default=get_default_cc_email)
    cc_recipient_ids = fields.Many2many(
        'res.partner', 'mail_compose_message_res_partner_cc_rel',
        'wizard_id', 'partner_id', string='Cc (Partners)')
    bcc_recipient_ids = fields.Many2many(
        'res.partner', 'mail_compose_message_res_partner_bcc_rel',
        'wizard_id', 'partner_id', string='Bcc (Partners)')
    display_cc = fields.Boolean(
        string="Display Cc",
        default=lambda self: self.env.company.display_cc,)
    display_bcc = fields.Boolean(
        string="Display Bcc",
        default=lambda self: self.env.company.display_bcc,)
    display_cc_recipients = fields.Boolean(
        string="Display Recipients Cc (Partners)",
        default=lambda self: self.env.company.display_cc_recipients,)
    display_bcc_recipients = fields.Boolean(
        string="Display Recipients Bcc (Partners)",
        default=lambda self: self.env.company.display_bcc_recipients)
    display_reply_to = fields.Boolean(
        string="Display Reply To",
        default=lambda self: self.env.company.display_reply_to,)
    email_to = fields.Text('To', help='Message recipients (emails)')
    reply_to = fields.Char(
        'Reply-To', default=get_default_reply_to,
        help='Reply email address. Setting the reply_to bypasses the automatic thread creation.')

    def _prepare_mail_values_static(self):
        self.ensure_one()
        values = super(MailComposer, self)._prepare_mail_values_static()
        values.update({
            'email_to': self.email_to,
            'email_bcc': self.email_bcc,
            'email_cc': self.email_cc,
            'cc_recipient_ids': self.cc_recipient_ids.ids,
            'bcc_recipient_ids': self.bcc_recipient_ids.ids,
        })
        return values    

class Message(models.Model):
    """ Messages model: system notification (replacing res.log notifications),
        comments (OpenChatter discussion) and incoming emails. """
    _inherit = 'mail.message'

    email_bcc = fields.Char(
        'Bcc (Emails)',
        help='Blind carbon copy message (Emails)')
    email_cc = fields.Char(
        'Cc (Emails)', help='Carbon copy message recipients (Emails)')
    cc_recipient_ids = fields.Many2many(
        'res.partner', 'mail_message_res_partner_cc_rel',
        'message_id', 'partner_id', string='Cc (Partners)')
    bcc_recipient_ids = fields.Many2many(
        'res.partner', 'mail_message_res_partner_bcc_rel',
        'message_id', 'partner_id', string='Bcc (Partners)')
    email_to = fields.Text('To', help='Message recipients (emails)')

    def _to_store(self, store: Store, /, *, fields=None, **kwargs):
        if fields is None:
            fields = [
                "body",
                "create_date",
                "date",
                "message_type",
                "model",
                "pinned_at",
                "res_id",
                "subject",
                "write_date",
                'email_cc', 'cc_recipient_ids',
                'email_bcc', 'bcc_recipient_ids','email_to'
            ]
        res = super()._to_store(store, fields=fields, **kwargs)
        return res
    
    def fetch_partner_name(self,partner_ids):
        partner_list = []
        for partner_id in partner_ids:
            partner_record = self.env['res.partner'].sudo().browse(int(partner_id))
            partner_list.append(partner_record.name)
        return partner_list

class Mail(models.Model):
    _inherit = "mail.mail"

    def get_partner_email_list(self, partners):
        emails_list = []  
        for partner in partners:
            emails_normalized = tools.email_normalize_all(partner.email)
            if emails_normalized:
                emails_list += [
                    tools.formataddr((partner.name or "", email or "False"))
                    for email in emails_normalized
                ]
            else:
                emails_list += [tools.formataddr((partner.name or "", partner.email or "False"))]
        return emails_list

    def _prepare_outgoing_list(self, mail_server=False, recipients_follower_status=None):
        results = super(Mail, self)._prepare_outgoing_list(mail_server, recipients_follower_status)

        if self._context.get('cc'):
            cc_emails = self.get_partner_email_list(self.cc_recipient_ids) 
            bcc_emails = self.get_partner_email_list(self.bcc_recipient_ids)
            for result in results:
                email_cc = result.get('email_cc') or []
                email_bcc = result.get('email_bcc') or []
                result.update({
                    'email_cc':email_cc + cc_emails,
                    'email_bcc':email_bcc + bcc_emails,
                })  
        return results

    def _send(self, auto_commit=False, raise_exception=False, smtp_session=None, alias_domain_id=False, mail_server=False, post_send_callback=None):
        IrMailServer = self.env['ir.mail_server']
        # Only retrieve recipient followers of the mails if needed
        mails_with_unfollow_link = self.filtered(lambda m: m.body_html and '/mail/unfollow' in m.body_html)
        recipients_follower_status = (
            None if not mails_with_unfollow_link
            else self.env['mail.followers']._get_mail_recipients_follower_status(mails_with_unfollow_link.ids)
        )

        for mail_id in self.ids:
            success_pids = []
            failure_reason = None
            failure_type = None
            processing_pid = None
            mail = None
            try:
                mail = self.browse(mail_id)
                if mail.state != 'outgoing':
                    if mail.state != 'exception' and mail.auto_delete:
                        mail.sudo().unlink()
                    continue

                # Writing on the mail object may fail (e.g. lock on user) which
                # would trigger a rollback *after* actually sending the email.
                # To avoid sending twice the same email, provoke the failure earlier
                mail.write({
                    'state': 'exception',
                    'failure_reason': _('Error without exception. Probably due to sending an email without computed recipients.'),
                })
                # Update notification in a transient exception state to avoid concurrent
                # update in case an email bounces while sending all emails related to current
                # mail record.
                notifs = self.env['mail.notification'].search([
                    ('notification_type', '=', 'email'),
                    ('mail_mail_id', 'in', mail.ids),
                    ('notification_status', 'not in', ('sent', 'canceled'))
                ])
                if notifs:
                    notif_msg = _('Error without exception. Probably due to concurrent access update of notification records. Please see with an administrator.')
                    notifs.sudo().write({
                        'notification_status': 'exception',
                        'failure_type': 'unknown',
                        'failure_reason': notif_msg,
                    })
                    # `test_mail_bounce_during_send`, force immediate update to obtain the lock.
                    # see rev. 56596e5240ef920df14d99087451ce6f06ac6d36
                    notifs.flush_recordset(['notification_status', 'failure_type', 'failure_reason'])

                # protect against ill-formatted email_from when formataddr was used on an already formatted email
                emails_from = tools.mail.email_split_and_format_normalize(mail.email_from)
                email_from = emails_from[0] if emails_from else mail.email_from

                # build an RFC2822 email.message.Message object and send it without queuing
                res = None
                # TDE note: could be great to pre-detect missing to/cc and skip sending it
                # to go directly to failed state update
                email_list = mail.with_context(cc=True)._prepare_outgoing_list(mail_server, recipients_follower_status)

                cc_email_list = []
                if not mail.email_to and (mail.email_cc or mail.cc_recipient_ids or mail.email_bcc or mail.bcc_recipient_ids):
                    cc_email_list.append(mail.with_context(cc=True)._prepare_outgoing_list(mail_server, recipients_follower_status))
                # send each sub-email
                for email in email_list:
                    if alias_domain_id:
                        alias_domain = self.env['mail.alias.domain'].sudo().browse(alias_domain_id)
                        SendIrMailServer = IrMailServer.with_context(
                            domain_notifications_email=alias_domain.default_from_email,
                            domain_bounce_address=email['headers'].get('Return-Path') or alias_domain.bounce_email,
                        )
                    else:
                        SendIrMailServer = IrMailServer
                    if email.get('email_to'):    
                        msg = SendIrMailServer.build_email(
                            email_from=email_from,
                            email_to=email['email_to'],
                            subject=email['subject'],
                            body=email['body'],
                            body_alternative=email['body_alternative'],
                            email_cc=email['email_cc'],
                            email_bcc=email['email_bcc'],
                            reply_to=email['reply_to'],
                            attachments=email['attachments'],
                            message_id=email['message_id'],
                            references=email['references'],
                            object_id=email['object_id'],
                            subtype='html',
                            subtype_alternative='plain',
                            headers=email['headers'],
                        )
                        processing_pid = email.pop("partner_id", None)
                        try:
                            res = SendIrMailServer.send_email(
                                msg, mail_server_id=mail.mail_server_id.id, smtp_session=smtp_session)
                            if processing_pid:
                                success_pids.append(processing_pid)
                            processing_pid = None
                        except AssertionError as error:
                            if str(error) == IrMailServer.NO_VALID_RECIPIENT:
                                # if we have a list of void emails for email_list -> email missing, otherwise generic email failure
                                if not email.get('email_to') and failure_type != "mail_email_invalid":
                                    failure_type = "mail_email_missing"
                                else:
                                    failure_type = "mail_email_invalid"
                                # No valid recipient found for this particular
                                # mail item -> ignore error to avoid blocking
                                # delivery to next recipients, if any. If this is
                                # the only recipient, the mail will show as failed.
                                _logger.info("Ignoring invalid recipients for mail.mail %s: %s",
                                            mail.message_id, email.get('email_to'))
                            else:
                                raise
                    elif email.get('email_cc') or email.get('email_bcc'):
                        msg = SendIrMailServer.build_email(
                            email_from=email_from,
                            email_to=email['email_to'],
                            subject=email['subject'],
                            body=email['body'],
                            body_alternative=email['body_alternative'],
                            email_cc=email['email_cc'],
                            email_bcc=email['email_bcc'],
                            reply_to=email['reply_to'],
                            attachments=email['attachments'],
                            message_id=email['message_id'],
                            references=email['references'],
                            object_id=email['object_id'],
                            subtype='html',
                            subtype_alternative='plain',
                            headers=email['headers'],
                        )
                        processing_pid = email.pop("partner_id", None)
                        try:
                            res = SendIrMailServer.send_email(
                                msg, mail_server_id=mail.mail_server_id.id, smtp_session=smtp_session)
                            if processing_pid:
                                success_pids.append(processing_pid)
                            processing_pid = None
                        except AssertionError as error:
                            if str(error) == IrMailServer.NO_VALID_RECIPIENT:
                                # if we have a list of void emails for email_list -> email missing, otherwise generic email failure
                                if not email.get('email_to') and failure_type != "mail_email_invalid":
                                    failure_type = "mail_email_missing"
                                else:
                                    failure_type = "mail_email_invalid"
                                # No valid recipient found for this particular
                                # mail item -> ignore error to avoid blocking
                                # delivery to next recipients, if any. If this is
                                # the only recipient, the mail will show as failed.
                                _logger.info("Ignoring invalid recipients for mail.mail %s: %s",
                                            mail.message_id, email.get('email_to'))
                            else:
                                raise
                if not email_list and cc_email_list:
                    body = self._prepare_outgoing_body()
                    attachments = self.attachment_ids
                    if attachments:
                        if body:
                            link_ids = {int(link) for link in re.findall(r'/web/(?:content|image)/([0-9]+)', body)}
                            if link_ids:
                                attachments = attachments - self.env['ir.attachment'].browse(list(link_ids))
                        # load attachment binary data with a separate read(), as prefetching all
                        # `datas` (binary field) could bloat the browse cache, triggering
                        # soft/hard mem limits with temporary data.
                        email_attachments = [
                            (a['name'], base64.b64decode(a['datas']), a['mimetype'])
                            for a in attachments.sudo().read(['name', 'datas', 'mimetype']) if a['datas'] is not False
                        ]
                    else:
                        email_attachments = []
                    for email in cc_email_list:
                        if alias_domain_id:
                            alias_domain = self.env['mail.alias.domain'].sudo().browse(alias_domain_id)
                            SendIrMailServer = IrMailServer.with_context(
                                domain_notifications_email=alias_domain.default_from_email,
                                domain_bounce_address=email['headers'].get('Return-Path') or alias_domain.bounce_email,
                            )
                        else:
                            SendIrMailServer = IrMailServer
                        msg = SendIrMailServer.build_email(
                            email_from = mail.email_from,
                            email_to = email.get('email_to') if isinstance(email, dict) else None,
                            subject = mail.subject,
                            body = email.get('body') if isinstance(email, dict) else None,
                            body_alternative = email.get('body_alternative') if isinstance(email, dict) else None,
                            email_cc = email.get('email_cc') if isinstance(email, dict) else None,
                            email_bcc = email.get('email_bcc') if isinstance(email, dict) else None,
                            reply_to = mail.reply_to,
                            attachments = email_attachments,
                            message_id = mail.message_id,
                            references = mail.references,
                            object_id = mail.res_id and ('%s-%s' % (mail.res_id, mail.model)),
                            subtype = 'html',
                            subtype_alternative = 'plain',
                            headers = email.get('email_bcc') if isinstance(email, dict) else None)
                        processing_pid = email.get('partner_id') if isinstance(email, dict) else None
                        try:
                            res = IrMailServer.send_email(
                                msg, mail_server_id=mail.mail_server_id.id, smtp_session=smtp_session)
                            if processing_pid:
                                success_pids.append(processing_pid)
                            processing_pid = None
                        except AssertionError as error:
                            if str(error) == IrMailServer.NO_VALID_RECIPIENT:
                                # if we have a list of void emails for email_list -> email missing, otherwise generic email failure
                                if not email.get('email_to') if isinstance(email, dict) else None and failure_type != "mail_email_invalid":
                                    failure_type = "mail_email_missing"
                                else:
                                    failure_type = "mail_email_invalid"
                                # No valid recipient found for this particular
                                # mail item -> ignore error to avoid blocking
                                # delivery to next recipients, if any. If this is
                                # the only recipient, the mail will show as failed.
                                _logger.info("Ignoring invalid recipients for mail.mail %s: %s",
                                            mail.message_id, email.get('email_to') if isinstance(email, dict) else None)
                            else:
                                raise              
                if res:  # mail has been sent at least once, no major exception occurred
                    mail.write({'state': 'sent', 'message_id': res, 'failure_reason': False})
                    _logger.info('Mail with ID %r and Message-Id %r successfully sent', mail.id, mail.message_id)
                    # /!\ can't use mail.state here, as mail.refresh() will cause an error
                    # see revid:odo@openerp.com-20120622152536-42b2s28lvdv3odyr in 6.1
                mail._postprocess_sent_message(success_pids=success_pids, failure_type=failure_type)
            except MemoryError:
                # prevent catching transient MemoryErrors, bubble up to notify user or abort cron job
                # instead of marking the mail as failed
                _logger.exception(
                    'MemoryError while processing mail with ID %r and Msg-Id %r. Consider raising the --limit-memory-hard startup option',
                    mail.id, mail.message_id)
                # mail status will stay on ongoing since transaction will be rollback
                raise
            except (psycopg2.Error, smtplib.SMTPServerDisconnected):
                # If an error with the database or SMTP session occurs, chances are that the cursor
                # or SMTP session are unusable, causing further errors when trying to save the state.
                _logger.exception(
                    'Exception while processing mail with ID %r and Msg-Id %r.',
                    mail.id, mail.message_id)
                raise
            except Exception as e:
                if isinstance(e, AssertionError):
                    # Handle assert raised in IrMailServer to try to catch notably from-specific errors.
                    # Note that assert may raise several args, a generic error string then a specific
                    # message for logging in failure type
                    error_code = e.args[0]
                    if len(e.args) > 1 and error_code == IrMailServer.NO_VALID_FROM:
                        # log failing email in additional arguments message
                        failure_reason = tools.exception_to_unicode(e.args[1])
                    else:
                        failure_reason = error_code
                    if error_code == IrMailServer.NO_VALID_FROM:
                        failure_type = "mail_from_invalid"
                    elif error_code in (IrMailServer.NO_FOUND_FROM, IrMailServer.NO_FOUND_SMTP_FROM):
                        failure_type = "mail_from_missing"
                # generic (unknown) error as fallback
                if not failure_reason:
                    failure_reason = tools.exception_to_unicode(e)
                if not failure_type:
                    failure_type = "unknown"

                _logger.exception('failed sending mail (id: %s) due to %s', mail.id, failure_reason)
                mail.write({
                    "failure_reason": failure_reason,
                    "failure_type": failure_type,
                    "state": "exception",
                })
                mail._postprocess_sent_message(
                    success_pids=success_pids,
                    failure_reason=failure_reason, failure_type=failure_type
                )
                if raise_exception:
                    if isinstance(e, (AssertionError, UnicodeEncodeError)):
                        if isinstance(e, UnicodeEncodeError):
                            value = "Invalid text: %s" % e.object
                        else:
                            value = '. '.join(e.args)
                        raise MailDeliveryException(value)
                    raise

            if auto_commit is True:
                self._cr.commit()
        return True


class Thread(models.AbstractModel):

    _inherit = "mail.thread"

    def _send_and_create_notification(self, message, recipient_ids, msg_vals=False,
                                model_description=False, mail_auto_delete=True, resend_existing=False,
                                force_send=True, send_after_commit=True,
                                **kwargs):
        if not recipient_ids:
            return True
        Mail = self.env['mail.mail'].sudo()
        notif_create_values = []
        mail_body = message.body
        mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)
        msg_vals.update({
                        'body_html': mail_body,
                        'recipient_ids': [(4, pid) for pid in recipient_ids],
                        'email_cc': message.email_cc,
                        'email_bcc': message.email_bcc,
                        'cc_recipient_ids': message.cc_recipient_ids,
                        'bcc_recipient_ids': message.bcc_recipient_ids,
                    })
        if message.email_to:
            msg_vals['email_to'] = message.email_to
        # create_values.update(msg_vals)  # mail_message_id, mail_server_id, auto_delete, references, headers
        email = Mail.create(msg_vals)
        if email and recipient_ids:
            tocreate_recipient_ids = list(recipient_ids)
            if resend_existing:
                existing_notifications = self.env['mail.notification'].sudo().search([
                    ('mail_message_id', '=', message.id),
                    ('notification_type', '=', 'email'),
                    ('res_partner_id', 'in', tocreate_recipient_ids)
                ])
                if existing_notifications:
                    tocreate_recipient_ids = [rid for rid in recipient_ids if rid not in existing_notifications.mapped('res_partner_id.id')]
                    existing_notifications.write({
                        'notification_status': 'ready',
                        'mail_mail_mail_idid': email.id,
                    })
            notif_create_values += [{
                'mail_message_id': message.id,
                'res_partner_id': recipient_id,
                'notification_type': 'email',
                'mail_mail_id': email.id,
                'is_read': True,  # discard Inbox notification
                'notification_status': 'ready',
            } for recipient_id in tocreate_recipient_ids]
        return email, notif_create_values


    def _notify_thread_by_email(self, message, recipients_data, msg_vals=False,
                                mail_auto_delete=True,  # mail.mail
                                model_description=False, force_email_company=False, force_email_lang=False,  # rendering
                                subtitles=None,  # rendering
                                resend_existing=False, force_send=True, send_after_commit=True,  # email send
                                 **kwargs):
        """ Method to send emails notifications linked to a message.

        :param record message: <mail.message> record being notified. May be
          void as 'msg_vals' superseeds it;
        :param list recipients_data: list of recipients data based on <res.partner>
          records formatted like [
          {
            'active': partner.active;
            'id': id of the res.partner being recipient to notify;
            'is_follower': follows the message related document;
            'lang': its lang;
            'groups': res.group IDs if linked to a user;
            'notif': 'inbox', 'email', 'sms' (SMS App);
            'share': is partner a customer (partner.partner_share);
            'type': partner usage ('customer', 'portal', 'user');
            'ushare': are users shared (if users, all users are shared);
          }, {...}]. See ``MailThread._notify_get_recipients()``;
        :param dict msg_vals: values dict used to create the message, allows to
          skip message usage and spare some queries;

        :param bool mail_auto_delete: delete notification emails once sent;

        :param str model_description: description of current model, given to
          avoid fetching it and easing translation support;
        :param record force_email_company: <res.company> record used when rendering
          notification layout. Otherwise computed based on current record;
        :param str force_email_lang: lang used when rendering content, used
          notably to compute model name or translate access buttons;
        :param list subtitles: optional list set as template value "subtitles";

        :param bool resend_existing: check for existing notifications to update
          based on mailed recipient, otherwise create new notifications;
        :param bool force_send: send emails directly instead of using queue;
        :param bool send_after_commit: if force_send, tells to send emails after
          the transaction has been committed using a post-commit hook;
        """
        partners_data = [r for r in recipients_data if r['notif'] == 'email']
        if not partners_data:
            if message.email_cc or message.email_bcc or message.cc_recipient_ids or message.bcc_recipient_ids or message.email_to:
                email = self._nofity_cc_bcc(message, msg_vals=msg_vals, **kwargs)
            return True

        base_mail_values = self._notify_by_email_get_base_mail_values(
            message,
            additional_values={'auto_delete': mail_auto_delete}
        )

        # Clean the context to get rid of residual default_* keys that could cause issues during
        # the mail.mail creation.
        # Example: 'default_state' would refer to the default state of a previously created record
        # from another model that in turns triggers an assignation notification that ends up here.
        # This will lead to a traceback when trying to create a mail.mail with this state value that
        # doesn't exist.
        SafeMail = self.env['mail.mail'].sudo().with_context(clean_context(self._context))
        SafeNotification = self.env['mail.notification'].sudo().with_context(clean_context(self._context))
        emails = self.env['mail.mail'].sudo()

        # loop on groups (customer, portal, user,  ... + model specific like group_sale_salesman)
        notif_create_values = []
        recipients_max = 50
        cc_email = False
        if message.email_cc or message.email_bcc or message.cc_recipient_ids or message.bcc_recipient_ids: 
            cc_email = True
        email_to = ''
        for _lang, render_values, recipients_group in self._notify_get_classified_recipients_iterator(
            message,
            partners_data,
            msg_vals=msg_vals,
            model_description=model_description,
            force_email_company=force_email_company,
            force_email_lang=force_email_lang,
            subtitles=subtitles,
        ):
            # generate notification email content
            mail_body = self._notify_by_email_render_layout(
                message,
                recipients_group,
                msg_vals=msg_vals,
                render_values=render_values,
            )
            recipients_ids = recipients_group.pop('recipients')

            # create email
            for recipients_ids_chunk in split_every(recipients_max, recipients_ids):
                mail_values = self._notify_by_email_get_final_mail_values(
                    recipients_ids_chunk,
                    base_mail_values,
                    additional_values={'body_html': mail_body}
                )
                new_email = SafeMail.create(mail_values)

                if new_email and recipients_ids_chunk:
                    tocreate_recipient_ids = list(recipients_ids_chunk)
                    if resend_existing:
                        existing_notifications = self.env['mail.notification'].sudo().search([
                            ('mail_message_id', '=', message.id),
                            ('notification_type', '=', 'email'),
                            ('res_partner_id', 'in', tocreate_recipient_ids)
                        ])
                        if existing_notifications:
                            tocreate_recipient_ids = [rid for rid in recipients_ids_chunk if rid not in existing_notifications.mapped('res_partner_id.id')]
                            existing_notifications.write({
                                'notification_status': 'ready',
                                'mail_mail_id': new_email.id,
                            })
                    notif_create_values += [{
                        'author_id': message.author_id.id,
                        'is_read': True,  # discard Inbox notification
                        'mail_mail_id': new_email.id,
                        'mail_message_id': message.id,
                        'notification_status': 'ready',
                        'notification_type': 'email',
                        'res_partner_id': recipient_id,
                    } for recipient_id in tocreate_recipient_ids]
                emails |= new_email

        if notif_create_values:
            SafeNotification.create(notif_create_values)

        # NOTE:
        #   1. for more than 50 followers, use the queue system
        #   2. do not send emails immediately if the registry is not loaded,
        #      to prevent sending email during a simple update of the database
        #      using the command-line.
        test_mode = getattr(threading.current_thread(), 'testing', False)
        if force_send := self.env.context.get('mail_notify_force_send', force_send):
            force_send_limit = int(self.env['ir.config_parameter'].sudo().get_param('mail.mail.force.send.limit', 100))
            force_send = len(emails) < force_send_limit
        if force_send and (not self.pool._init or test_mode):
            # unless asked specifically, send emails after the transaction to
            # avoid side effects due to emails being sent while the transaction fails
            if not test_mode and send_after_commit:
                emails.send_after_commit()
            else:
                emails.send()

        return True
    
    def _raise_for_invalid_parameters(self, parameter_names, forbidden_names=None, restricting_names=None):
        recipient_list = ['bcc_recipient_ids','cc_recipient_ids','email_cc','email_to','email_bcc']
        if restricting_names:
            restricting_names.update(recipient_list)
        return super()._raise_for_invalid_parameters(parameter_names, forbidden_names=forbidden_names, restricting_names=restricting_names)

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, *,
                     body='', subject=None, message_type='notification',
                     email_from=None, author_id=None, parent_id=False,
                     subtype_xmlid=None, subtype_id=False, partner_ids=None,
                     attachments=None, attachment_ids=None, body_is_html=False,
                     **kwargs):
        """ Post a new message in an existing thread, returning the new mail.message.

        :param str|Markup body: body of the message, str content will be escaped, Markup
            for html body
        :param str subject: subject of the message
        :param str message_type: see mail_message.message_type field. Can be anything but
            user_notification, reserved for message_notify
        :param str email_from: from address of the author. See ``_message_compute_author``
            that uses it to make email_from / author_id coherent;
        :param int author_id: optional ID of partner record being the author. See
            ``_message_compute_author`` that uses it to make email_from / author_id coherent;
        :param int parent_id: handle thread formation
        :param str subtype_xmlid: optional xml id of a mail.message.subtype to
          fetch, will force value of subtype_id;
        :param int subtype_id: subtype_id of the message, used mainly for followers
            notification mechanism;
        :param list(int) partner_ids: partner_ids to notify in addition to partners
            computed based on subtype / followers matching;
        :param list(tuple(str,str), tuple(str,str, dict)) attachments : list of attachment
            tuples in the form ``(name,content)`` or ``(name,content, info)`` where content
            is NOT base64 encoded;
        :param list attachment_ids: list of existing attachments to link to this message
            Should not be a list of commands. Attachment records attached to mail
            composer will be attached to the related document.
        :param bool body_is_html: indicates body should be threated as HTML even if str
            to be used only for RPC calls

        Extra keyword arguments will be used either
          * as default column values for the new mail.message record if they match
            mail.message fields;
          * propagated to notification methods if not;

        :return record: newly create mail.message
        """
        self.ensure_one()  # should always be posted on a record, use message_notify if no record
        # preliminary value safety check
        self._raise_for_invalid_parameters(
            set(kwargs.keys()),
            forbidden_names={'model', 'res_id', 'subtype'}
        )
        if self._name == 'mail.thread' or not self.id:
            raise ValueError(_("Posting a message should be done on a business document. Use message_notify to send a notification to an user."))
        if message_type == 'user_notification':
            raise ValueError(_("Use message_notify to send a notification to an user."))
        if attachments:
            # attachments should be a list (or tuples) of 3-elements list (or tuple)
            format_error = not is_list_of(attachments, list) and not is_list_of(attachments, tuple)
            if not format_error:
                format_error = not all(len(attachment) in {2, 3} for attachment in attachments)
            if format_error:
                raise ValueError(
                    _('Posting a message should receive attachments as a list of list or tuples (received %(aids)s)',
                      aids=repr(attachment_ids),
                     )
                )
        if attachment_ids and not is_list_of(attachment_ids, int):
            raise ValueError(
                _('Posting a message should receive attachments records as a list of IDs (received %(aids)s)',
                  aids=repr(attachment_ids),
                 )
            )
        attachment_ids = list(attachment_ids or [])
        if partner_ids and not is_list_of(partner_ids, int):
            raise ValueError(
                _('Posting a message should receive partners as a list of IDs (received %(pids)s)',
                  pids=repr(partner_ids),
                 )
            )
        partner_ids = list(partner_ids or [])

        # split message additional values from notify additional values
        msg_kwargs = {key: val for key, val in kwargs.items()
                      if key in self.env['mail.message']._fields}
        notif_kwargs = {key: val for key, val in kwargs.items()
                        if key not in msg_kwargs}

        # Add lang to context immediately since it will be useful in various flows later
        self = self._fallback_lang()

        # Explicit access rights check, because display_name is computed as sudo.
        self.check_access('read')
        self.check_access('read')

        # Find the message's author
        guest = self.env['mail.guest']._get_guest_from_context()
        if self.env.user._is_public() and guest:
            author_guest_id = guest.id
            author_id, email_from = False, False
        else:
            author_guest_id = False
            author_id, email_from = self._message_compute_author(author_id, email_from, raise_on_email=True)

        if subtype_xmlid:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id(subtype_xmlid)
        if not subtype_id:
            subtype_id = self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note')

        # automatically subscribe recipients if asked to
        if self._context.get('mail_post_autofollow') and partner_ids:
            self.message_subscribe(partner_ids=list(partner_ids))
        
        parent_id = self._message_compute_parent_id(parent_id)

        cc_partner_ids = set()
        cc_recipient_ids = kwargs.pop('cc_recipient_ids', [])
        for partner_id in cc_recipient_ids:
            if isinstance(partner_id, (list, tuple)) and partner_id[0] == 4 \
                    and len(partner_id) == 2:
                cc_partner_ids.add(partner_id[1])
            if isinstance(partner_id, (list, tuple)) and partner_id[0] == 6 \
                    and len(partner_id) == 3:
                cc_partner_ids |= set(partner_id[2])
            elif isinstance(partner_id, int):
                cc_partner_ids.add(partner_id)
            else:
                pass
        bcc_partner_ids = set()
        bcc_recipient_ids = kwargs.pop('bcc_recipient_ids', [])
        for partner_id in bcc_recipient_ids:
            if isinstance(partner_id, (list, tuple)) and partner_id[0] == 4 and len(partner_id) == 2:
                bcc_partner_ids.add(partner_id[1])
            if isinstance(partner_id, (list, tuple)) and partner_id[0] == 6 and len(partner_id) == 3:
                bcc_partner_ids |= set(partner_id[2])
            elif isinstance(partner_id, int):
                bcc_partner_ids.add(partner_id)
            else:
                pass
        msg_values = dict(msg_kwargs)
        if 'email_add_signature' not in msg_values:
            msg_values['email_add_signature'] = True
        if not msg_values.get('record_name'):
            # use sudo as record access is not always granted (notably when replying
            # a notification) -> final check is done at message creation level
            msg_values['record_name'] = self.sudo().display_name
        if body_is_html and self.env.user._is_internal():
            _logger.warning("Posting HTML message using body_is_html=True, use a Markup object instead (user: %s)",
                self.env.user.id)
            body = Markup(body)

        msg_values.update({
            # author
            'author_id': author_id,
            'author_guest_id': author_guest_id,
            'email_from': email_from,
            # document
            'model': self._name,
            'res_id': self.id,
            # content
            'body': escape(body),  # escape if text, keep if markup
            'message_type': message_type,
            'parent_id': self._message_compute_parent_id(parent_id),
            'subject': subject or False,
            'subtype_id': subtype_id,
            # recipients
            'partner_ids': partner_ids,
            'cc_recipient_ids': cc_recipient_ids,
            'bcc_recipient_ids': bcc_recipient_ids
        })

        msg_values.update(
            self._process_attachments_for_post(attachments, attachment_ids, msg_values)
        )  # attachement_ids, body
        new_message = self._message_create([msg_values])

        # subscribe author(s) so that they receive answers; do it only when it is
        # a manual post by the author (aka not a system notification, not a message
        # posted 'in behalf of', and if still active).
        author_subscribe = (not self._context.get('mail_create_nosubscribe') and
                             msg_values['message_type'] != 'notification')
        if author_subscribe:
            real_author_id = False
            # if current user is active, they are the one doing the action and should
            # be notified of answers. If they are inactive they are posting on behalf
            # of someone else (a custom, mailgateway, ...) and the real author is the
            # message author
            if self.env.user.active:
                real_author_id = self.env.user.partner_id.id
            elif msg_values['author_id']:
                author = self.env['res.partner'].browse(msg_values['author_id'])
                if author.active:
                    real_author_id = author.id
            if real_author_id:
                self._message_subscribe(partner_ids=[real_author_id])

        self._message_post_after_hook(new_message, msg_values)
        self._notify_thread(new_message, msg_values, **notif_kwargs)
        return new_message

    def _notify_thread(self, message, msg_vals=False, notify_by_email=True, **kwargs):
        """ Main notification method. This method basically does two things

         * call ``_notify_compute_recipients`` that computes recipients to
           notify based on message record or message creation values if given
           (to optimize performance if we already have data computed);
         * performs the notification process by calling the various notification
           methods implemented;

        This method cnn be overridden to intercept and postpone notification
        mechanism like mail.channel moderation.

        :param message: mail.message record to notify;
        :param msg_vals: dictionary of values used to create the message. If given
          it is used instead of accessing ``self`` to lessen query count in some
          simple cases where no notification is actually required;

        Kwargs allow to pass various parameters that are given to sub notification
        methods. See those methods for more details about the additional parameters.
        Parameters used for email-style notifications
        """
        msg_vals = msg_vals if msg_vals else {}
        rdata = self._notify_get_recipients(message, msg_vals)
        if message.email_cc or message.email_bcc or message.cc_recipient_ids or message.bcc_recipient_ids or message.email_to:
            email = self._nofity_cc_bcc(message, msg_vals=msg_vals, **kwargs)

        self._notify_thread_by_inbox(message, rdata, msg_vals=msg_vals, **kwargs)
        if notify_by_email:
            self._notify_thread_by_email(message, rdata, msg_vals=msg_vals, **kwargs)

        return rdata

    def _nofity_cc_bcc(self, message, msg_vals, model_description=False, mail_auto_delete=True,
                                force_send=True, send_after_commit=True, **kwargs):
        force_send = self.env.context.get('mail_notify_force_send', force_send)

        template_values = self._notify_by_email_prepare_rendering_context(message, msg_vals, model_description=model_description) # 10 queries

        email_layout_xmlid = msg_vals.get('email_layout_xmlid') if msg_vals else message.email_layout_xmlid
        template_xmlid = email_layout_xmlid if email_layout_xmlid else 'mail.mail_notification_layout'
        mail_body = message.body
        mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)
        mail_subject = message.subject or (message.record_name and 'Re: %s' % message.record_name) # in cache, no queries
        # prepare notification mail values
        base_mail_values = {
            'mail_message_id': message.id,
            'mail_server_id': message.mail_server_id.id, # 2 query, check acces + read, may be useless, Falsy, when will it be used?
            'auto_delete': mail_auto_delete,
            # due to ir.rule, user have no right to access parent message if message is not published
            'references': message.parent_id.sudo().message_id if message.parent_id else False,
            'subject': mail_subject,
            'body_html': mail_body,
            'subject': mail_subject,
            'email_cc':message.email_cc,
            'email_bcc':message.email_bcc,
            'cc_recipient_ids':message.cc_recipient_ids,
            'bcc_recipient_ids':message.bcc_recipient_ids,
            'email_to':message.email_to,
        }
        headers = self._notify_by_email_get_headers()
        if headers:
            base_mail_values['headers'] = headers
        Mail = self.env['mail.mail'].sudo()
        email = Mail.create(base_mail_values)
        if force_send:
            email.send(True)
        return email
