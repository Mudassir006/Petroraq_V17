# PR Retention Management

This module adds a **Construction Retention** workflow so you can record retention (holdback) amounts against construction contracts and release them over time. Retention is typically a percentage of the contract value withheld from payments until specific milestones or completion are achieved. It integrates with **Sales Orders** and **Customer Invoices** so holdbacks are created automatically when invoices are posted.

## What the module does
- Create retention records linked to **Work Orders**, **Sale Orders**, **Projects**, and **Customers**.
- Calculate retention by **percentage** or by **fixed amount**.
- Track **withheld** (from invoices), **released**, and **remaining** retention via lines.
- Simple lifecycle: **Draft → Active → Closed/Cancelled**.
- Push retention settings from **Sale Orders** to **Customer Invoices** automatically.

## Installation
1. Copy the `pr_retention` module into your Odoo addons path.
2. Update the Apps list.
3. Install **PR Retention Management**.

## Configuration
No extra configuration is required.

## Usage
1. On a **Sale Order**, go to the **Retention** tab and enable **Apply Retention**.
2. Choose **Retention Type**:
   - **Percentage**: enter **Retention (%)**.
   - **Fixed Amount**: enter **Retention Fixed Amount**.
3. Confirm the Sale Order and create a customer invoice.
4. When you **Post** the invoice, a holdback line is created automatically in the linked retention record.
5. Go to **Work Orders → Retentions** to review withheld amounts.
6. Confirm the retention to make it **Active** (optional if already active).
7. Add **Release Lines** as you pay back retention to the customer:
   - Enter release date, amount, and note.
   - Click **Release** on each line to mark it released.
8. When the **Amount Remaining** reaches 0, click **Close**.

## Field guide
- **Base Amount**: Contract or sale amount used for calculating retention percentage.
- **Retention Amount**: Computed holdback value.
- **Amount Withheld**: Sum of invoice holdbacks.
- **Amount Released**: Sum of released lines.
- **Amount Remaining**: Withheld retention still held back.

## Testing checklist
- Create a retention with **percentage** and verify the computed amount.
- Create a retention with **fixed amount** and verify the computed amount.
- Post an invoice and verify the holdback line shows under **Invoice Holdbacks**.
- Release lines until remaining is zero, then close the retention.
- Attempt to release more than remaining to confirm validation works.

## Notes
- This module does not post accounting entries. It focuses on operational tracking.
- Use your accounting workflow to handle retention invoicing/payment entries if required.
