# PR Retention Management

This module adds a **Construction Retention** workflow so you can record retention (holdback) amounts against construction contracts and release them over time. Retention is typically a percentage of the contract value withheld from payments until specific milestones or completion are achieved.

## What the module does
- Create retention records linked to **Work Orders**, **Sale Orders**, **Projects**, and **Customers**.
- Calculate retention by **percentage** or by **fixed amount**.
- Track **released** and **remaining** retention via release lines.
- Simple lifecycle: **Draft → Active → Closed/Cancelled**.

## Installation
1. Copy the `pr_retention` module into your Odoo addons path.
2. Update the Apps list.
3. Install **PR Retention Management**.

## Configuration
No extra configuration is required.

## Usage
1. Go to **Work Orders → Retentions**.
2. Click **Create**.
3. Link a **Work Order** or **Sale Order** (optional), or fill the **Base Amount** manually.
4. Choose **Retention Type**:
   - **Percentage**: enter **Retention (%)**.
   - **Fixed Amount**: enter **Retention Fixed Amount**.
5. Confirm the retention to make it **Active**.
6. Add **Release Lines** as you pay back retention to the customer:
   - Enter release date, amount, and note.
   - Click **Release** on each line to mark it released.
7. When the **Amount Remaining** reaches 0, click **Close**.

## Field guide
- **Base Amount**: Contract or sale amount used for calculating retention percentage.
- **Retention Amount**: Computed holdback value.
- **Amount Released**: Sum of released lines.
- **Amount Remaining**: Retention still held back.

## Testing checklist
- Create a retention with **percentage** and verify the computed amount.
- Create a retention with **fixed amount** and verify the computed amount.
- Release lines until remaining is zero, then close the retention.
- Attempt to release more than remaining to confirm validation works.

## Notes
- This module does not post accounting entries. It focuses on operational tracking.
- Use your accounting workflow to handle retention invoicing/payment entries if required.
