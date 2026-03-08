from odoo.tests.common import TransactionCase


class TestPurchaseOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.keep_name_po = False
        cls.partner = cls.env["res.partner"].create({"name": "Test Vendor", "supplier_rank": 1})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Service A",
                "type": "service",
                "purchase_ok": True,
            }
        )

    def test_rfq_and_po_sequences(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": "Service A",
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "product_uom": self.product.uom_po_id.id,
                            "price_unit": 100.0,
                            "date_planned": "2026-01-01 00:00:00",
                        },
                    )
                ],
            }
        )

        self.assertRegex(po.name, r"^PEC/RFQ/\d{4}/\d{4}$")
        rfq_name = po.name

        po.button_confirm()

        self.assertRegex(po.name, r"^PEC/PO/\d{4}/\d{4}$")
        self.assertEqual(po.origin, rfq_name)
