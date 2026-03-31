# pr_vat_summary/reports/vat_summary_xlsx.py
from odoo import models


class VatSummaryXlsx(models.AbstractModel):
    _name = "report.pr_vat_summary.vat_summary_xlsx"
    _inherit = "report.report_xlsx.abstract"

    def _write_detail_section(self, sheet, row, title, lines, header_fmt, cell_left, cell_right):
        sheet.merge_range(row, 0, row, 6, title, header_fmt)
        row += 1
        headers = ["Journal Entry", "Reference", "Date", "Description", "Amount", "VAT Amount", "Total Amount"]
        for col, value in enumerate(headers):
            sheet.write(row, col, value, header_fmt)
        row += 1

        if not lines:
            sheet.merge_range(row, 0, row, 6, "No lines", cell_left)
            row += 1
        else:
            for line in lines:
                sheet.write(row, 0, line.get("entry", ""), cell_left)
                sheet.write(row, 1, line.get("reference", ""), cell_left)
                sheet.write(row, 2, str(line.get("date", "")), cell_left)
                sheet.write(row, 3, line.get("label", ""), cell_left)
                sheet.write_number(row, 4, line.get("amount", 0.0), cell_right)
                sheet.write_number(row, 5, line.get("vat_amount", 0.0), cell_right)
                sheet.write_number(row, 6, line.get("total_amount", 0.0), cell_right)
                row += 1

        total = sum(line.get("amount", 0.0) for line in lines)
        vat_total = sum(line.get("vat_amount", 0.0) for line in lines)
        grand_total = sum(line.get("total_amount", 0.0) for line in lines)
        sheet.merge_range(row, 0, row, 3, "Total", cell_left)
        sheet.write_number(row, 4, total, cell_right)
        sheet.write_number(row, 5, vat_total, cell_right)
        sheet.write_number(row, 6, grand_total, cell_right)
        row += 2
        return row

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[0]

        # recompute exact values used in PDF/HTML
        wizard._compute_vat_summary()

        sales_vat_abs = abs(wizard.sales_vat)
        pur_vat_abs = abs(wizard.vated_purchases_vat)

        sales_total = wizard.sales_amount + sales_vat_abs
        vated_pur_total = wizard.vated_purchases_amount + pur_vat_abs
        non_vated_total = wizard.non_vated_purchases_amount

        amount_total = wizard.total_amount
        vat_total = wizard.total_vat_payable
        grand_total = sales_total - vated_pur_total

        sheet = workbook.add_worksheet("VAT Summary")

        # ---------------------------------------------
        # FORMATS (matching PDF)
        # ---------------------------------------------
        header_fmt = workbook.add_format({
            "bold": True,
            "border": 2,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#29608F",
            "font_color": "white"
        })

        title_fmt = workbook.add_format({
            "bold": True,
            "border": 2,
            "align": "center",
            "valign": "vcenter",
            "font_size": 14
        })

        cell_right = workbook.add_format({
            "border": 2,
            "align": "right"
        })

        cell_center = workbook.add_format({
            "border": 2,
            "align": "center"
        })

        cell_left = workbook.add_format({
            "border": 2,
            "align": "left"
        })

        section_fmt = workbook.add_format({
            "bold": True,
            "border": 2,
            "align": "left",
            "bg_color": "#f5f5f5"
        })

        total_fmt = workbook.add_format({
            "bold": True,
            "border": 2,
            "align": "center"
        })

        # ---------------------------------------------
        # COLUMN WIDTHS
        # ---------------------------------------------
        sheet.set_column(0, 0, 8)
        sheet.set_column(1, 1, 35)
        sheet.set_column(2, 4, 18)

        # ---------------------------------------------
        # TITLE ROW (Merged across 5 columns)
        # ---------------------------------------------
        sheet.merge_range(0, 0, 0, 4,
                          f"VAT Report {wizard.date_start} to {wizard.date_end}",
                          title_fmt)

        # ---------------------------------------------
        # HEADER ROW
        # ---------------------------------------------
        row = 2
        sheet.write(row, 0, "Sr. No", header_fmt)
        sheet.write(row, 1, "Description", header_fmt)
        sheet.write(row, 2, "Amount", header_fmt)
        sheet.write(row, 3, "VAT 15%", header_fmt)
        sheet.write(row, 4, "Total", header_fmt)
        row += 1

        # ---------------------------------------------
        # SALES SECTION
        # ---------------------------------------------
        sheet.write(row, 0, "1", section_fmt)
        sheet.write(row, 1, "Sales:", section_fmt)
        sheet.write(row, 2, "", section_fmt)
        sheet.write(row, 3, "", section_fmt)
        sheet.write(row, 4, "", section_fmt)
        row += 1

        sheet.write(row, 0, "i", cell_center)
        sheet.write(row, 1, "Sales Revenue / Income", cell_left)
        sheet.write_number(row, 2, wizard.sales_amount, cell_right)
        sheet.write_number(row, 3, sales_vat_abs, cell_right)
        sheet.write_number(row, 4, sales_total, cell_right)
        row += 1

        # ---------------------------------------------
        # PURCHASES SECTION
        # ---------------------------------------------
        sheet.write(row, 0, "2", section_fmt)
        sheet.write(row, 1, "Purchases :", section_fmt)
        sheet.write(row, 2, "", section_fmt)
        sheet.write(row, 3, "", section_fmt)
        sheet.write(row, 4, "", section_fmt)
        row += 1

        sheet.write(row, 0, "i", cell_center)
        sheet.write(row, 1, "Vated Purchase/Expenses", cell_left)
        sheet.write_number(row, 2, wizard.vated_purchases_amount, cell_right)
        sheet.write_number(row, 3, pur_vat_abs, cell_right)
        sheet.write_number(row, 4, vated_pur_total, cell_right)
        row += 1

        sheet.write(row, 0, "ii", cell_center)
        sheet.write(row, 1, "Non Vated Purchase/Expenses", cell_left)
        sheet.write_number(row, 2, wizard.non_vated_purchases_amount, cell_right)
        sheet.write(row, 3, "-", cell_center)
        sheet.write_number(row, 4, non_vated_total, cell_right)
        row += 1

        # ---------------------------------------------
        # FINAL TOTAL ROW (exact same as PDF/HTML)
        # ---------------------------------------------
        sheet.merge_range(row, 0, row, 1,
                          "Total VAT Payable / Receivable",
                          section_fmt)

        sheet.write_number(row, 2, amount_total, total_fmt)
        sheet.write_number(row, 3, vat_total, total_fmt)
        sheet.write_number(row, 4, grand_total, total_fmt)

        if wizard.is_detailed:
            details = wizard._prepare_detailed_lines()
            row += 2
            sheet.set_column(0, 0, 20)
            sheet.set_column(1, 1, 20)
            sheet.set_column(2, 2, 14)
            sheet.set_column(3, 3, 40)
            sheet.set_column(4, 6, 18)
            self._write_detail_section(
                sheet, row, "Detailed Transactions", details,
                header_fmt, cell_left, cell_right,
            )
