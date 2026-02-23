/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function parseBoolean(formData, name) {
    return formData.has(name) ? true : false;
}

function normalizeType(raw) {
    const val = (raw || "").toString().toLowerCase().trim();
    if (val.startsWith("serv")) return "service";
    return "material";
}

// Expose helpers for inline handlers in template
let lineIndex = 1;
function computeRowTotal(row) {
    const qtyEl = row.querySelector('input[name^="product_quantity_"]');
    const priceEl = row.querySelector('input[name^="product_price_"]');
    const totalEl = row.querySelector('input[name^="product_total_"]');
    const qty = parseFloat((qtyEl && qtyEl.value) || '0') || 0;
    const price = parseFloat((priceEl && priceEl.value) || '0') || 0;
    const total = qty * price;
    if (totalEl) totalEl.value = total.toFixed(2);
}

function updateTotalAmount() {
    const totals = Array.from(document.querySelectorAll('#quotation_lines_body input[name^="product_total_"]'));
    const sum = totals.reduce((acc, el) => acc + (parseFloat(el.value || '0') || 0), 0);
    const totalAmount = document.getElementById('total_amount');
    if (totalAmount) totalAmount.value = sum.toFixed(2);
}

function wireRowEvents(row) {
    ['input', 'change'].forEach((evt) => {
        row.addEventListener(evt, function(e) {
            if (e.target && (e.target.name.includes('product_quantity_') || e.target.name.includes('product_price_'))) {
                computeRowTotal(row);
                updateTotalAmount();
            }
        });
    });
    computeRowTotal(row);
}

function addLine() {
    lineIndex++;
    const tbody = document.getElementById("quotation_lines_body");
    if (!tbody) return;
    const tr = document.createElement("tr");
    tr.innerHTML = `
        <td><input type="text" name="product_description_${lineIndex}" class="form-control"/></td>
        <td><input type="number" step="0.01" name="product_quantity_${lineIndex}" class="form-control"/></td>
        <td><input type="text" name="product_type_${lineIndex}" class="form-control"/></td>
        <td><input type="text" name="product_unit_${lineIndex}" class="form-control"/></td>
        <td><input type="number" step="0.01" name="product_price_${lineIndex}" class="form-control"/></td>
        <td><input type="number" step="0.01" name="product_total_${lineIndex}" class="form-control" readonly="readonly"/></td>
        <td><button type="button" class="btn btn-danger btn-sm p-1" title="Remove" aria-label="Remove">&times;</button></td>
    `;
    tbody.appendChild(tr);
    // remove handler
    tr.querySelector('button').addEventListener('click', () => {
        tr.remove();
        updateTotalAmount();
    });
    wireRowEvents(tr);
    updateTotalAmount();
}

// Make globally available for inline onclick in template
window.addLine = addLine;
window.updateTotalAmount = updateTotalAmount;

class QuotationFormPage extends Component {
    setup() {
        this.rpc = useService('rpc');
        this.action = useService('action');
        this.state = useState({ rfqs: [], vendors: [] });
        onMounted(() => {
            // Wire first row
            const firstRow = document.querySelector('#quotation_lines_body tr');
            if (firstRow) wireRowEvents(firstRow);
            updateTotalAmount();
            this.loadRfqs();
            this.loadVendors();
            // Enforce exclusive selections and conditional enables
            this._initTermsUiLogic();
            // Wire RFQ Origin change → auto populate header + lines
            const rfqInput = document.querySelector('input[name="rfq_origin"], select[name="rfq_origin"]');
            if (rfqInput) {
                rfqInput.addEventListener('change', async (e) => {
                    const rfqName = e.target && e.target.value;
                    await this.populateFromRfqName(rfqName);
                });
            }
            // Wire Vendor change → populate vendor-based fields
            const vendorInput = document.querySelector('input[name="supplier_name"]');
            if (vendorInput) {
                vendorInput.addEventListener('change', async (e) => {
                    const vendorName = (e.target && e.target.value) || '';
                    await this.populateFromVendorName(vendorName);
                });
            }
        });
    }

    async loadRfqs() {
        try {
            const rfqs = await this.rpc('/web/dataset/call_kw', {
                model: 'purchase.order',
                method: 'search_read',
                args: [[['state', 'in', ['draft', 'sent']]]],
                kwargs: { fields: ['id', 'name'], limit: 200 },
            });
            this.state.rfqs = rfqs || [];
        } catch (e) {
            console.error('Failed to load RFQs', e);
            this.state.rfqs = [];
        }
    }

    async loadVendors() {
        try {
            const vendors = await this.rpc('/web/dataset/call_kw', {
                model: 'res.partner',
                method: 'search_read',
                args: [[['active', '=', true]]],
                kwargs: { fields: ['id', 'name', 'email', 'phone'], limit: 500 },
            });
            this.state.vendors = vendors || [];
        } catch (e) {
            console.error('Failed to load vendors', e);
            this.state.vendors = [];
        }
    }

    async _loadRfqMetaByName(rfqName) {
        if (!rfqName) return null;
        try {
            const recs = await this.rpc('/web/dataset/call_kw', {
                model: 'purchase.order',
                method: 'search_read',
                args: [[['name', '=', rfqName]]],
                kwargs: {
                    fields: [
                        'id', 'name', 'project_id', 'budget_type', 'budget_code',
                        'pr_name', 'requested_by', 'department', 'supervisor', 'supervisor_partner_id',
                    ],
                    limit: 1,
                },
            });
            return (recs && recs[0]) || null;
        } catch (e) {
            console.error('Failed to load RFQ meta for', rfqName, e);
            return null;
        }
    }

    async populateFromRfqName(rfqName) {
        if (!rfqName) return;
        // Fetch the RFQ/PO record first
        let po;
        try {
            const recs = await this.rpc('/web/dataset/call_kw', {
                model: 'purchase.order',
                method: 'search_read',
                args: [[['name', '=', rfqName]]],
                kwargs: { fields: ['id','name','partner_id','partner_ref','date_planned','date_order','custom_line_ids','order_line'], limit: 1 },
            });
            po = (recs && recs[0]) || null;
        } catch (e) {
            console.error('Failed to load RFQ by name', rfqName, e);
            po = null;
        }
        if (!po) return;

        // Populate some header inputs if present
        const setIfExists = (name, val) => {
            const el = document.querySelector(`[name="${name}"]`);
            if (el) el.value = val || '';
        };
        const toDateInput = (v) => {
            if (!v) return '';
            const s = (v || '').toString();
            const pad2 = (n) => (n < 10 ? '0' + n : '' + n);
            // helper: add 5 hours then format local date parts
            const fmtPlus5h = (dateObj) => {
                const d2 = new Date(dateObj.getTime() + 5 * 60 * 60 * 1000);
                return `${d2.getFullYear()}-${pad2(d2.getMonth() + 1)}-${pad2(d2.getDate())}`;
            };

            // If 'YYYY-MM-DD' or starts with that, add +5h from midnight local
            const m = s.match(/^(\d{4}-\d{2}-\d{2})/);
            if (m) {
                const d0 = new Date(m[1] + 'T00:00:00');
                if (!isNaN(d0)) return fmtPlus5h(d0);
                return m[1];
            }
            // Otherwise parse and format in LOCAL time then add +5h
            try {
                const d = new Date(s.replace(' ', 'T'));
                if (!isNaN(d)) return fmtPlus5h(d);
            } catch (e) {}
            return '';
        };

        setIfExists('vendor_ref', po.partner_ref || '');
        setIfExists('quotation_ref', po.name || rfqName || '');
        if (po.partner_id && po.partner_id[1]) setIfExists('supplier_name', po.partner_id[1]);
        if (po.partner_id && po.partner_id[1]) await this.populateFromVendorName(po.partner_id[1]);

        // Expected Arrival: patch from RFQ/PO date_planned in YYYY-MM-DD (with +5h adjustment)
        setIfExists('expected_arrival', toDateInput(po.date_planned || headerDatePlanned));

        // Fetch lines: prefer custom_line_ids
        const lines = [];
        let headerDatePlanned = po.date_planned || null;
        let minLineDatePlanned = null;
        try {
            if (po.custom_line_ids && po.custom_line_ids.length) {
                const clines = await this.rpc('/web/dataset/call_kw', {
                    model: 'purchase.order.custom.line',
                    method: 'read',
                    args: [po.custom_line_ids, ['name','quantity','unit','type','price_unit']],
                    kwargs: {},
                });
                for (const ln of (clines || [])) {
                    lines.push({
                        description: ln.name || '',
                        quantity: ln.quantity || 0,
                        type: ln.type || '',
                        unit: ln.unit || '',
                        price: ln.price_unit || 0,
                    });
                }
            } else if (po.order_line && po.order_line.length) {
                const olines = await this.rpc('/web/dataset/call_kw', {
                    model: 'purchase.order.line',
                    method: 'read',
                    args: [po.order_line, ['name','product_id','product_qty','product_uom','price_unit','date_planned']],
                    kwargs: {},
                });
                for (const ln of (olines || [])) {
                    if (ln.date_planned) {
                        const d = new Date(ln.date_planned);
                        if (!isNaN(d)) {
                            const iso = d.toISOString();
                            if (!minLineDatePlanned || new Date(minLineDatePlanned) > d) {
                                minLineDatePlanned = iso;
                            }
                        } else if (!minLineDatePlanned) {
                            minLineDatePlanned = ln.date_planned;
                        }
                    }
                    lines.push({
                        description: ln.name || (ln.product_id && ln.product_id[1]) || '',
                        quantity: ln.product_qty || 0,
                        type: normalizeType((ln.product_id && ln.product_id[1]) || 'material'),
                        unit: (ln.product_uom && ln.product_uom[1]) || '',
                        price: ln.price_unit || 0,
                    });
                }
            }
        } catch (e) {
            console.error('Failed to load RFQ lines', e);
        }

        // Populate table rows
        try {
            const tbody = document.getElementById('quotation_lines_body');
            if (!tbody) return;
            // reset
            tbody.innerHTML = '';
            lineIndex = 0;
            const makeRow = (ln) => {
                lineIndex++;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><input type="text" name="product_description_${lineIndex}" class="form-control"/></td>
                    <td><input type="number" step="0.01" name="product_quantity_${lineIndex}" class="form-control"/></td>
                    <td><input type="text" name="product_type_${lineIndex}" class="form-control"/></td>
                    <td><input type="text" name="product_unit_${lineIndex}" class="form-control"/></td>
                    <td><input type="number" step="0.01" name="product_price_${lineIndex}" class="form-control"/></td>
                    <td><input type="number" step="0.01" name="product_total_${lineIndex}" class="form-control" readonly="readonly"/></td>
                    <td><button type="button" class="btn btn-danger btn-sm p-1" title="Remove" aria-label="Remove">&times;</button></td>
                `;
                tbody.appendChild(tr);
                // set values
                tr.querySelector(`input[name="product_description_${lineIndex}"]`).value = ln.description || '';
                tr.querySelector(`input[name="product_quantity_${lineIndex}"]`).value = (ln.quantity || 0);
                tr.querySelector(`input[name="product_type_${lineIndex}"]`).value = ln.type || '';
                tr.querySelector(`input[name="product_unit_${lineIndex}"]`).value = ln.unit || '';
                tr.querySelector(`input[name="product_price_${lineIndex}"]`).value = (ln.price || 0);
                wireRowEvents(tr);
            };
            if (lines.length) {
                for (const ln of lines) makeRow(ln);
            } else {
                // Create a single empty row if no lines found
                makeRow({});
            }
            updateTotalAmount();
        } catch (e) {
            console.error('Failed to populate lines table', e);
        }
    }

    async populateFromVendorName(vendorName) {
        if (!vendorName) return;
        let partner = null;
        try {
            const partners = await this.rpc('/web/dataset/call_kw', {
                model: 'res.partner',
                method: 'search_read',
                args: [[['name', '=', vendorName]]],
                kwargs: { fields: ['id','name','email','phone','vat','contact_address','street','street2','city','zip','state_id','country_id'], limit: 1 },
            });
            partner = (partners && partners[0]) || null;
        } catch (e) {
            console.error('Failed to resolve vendor by name', vendorName, e);
            partner = null;
        }
        if (!partner) return;

        const setIfExists = (name, val) => {
            const el = document.querySelector(`[name="${name}"]`);
            if (el) el.value = val || '';
        };

        // Compose address if contact_address not available
        const addr = partner.contact_address || [partner.street, partner.street2, partner.city, partner.zip, (partner.state_id && partner.state_id[1]) || '', (partner.country_id && partner.country_id[1]) || ''].filter(Boolean).join(', ');

        setIfExists('company_address', addr);
        setIfExists('email_address', partner.email || '');
        setIfExists('phone_number', partner.phone || '');
        setIfExists('supplier_id', partner.vat || '');
        setIfExists('contact_person', partner.name || '');
    }

    async save(ev) {
        if (ev && ev.preventDefault) ev.preventDefault();
        const btn = ev && ev.currentTarget ? ev.currentTarget : null;
        let form = null;
        if (btn && btn.closest) {
            form = btn.closest('form');
        }
        if (!form && this.el) {
            if (this.el.tagName && this.el.tagName.toLowerCase() === 'form') {
                form = this.el;
            } else if (this.el.closest) {
                form = this.el.closest('form');
            } else if (this.el.querySelector) {
                form = this.el.querySelector('form');
            }
        }
        if (!form) {
            form = document.querySelector('form.quotation-form') || document.querySelector('form');
        }
        if (!form) {
            console.error('Quotation form element not found');
            alert('Unable to find the quotation form in the page.');
            return;
        }
        const fd = new FormData(form);

        // Client-side required validation with alerts
        const requiredChecks = [];
        const addCheck = (ok, msg) => { if (!ok) requiredChecks.push(msg); };

        // Supplier Name, Email, Quotation Ref, Expected Arrival (Quotation Date), Quotation Valid Till
        addCheck((fd.get('supplier_name') || '').toString().trim().length > 0, 'Supplier Name is required');
        addCheck((fd.get('email_address') || '').toString().trim().length > 0, 'Email Address is required');
        addCheck((fd.get('quotation_ref') || '').toString().trim().length > 0, 'Quotation Ref No is required');
        addCheck((fd.get('expected_arrival') || '').toString().trim().length > 0, 'Quotation Date (Expected Arrival) is required');
        addCheck((fd.get('quotation_valid_till') || '').toString().trim().length > 0, 'Quotation Valid Till is required');

        // Terms: now exactly one selection per group
        const paymentCount = ['terms_net','terms_30days','terms_advance','terms_delivery','terms_other'].reduce((n, k) => n + (fd.has(k) ? 1 : 0), 0);
        addCheck(paymentCount === 1, 'Select exactly one Payment Term');

        const prodCount = ['ex_stock','required_days'].reduce((n, k) => n + (fd.has(k) ? 1 : 0), 0);
        addCheck(prodCount === 1, 'Select exactly one Production/Material Availability option');

        const delivTermsCount = ['ex_work','delivery_site'].reduce((n, k) => n + (fd.has(k) ? 1 : 0), 0);
        addCheck(delivTermsCount === 1, 'Select exactly one Delivery Term');

        // Delivery Date Expected
        addCheck((fd.get('delivery_date') || '').toString().trim().length > 0, 'Delivery Date Expected is required');

        // Delivery Method (exactly one)
        const delivMethodCount = ['courier','pickup','freight','delivery_others'].reduce((n, k) => n + (fd.has(k) ? 1 : 0), 0);
        addCheck(delivMethodCount === 1, 'Select exactly one Delivery Method');

        // Partial Order Acceptable (exactly one of yes/no)
        const partialYes = fd.has('partial_yes');
        const partialNo = fd.has('partial_no');
        addCheck((partialYes ? 1 : 0) + (partialNo ? 1 : 0) === 1, 'Select exactly one: Partial Order acceptable Yes/No');

        // Conditional specifies
        if (fd.has('terms_advance')) {
            addCheck((fd.get('terms_advance_specify') || '').toString().trim().length > 0, 'Specify % for Advance');
        }
        if (fd.has('terms_other')) {
            addCheck((fd.get('terms_others_specify') || '').toString().trim().length > 0, 'Specify Other Payment Term');
        }
        if (fd.has('required_days')) {
            addCheck((fd.get('production_days') || '').toString().trim().length > 0, 'Specify Required Days for Production/Import');
        }
        if (fd.has('delivery_others')) {
            addCheck((fd.get('delivery_others_specify') || '').toString().trim().length > 0, 'Specify Other Delivery Method');
        }

        if (requiredChecks.length) {
            alert(requiredChecks[0]);
            return;
        }

        // Header values mapping to purchase.quotation
        const rfqOrigin = fd.get('rfq_origin') || null;
        const rfqMeta = await this._loadRfqMetaByName(rfqOrigin);

        const quotationVals = {
            rfq_origin: rfqOrigin,
            vendor_ref: fd.get('vendor_ref') || null,
            // If supplier_name matches a known contact, set vendor_id
            ...(function() {
                const name = (fd.get('supplier_name') || '').toString().trim();
                const match = (name && Array.isArray(this.state.vendors)) ? this.state.vendors.find(v => v.name === name) : null;
                return match ? { vendor_id: match.id } : {};
            }).call(this),
            supplier_name: fd.get('supplier_name') || null,
            contact_person: fd.get('contact_person') || null,
            company_address: fd.get('company_address') || null,
            phone_number: fd.get('phone_number') || null,
            email_address: fd.get('email_address') || null,
            supplier_id: fd.get('supplier_id') || null,
            quotation_ref: fd.get('quotation_ref') || null,
            order_deadline: fd.get('quotation_valid_till') || null,
            expected_arrival: fd.get('expected_arrival') || null,
            // Payment Terms
            terms_net: parseBoolean(fd, 'terms_net'),
            terms_30days: parseBoolean(fd, 'terms_30days'),
            terms_advance: parseBoolean(fd, 'terms_advance'),
            terms_advance_specify: fd.get('terms_advance_specify') || null,
            terms_delivery: parseBoolean(fd, 'terms_delivery'),
            terms_other: parseBoolean(fd, 'terms_other'),
            terms_others_specify: fd.get('terms_others_specify') || null,
            // Production / Availability
            ex_stock: parseBoolean(fd, 'ex_stock'),
            required_days: parseBoolean(fd, 'required_days'),
            production_days: fd.get('production_days') || null,
            // Delivery terms
            ex_work: parseBoolean(fd, 'ex_work'),
            delivery_site: parseBoolean(fd, 'delivery_site'),
            // Delivery date
            delivery_date: fd.get('delivery_date') || null,
            // Delivery method mapping
            delivery_courier: parseBoolean(fd, 'courier'),
            delivery_pickup: parseBoolean(fd, 'pickup'),
            delivery_freight: parseBoolean(fd, 'freight'),
            delivery_others: parseBoolean(fd, 'delivery_others'),
            delivery_others_specify: fd.get('delivery_others_specify') || null,
            // Partial order acceptable
            partial_yes: parseBoolean(fd, 'partial_yes'),
            partial_no: parseBoolean(fd, 'partial_no'),
            // Notes
            notes: fd.get('description') || null,
        };

        // Patch project/budget fields from RFQ if found
        if (rfqMeta) {
            if (rfqMeta.project_id && rfqMeta.project_id[0]) {
                quotationVals.project_id = rfqMeta.project_id[0];
            }
            if (rfqMeta.budget_type) quotationVals.budget_type = rfqMeta.budget_type;
            if (rfqMeta.budget_code) quotationVals.budget_code = rfqMeta.budget_code;
            if (rfqMeta.pr_name) quotationVals.pr_name = rfqMeta.pr_name;
            if (rfqMeta.requested_by) quotationVals.requested_by = rfqMeta.requested_by;
            if (rfqMeta.department) quotationVals.department = rfqMeta.department;
            if (rfqMeta.supervisor) quotationVals.supervisor = rfqMeta.supervisor;
            if (rfqMeta.supervisor_partner_id) quotationVals.supervisor_partner_id = rfqMeta.supervisor_partner_id;
        }

        // Create quotation
        let quotationId;
        try {
            quotationId = await this.rpc('/web/dataset/call_kw', {
                model: 'purchase.quotation',
                method: 'create',
                args: [quotationVals],
                kwargs: {},
            });
        } catch (e) {
            console.error('Failed to create quotation', e);
            alert('Failed to save quotation header.');
            return;
        }

        // Collect line items
        const rows = Array.from(document.querySelectorAll('#quotation_lines_body tr'));

        // Validate each line has Description, Quantity (>0), Type, Unit, Unit Price (>0)
        if (rows.length === 0) {
            alert('Add at least one Quotation Line');
            return;
        }
        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            const get = (sel) => {
                const el = row.querySelector(sel); return el ? el.value : '';
            };
            const description = (get('input[name^="product_description_"]') || '').trim();
            const quantity = parseFloat(get('input[name^="product_quantity_"]') || '0');
            const type = (get('input[name^="product_type_"]') || '').trim();
            const unit = (get('input[name^="product_unit_"]') || '').trim();
            const price = parseFloat(get('input[name^="product_price_"]') || '0');
            if (!description) { alert(`Line ${i+1}: Item Description is required`); return; }
            if (!(quantity > 0)) { alert(`Line ${i+1}: Quantity must be greater than 0`); return; }
            if (!type) { alert(`Line ${i+1}: Type is required`); return; }
            if (!unit) { alert(`Line ${i+1}: Unit is required`); return; }
            if (!(price > 0)) { alert(`Line ${i+1}: Unit Price must be greater than 0`); return; }
        }
        const lineCreates = [];
        for (const row of rows) {
            const get = (selector) => {
                const el = row.querySelector(selector);
                return el ? el.value : '';
            };
            const description = get('input[name^="product_description_"]');
            const quantity = parseFloat(get('input[name^="product_quantity_"]') || '0') || 0;
            const unit = get('input[name^="product_unit_"]');
            const price = parseFloat(get('input[name^="product_price_"]') || '0') || 0;
            const typeRaw = get('input[name^="product_type_"]');
            if (!description) continue; // skip empty
            const vals = {
                quotation_id: quotationId,
                name: description, // product name into description field
                quantity: quantity,
                unit: unit || null,
                type: normalizeType(typeRaw),
                price_unit: price,
            };
            lineCreates.push(this.rpc('/web/dataset/call_kw', {
                model: 'purchase.quotation.line',
                method: 'create',
                args: [vals],
                kwargs: {},
            }));
        }

        try {
            await Promise.all(lineCreates);
        } catch (e) {
            console.error('Failed to create one or more quotation lines', e);
            alert('Quotation header saved, but some lines failed to save.');
            return;
        }

        // Redirect to Purchase RFQs after success
        try {
            await this.action.doAction('purchase.purchase_rfq');
        } catch (e) {
            // Fallback: navigate to Purchase app
            window.location.href = '/web#cids=1&menu_id=115&action=purchase.purchase_rfq';
        }
    }

    _initTermsUiLogic() {
        // Generic exclusive group binder
        const bindExclusive = (names, onToggle = null) => {
            const inputs = names.map((n) => document.querySelector(`input[name="${n}"]`)).filter(Boolean);
            const uncheckOthers = (current) => {
                inputs.forEach((inp) => { if (inp !== current) inp.checked = false; });
                if (typeof onToggle === 'function') onToggle();
            };
            inputs.forEach((inp) => {
                inp.addEventListener('change', () => { if (inp.checked) uncheckOthers(inp); else { if (typeof onToggle === 'function') onToggle(); } });
            });
            // Initial
            if (typeof onToggle === 'function') onToggle();
        };

        // Enable/disable helper
        const toggleEnable = (selector, enabled) => {
            const el = document.querySelector(selector);
            if (!el) return;
            el.disabled = !enabled;
            if (!enabled) el.value = '';
        };

        // Payment Terms exclusive group
        bindExclusive(['terms_net','terms_30days','terms_advance','terms_delivery','terms_other'], () => {
            const adv = document.querySelector('input[name="terms_advance"]').checked;
            const oth = document.querySelector('input[name="terms_other"]').checked;
            toggleEnable('input[name="terms_advance_specify"]', adv);
            toggleEnable('input[name="terms_others_specify"]', oth);
        });

        // Production / Availability exclusive
        bindExclusive(['ex_stock','required_days'], () => {
            const req = document.querySelector('input[name="required_days"]').checked;
            toggleEnable('input[name="production_days"]', req);
        });

        // Delivery Terms exclusive
        bindExclusive(['ex_work','delivery_site']);

        // Delivery Method exclusive
        bindExclusive(['courier','pickup','freight','delivery_others'], () => {
            const other = document.querySelector('input[name="delivery_others"]').checked;
            toggleEnable('input[name="delivery_others_specify"]', other);
        });

        // Partial Order Acceptable exclusive
        bindExclusive(['partial_yes','partial_no']);
    }
}

QuotationFormPage.template = "pr_custom_purchase.QuotationFormTemplate";

registry.category("actions").add("quotation_form_page", QuotationFormPage);