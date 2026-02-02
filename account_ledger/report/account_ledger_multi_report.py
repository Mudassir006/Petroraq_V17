# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, models
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT


class AccountLedgerMultiReport(models.AbstractModel):
    _name = "report.account_ledger.account_ledger_multi_rep"

    def _get_valuation_dates(self, start_date, end_date):
        date_start = datetime.strptime(start_date, DATE_FORMAT).date()
        date_end = datetime.strptime(end_date, DATE_FORMAT).date()
        return f"{date_start} To {date_end}"

    def _build_account_docs(self, account_id, data, analytic_ids, str_analytic_ids):
        date_start = data["form"]["date_start"]
        date_end = data["form"]["date_end"]
        company = data["form"]["company"]
        department = data["form"].get("department")
        section = data["form"].get("section")
        project = data["form"].get("project")
        employee = data["form"].get("employee")
        asset = data["form"].get("asset")

        ji_domain = [
            ("company_id", "=", company),
            ("date", ">=", datetime.strptime(date_start, DATE_FORMAT).date()),
            ("date", "<=", datetime.strptime(date_end, DATE_FORMAT).date()),
            ("move_id.state", "=", "posted"),
            ("account_id", "=", account_id),
        ]
        opening_balance_domain = [
            ("company_id", "=", company),
            ("date", ">=", datetime.strptime(date_start, DATE_FORMAT).date()),
            ("date", "<=", datetime.strptime(date_end, DATE_FORMAT).date()),
            ("move_id.state", "=", "posted"),
            ("account_id", "=", account_id),
        ]

        if analytic_ids:
            opening_balance_domain.append(("analytic_distribution", "in", analytic_ids))
        if department:
            ji_domain.append(("analytic_distribution", "in", [int(department)]))

        journal_items = self.env["account.move.line"].search(ji_domain, order="date asc")

        if journal_items and section:
            journal_items = self.env["account.move.line"].search(
                [("id", "in", journal_items.ids), ("analytic_distribution", "in", [int(section)])], order="date asc"
            )
        if journal_items and project:
            journal_items = self.env["account.move.line"].search(
                [("id", "in", journal_items.ids), ("analytic_distribution", "in", [int(project)])], order="date asc"
            )
        if journal_items and employee:
            journal_items = self.env["account.move.line"].search(
                [("id", "in", journal_items.ids), ("analytic_distribution", "in", [int(employee)])], order="date asc"
            )
        if journal_items and asset:
            journal_items = self.env["account.move.line"].search(
                [("id", "in", journal_items.ids), ("analytic_distribution", "in", [int(asset)])], order="date asc"
            )

        where_statement = f"""
            WHERE aml.account_id = {account_id}
            AND
            aml.date < '{date_start}'
            AND am.state = 'posted'"""

        if analytic_ids:
            if "WHERE" in where_statement:
                where_statement += f""" AND
                    analytic_distribution ?& array{str_analytic_ids}"""
            else:
                where_statement += f""" WHERE
                    analytic_distribution ?& array{str_analytic_ids}"""

        sql = f"""
            SELECT
                SUM(aml.balance)
            FROM
                account_move_line aml
            JOIN
                account_move am ON aml.move_id = am.id
            {where_statement}
            GROUP BY aml.account_id
        """
        self.env.cr.execute(sql)
        result = self.env.cr.fetchone()
        initial_balance = result[0] if result and result[0] else 0

        t_debit = 0
        t_credit = 0
        init_balance = initial_balance
        opening_debit = initial_balance if initial_balance > 0 else 0
        opening_credit = abs(initial_balance) if initial_balance < 0 else 0

        docs = [
            {
                "transaction_ref": "Opening",
                "date": date_start,
                "description": "Opening Balance",
                "reference": " ",
                "journal": " ",
                "initial_balance": "{:,.2f}".format(initial_balance),
                "debit": "{:,.2f}".format(opening_debit),
                "credit": "{:,.2f}".format(opening_credit),
                "balance": "{:,.2f}".format(initial_balance),
            }
        ]

        for item in journal_items:
            balance = initial_balance + (item.debit - item.credit)
            t_debit += item.debit
            t_credit += item.credit
            docs.append(
                {
                    "transaction_ref": item.move_id.name,
                    "date": item.date,
                    "description": item.name,
                    "reference": item.ref,
                    "journal": item.journal_id.name,
                    "initial_balance": "{:,.2f}".format(initial_balance),
                    "debit": "{:,.2f}".format(item.debit),
                    "credit": "{:,.2f}".format(item.credit),
                    "balance": "{:,.2f}".format(balance),
                }
            )
            initial_balance = balance

        docs.append(
            {
                "transaction_ref": False,
                "date": " ",
                "description": " ",
                "reference": " ",
                "journal": " ",
                "initial_balance": "{:,.2f}".format(init_balance),
                "debit": "{:,.2f}".format(t_debit),
                "credit": "{:,.2f}".format(t_credit),
                "balance": "{:,.2f}".format(init_balance + t_debit - t_credit),
            }
        )

        return docs

    @api.model
    def _get_report_values(self, docids, data=None):
        account_ids = data["form"]["account"]
        date_start = data["form"]["date_start"]
        date_end = data["form"]["date_end"]
        company = data["form"]["company"]

        analytic_ids = []
        str_analytic_ids = []
        for key in ("department", "section", "project", "employee", "asset"):
            if data["form"].get(key):
                analytic_ids.append(int(data["form"][key]))
                str_analytic_ids.append(str(data["form"][key]))

        report_date = datetime.today().strftime("%b-%d-%Y")
        company_name = self.env["res.company"].browse(company).name
        account_names = ", ".join(self.env["account.account"].browse(account_ids).mapped("name"))

        accounts = []
        for account_id in account_ids:
            account = self.env["account.account"].browse(account_id)
            accounts.append(
                {
                    "account_name": account.display_name,
                    "docs": self._build_account_docs(account_id, data, analytic_ids, str_analytic_ids),
                }
            )

        return {
            "doc_ids": data["ids"],
            "doc_model": data["model"],
            "valuation_date": self._get_valuation_dates(date_start, date_end),
            "account": f"{company_name} - {account_names}" if account_names else company_name,
            "report_date": report_date,
            "accounts": accounts,
        }
