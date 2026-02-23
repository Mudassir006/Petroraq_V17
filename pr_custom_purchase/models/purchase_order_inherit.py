from odoo import models
from datetime import datetime, date, timedelta
import base64
from io import BytesIO

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def action_send_purchase_order_email(self):
        """Open the standard Compose wizard pre-filled with our custom body and recipients."""
        self.ensure_one()

        # Header fields (read defensively for custom attrs)
        vendor_name = self.partner_id.display_name or ''
        vendor_ref = self.partner_ref or ''
        rfq_origin = self.name or ''
        # Prefer Expected Arrival from related purchase.quotation, fallback to PO date_planned
        planned_val = self._get_expected_arrival_from_quotation() or self.date_planned or ''
        planned = self._format_expected_arrival(planned_val)

        # Persist back to PO so the backend reflects the quotation's expected arrival
        planned_dt = self._coerce_to_datetime(planned_val)
        if planned_dt and (not self.date_planned or self.date_planned != planned_dt):
            try:
                self.write({'date_planned': planned_dt})
            except Exception:
                # Non-blocking; continue even if write fails
                pass

        project_name = getattr(self, 'project_id', False) and self.project_id.display_name or ''
        budget_type = getattr(self, 'budget_type', '') or ''
        budget_code = getattr(self, 'budget_code', '') or ''
        pr_name = getattr(self, 'pr_name', '') or ''
        requested_by = getattr(self, 'requested_by', '') or ''
        department = getattr(self, 'department', '') or ''
        supervisor = getattr(self, 'supervisor', '') or ''

        total_amount = getattr(self, 'amount_total', 0.0)

        # Build HTML sections
        summary_html = f"""
        <h3 style="margin-top:16px;">Summary</h3>
        <table border="0" cellspacing="0" cellpadding="4" style="width:100%;">
          <tr>
            <td style="width:25%;"><strong>Vendor</strong></td>
            <td>{vendor_name}</td>
            <td style="width:25%;"><strong>Vendor Ref</strong></td>
            <td>{vendor_ref}</td>
          </tr>
          <tr>
            <td><strong>RFQ Origin</strong></td>
            <td>{rfq_origin}</td>
            <td><strong>Expected Arrival</strong></td>
            <td>{planned}</td>
          </tr>
          <tr>
            <td><strong>Project</strong></td>
            <td>{project_name}</td>
            <td><strong>PR Name</strong></td>
            <td>{pr_name}</td>
          </tr>
          <tr>
            <td><strong>Requested By</strong></td>
            <td>{requested_by}</td>
            <td><strong>Department</strong></td>
            <td>{department}</td>
          </tr>
          <tr>
            <td><strong>Supervisor</strong></td>
            <td>{supervisor}</td>
             <td><strong>Quotation Ref No</strong></td>
            <td>{rfq_origin}</td>
          </tr>
        </table>
        """

        # Custom quotation lines (if your PO has custom_line_ids)
        custom_lines = getattr(self, 'custom_line_ids', False)
        custom_lines_html = ''
        if custom_lines:
            rows = []
            subtotal_sum = 0.0
            for ln in custom_lines:
                qty_val = ln.quantity or 0.0
                price_val = ln.price_unit or 0.0
                subtotal_sum += price_val * qty_val
                rows.append(
                    f"<tr>"
                    f"<td>{ln.name or ''}</td>"
                    f"<td>{qty_val}</td>"
                    f"<td>{ln.type or ''}</td>"
                    f"<td>{ln.unit or ''}</td>"
                    f"<td>{price_val}</td>"
                    f"</tr>"
                )
            currency = getattr(self, 'currency_id', False)
            symbol = (currency and currency.symbol) or ''
            amount_str = f"{symbol} {subtotal_sum:,.2f}".strip()
            custom_lines_html = (
                "<h3 style=\"margin-top:24px;\">Quotation Lines</h3>"
                "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" style=\"border-collapse: collapse; width: 100%;\">"
                "<thead><tr style=\"background-color:#f2f2f2;\">"
                "<th>Description</th><th>Quantity</th><th>Type</th><th>Unit</th><th>Unit Price</th>"
                "</tr></thead><tbody>" + ''.join(rows) + "</tbody></table>"
                f"<div style=\"display:flex; justify-content:flex-end; margin-top:10px;\">"
                f"  <div style=\"min-width:260px; text-align:right;\">"
                f"    <span style=\"margin-right:12px;\"><strong>Subtotal</strong></span>"
                f"    <span>{amount_str}</span>"
                f"  </div>"
                f"</div>"
            )

        # Standard PO lines (commented out per request)
        # po_rows = []
        # for line in self.order_line:
        #     po_rows.append(
        #         f"<tr>"
        #         f"<td>{line.product_id.display_name or ''}</td>"
        #         f"<td>{line.name or ''}</td>"
        #         f"<td>{line.product_qty or 0}</td>"
        #         f"<td>{line.price_unit or 0}</td>"
        #         f"<td>{line.price_subtotal or 0}</td>"
        #         f"</tr>"
        #     )
        # po_lines_html = (
        #     "<h3 style=\"margin-top:24px;\">Purchase Order Lines</h3>"
        #     "<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\" style=\"border-collapse: collapse; width: 100%;\">"
        #     "<thead><tr style=\"background-color:#f2f2f2;\">"
        #     "<th>Product</th><th>Description</th><th>Quantity</th><th>Unit Price</th><th>Subtotal</th>"
        #     "</tr></thead><tbody>" + ''.join(po_rows) + "</tbody></table>"
        # )
        po_lines_html = ""

        # Terms & conditions: fetch from related purchase.quotation (by origin)
        terms = self._get_terms_section()
        terms_html = terms.get('html', '')

        body = f"""
        <p>Dear Vendor,</p>
        <p>Please find below the details of Purchase Order <strong>{self.name}</strong>:</p>
        {summary_html}
        {custom_lines_html}
        {po_lines_html}
        {terms_html}
        <p style=\"margin-top:16px;\">Regards,<br/>{self.env.user.name}</p>
        """

        subject = f"Purchase Order: {self.name}"

        # Recipients: partner_id + optional vendor_ids (if present on model)
        partner_ids = []
        if self.partner_id:
            partner_ids.append(self.partner_id.id)
        extra_vendor_ids = getattr(self, 'vendor_ids', False) and self.vendor_ids.ids or []
        for vid in extra_vendor_ids:
            if vid not in partner_ids:
                partner_ids.append(vid)

        compose_form = self.env.ref('mail.email_compose_message_wizard_form')
        # Generate and attach PO PDF (pure Python using reportlab)
        attachment_ids = []
        try:
            pdf_bytes = self._build_email_pdf_bytes(
                vendor_name=vendor_name,
                summary_html=summary_html,
                custom_lines=self.custom_line_ids,
                currency_name=getattr(self, 'currency_id', False) and self.currency_id.name or '',
                terms=terms
            )
            if pdf_bytes:
                Attachment = self.env['ir.attachment'].sudo()
                filename = f"{self.name}.pdf"
                existing = Attachment.search([
                    ('res_model', '=', 'purchase.order'),
                    ('res_id', '=', self.id),
                    ('name', '=', filename),
                ], limit=1)
                if existing:
                    existing.write({'datas': base64.b64encode(pdf_bytes)})
                    attachment_ids = [existing.id]
                else:
                    att = Attachment.create({
                        'name': filename,
                        'res_model': 'purchase.order',
                        'res_id': self.id,
                        'type': 'binary',
                        'mimetype': 'application/pdf',
                        'datas': base64.b64encode(pdf_bytes),
                    })
                    attachment_ids = [att.id]
        except Exception:
            # Non-blocking if report not available
            attachment_ids = []
        ctx = {
            'default_model': 'purchase.order',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_subject': subject,
            'default_body': body,
            'default_partner_ids': partner_ids,
            'default_email_layout_xmlid': 'mail.mail_notification_light',
            'default_attachment_ids': [(6, 0, attachment_ids)] if attachment_ids else [],
            'force_email': True,
            'mark_rfq_as_sent': True,
        }

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    def _build_email_pdf_bytes(self, vendor_name, summary_html, custom_lines, currency_name, terms):
        """Create a PDF in-memory with the same info as the email body using reportlab.
        Returns raw PDF bytes or b'' if reportlab is not available.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        except Exception:
            return b''

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        elements = []

        title = Paragraph(f"Your Purchase Order <b>{self.name}</b>", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 12))

        greeting = Paragraph(f"Dear {'Vendor' or ''},", styles['Normal'])
        elements.append(greeting)
        elements.append(Spacer(1, 8))

        intro = Paragraph(f"Please find below the details of Purchase Order <b>{self.name}</b>:", styles['Normal'])
        elements.append(intro)
        elements.append(Spacer(1, 12))

        # Summary table (four columns)
        def _val(v):
            return v if v is not None else ''

        data_summary = [
            ['Vendor', _val(vendor_name), 'Vendor Ref', _val(self.partner_ref or '')],
            ['RFQ Origin', _val(self.name), 'Expected Arrival', _val(self._format_expected_arrival(self._get_expected_arrival_from_quotation() or self.date_planned or ''))],
            ['Project', _val(getattr(self.project_id, 'display_name', '')), 'PR Name', _val(getattr(self, 'pr_name', ''))],
            ['Requested By', _val(getattr(self, 'requested_by', '')), 'Department', _val(getattr(self, 'department', ''))],
            ['Supervisor', _val(getattr(self, 'supervisor', '')), 'Quotation Ref No', _val(self.name)],
        ]
        t_summary = Table(data_summary, colWidths=[90, 170, 110, 170])
        t_summary.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('TEXTCOLOR', (2, 0), (2, -1), colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(Paragraph('Summary', styles['Heading2']))
        elements.append(t_summary)
        elements.append(Spacer(1, 12))

        # Quotation lines table
        rows = [['Description', 'Quantity', 'Type', 'Unit', 'Unit Price']]
        source_lines = custom_lines or self.order_line
        subtotal_sum = 0.0
        for ln in source_lines:
            desc = getattr(ln, 'name', '')
            qty = getattr(ln, 'quantity', None)
            if qty is None:
                qty = getattr(ln, 'product_qty', 0.0)
            typ = getattr(ln, 'type', '')
            unit = getattr(ln, 'unit', '')
            if not unit:
                uom = getattr(ln, 'product_uom', False)
                unit = uom and uom.name or ''
            price = getattr(ln, 'price_unit', 0.0)
            subtotal_sum += (price or 0.0) * (qty or 0.0)
            rows.append([desc or '', f"{qty}", typ or '', unit or '', f"{price}"])

        t_lines = Table(rows, colWidths=[200, 70, 70, 70, 100])
        t_lines.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(Paragraph('Quotation Lines', styles['Heading2']))
        elements.append(t_lines)
        # Subtotal footer under table
        try:
            symbol = getattr(self.currency_id, 'symbol', '') or ''
        except Exception:
            symbol = ''
        subtotal_str = f"{symbol} {subtotal_sum:,.2f}".strip()
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<para align='right'><b>Subtotal</b>  {subtotal_str}</para>", styles['Normal']))
        elements.append(Spacer(1, 12))

        # Terms & Conditions
        if terms and terms.get('items'):
            elements.append(Spacer(1, 12))
            elements.append(Paragraph('Terms and Conditions', styles['Heading2']))
            data_tc = []
            for label, value in terms['items']:
                data_tc.append([label, value])
            t_tc = Table(data_tc, colWidths=[180, 360])
            t_tc.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(t_tc)

        elements.append(Paragraph(f"Regards,<br/>{self.env.user.name}", styles['Normal']))

        doc.build(elements)
        return buffer.getvalue()

    def _get_expected_arrival_from_quotation(self):
        """Fetch expected_arrival from related purchase.quotation if available."""
        Quotation = self.env['purchase.quotation'].sudo()
        quotation = False
        if self.origin:
            quotation = Quotation.search([('rfq_origin', '=', self.origin)], limit=1)
        if not quotation and self.name:
            quotation = Quotation.search([('rfq_origin', '=', self.name)], limit=1)
        if not quotation and getattr(self, 'pr_name', False):
            quotation = Quotation.search([('pr_name', '=', self.pr_name)], limit=1)
        if not quotation:
            return False
        # Try expected_arrival first, fallback to delivery_date used elsewhere
        val = getattr(quotation, 'expected_arrival', False) or getattr(quotation, 'delivery_date', False)
        return val

    def _format_expected_arrival(self, value):
        """Return a YYYY-MM-DD string with +5h adjustment for datetimes, similar to client JS."""
        if not value:
            return ''
        try:
            # if it's a string already, try to parse, else return as-is
            if isinstance(value, str):
                try:
                    # attempt parse common formats
                    dt = datetime.fromisoformat(value)
                    value = dt
                except Exception:
                    return value
            if isinstance(value, datetime):
                adjusted = value + timedelta(hours=5)
                return adjusted.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
        except Exception:
            return str(value)
        return str(value)

    def _coerce_to_datetime(self, value):
        """Coerce a date/iso string into a datetime for writing into date_planned."""
        if not value:
            return False
        try:
            if isinstance(value, datetime):
                return value
            if isinstance(value, date):
                return datetime.combine(value, datetime.min.time())
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except Exception:
                    return False
        except Exception:
            return False
        return False

    def _get_terms_section(self):
        """Return a dict with 'html' and 'items' for Terms and Conditions based on
        fields defined on purchase.quotation related to this PO (origin).
        """
        def yes(v):
            return 'Yes' if v else 'No'

        Quotation = self.env['purchase.quotation'].sudo()
        quotation = False
        # 1) Typical linkage used in this module: PO.origin stores the RFQ origin
        if self.origin:
            quotation = Quotation.search([('rfq_origin', '=', self.origin)], limit=1)
        # 2) Some flows may set rfq_origin to the PO number instead
        if not quotation and self.name:
            quotation = Quotation.search([('rfq_origin', '=', self.name)], limit=1)
        # 3) Fallback: match by PR name copied on the PO
        if not quotation and getattr(self, 'pr_name', False):
            quotation = Quotation.search([('pr_name', '=', self.pr_name)], limit=1)
        if not quotation:
            return {'html': '', 'items': []}

        # Build items list (label, value)
        items = []
        # Payment Terms
        pt_parts = []
        if quotation.terms_net:
            pt_parts.append('Net')
        if quotation.terms_30days:
            pt_parts.append('30 Days')
        if quotation.terms_advance:
            adv = quotation.terms_advance_specify or '% Advance'
            pt_parts.append(adv)
        if quotation.terms_delivery:
            pt_parts.append('On Delivery')
        if quotation.terms_other:
            other = quotation.terms_others_specify or 'Other'
            pt_parts.append(other)
        if pt_parts:
            items.append(('Payment Terms', ', '.join(pt_parts)))

        # Production / Material Availability
        prod_parts = []
        if quotation.ex_stock:
            prod_parts.append('Ex-Stock')
        if quotation.required_days:
            txt = quotation.production_days or 'Production Required'
            prod_parts.append(txt)
        if prod_parts:
            items.append(('Production / Availability', ', '.join(prod_parts)))

        # Delivery Terms
        deliv_terms = []
        if quotation.ex_work:
            deliv_terms.append('Ex-Works')
        if quotation.delivery_site:
            deliv_terms.append('Site Delivery')
        if deliv_terms:
            items.append(('Delivery Terms', ', '.join(deliv_terms)))

        # Delivery Date Expected
        if quotation.delivery_date:
            items.append(('Delivery Date Expected', str(quotation.delivery_date)))

        # Delivery Method
        deliv_methods = []
        if quotation.delivery_courier:
            deliv_methods.append('Courier')
        if quotation.delivery_pickup:
            deliv_methods.append('Pickup')
        if quotation.delivery_freight:
            deliv_methods.append('Freight')
        if quotation.delivery_others:
            other = quotation.delivery_others_specify or 'Other'
            deliv_methods.append(other)
        if deliv_methods:
            items.append(('Delivery Method', ', '.join(deliv_methods)))

        # Partial Order Acceptance
        if quotation.partial_yes or quotation.partial_no:
            label_val = 'Yes' if quotation.partial_yes else 'No'
            items.append(('Partial Order Acceptable', label_val))

        # Notes / Additional information
        notes_val = getattr(quotation, 'notes', False)
        if notes_val:
            items.append(('Additional Information / Notes', notes_val))

        if not items:
            return {'html': '', 'items': []}

        # Build HTML block
        row_html = ''.join([f"<tr><td style='width:30%;'><strong>{label}</strong></td><td>{value}</td></tr>" for label, value in items])
        html = f"""
        <h3 style=\"margin-top:24px;\">Terms and Conditions</h3>
        <table border=\"1\" cellspacing=\"0\" cellpadding=\"6\" style=\"border-collapse:collapse; width:100%;\">{row_html}</table>
        """
        return {'html': html, 'items': items}
