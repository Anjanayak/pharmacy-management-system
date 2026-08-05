function exportArrayAsCsv(rows, filename) {
  if (!rows || rows.length === 0) {
    alert("Nothing to export yet — load the data first.");
    return;
  }
  const headers = Object.keys(rows[0]);
  const escape = (val) => {
    const s = val === null || val === undefined ? "" : String(val);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [headers.join(",")]
    .concat(rows.map((r) => headers.map((h) => escape(r[h])).join(",")))
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// ---------- Screen switching ----------
function showLogin() {
  document.getElementById("login-screen").style.display = "flex";
  document.getElementById("app-screen").style.display = "none";
}

function showApp() {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("app-screen").style.display = "block";
  const role = localStorage.getItem("pharmacy_role");
  document.getElementById("who-label").textContent =
    `${localStorage.getItem("pharmacy_username")} (${role})`;
  applyRoleVisibility(role);
  navigate("dashboard");
}

// Elements only Admin/Manager may use, per backend RBAC (see auth.py require_roles
// checks in each router). Hiding them for Staff avoids a round-trip 403 and makes
// the UI reflect the same permission model the API already enforces.
const ADMIN_MANAGER_ONLY_IDS = ["medicine-form", "supplier-form", "po-form"];

function applyRoleVisibility(role) {
  const isAdminOrManager = role === "admin" || role === "manager";
  ADMIN_MANAGER_ONLY_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const wrapper = el.closest(".card") || el;
    if (isAdminOrManager) {
      wrapper.style.display = "";
    } else {
      wrapper.style.display = "none";
      const note = document.createElement("p");
      note.className = "role-restricted-note";
      note.style.color = "var(--muted)";
      note.style.fontSize = "0.85rem";
      note.textContent = "Only Admin and Manager roles can perform this action.";
      if (!wrapper.nextElementSibling || !wrapper.nextElementSibling.classList.contains("role-restricted-note")) {
        wrapper.insertAdjacentElement("afterend", note);
      }
    }
  });
}

function flash(elId, message, type = "success") {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = message;
  el.className = `msg-box ${type}`;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 4000);
}

// ---------- Login ----------
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    const data = await api.login(username, password);
    setSession(data.access_token, data.refresh_token, data.role, data.username);
    showApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

document.getElementById("logout-btn").addEventListener("click", () => {
  clearSession();
  showLogin();
});

// ---------- Navigation ----------
const views = ["dashboard", "medicines", "prescriptions", "billing", "suppliers", "alerts", "reports"];

function navigate(viewName) {
  views.forEach((v) => {
    document.getElementById(`view-${v}`).classList.toggle("active", v === viewName);
    document.getElementById(`nav-${v}`).classList.toggle("active", v === viewName);
  });
  const loaders = {
    dashboard: loadDashboard,
    medicines: loadMedicines,
    prescriptions: loadPrescriptions,
    billing: loadBilling,
    suppliers: loadSuppliers,
    alerts: loadAlerts,
    reports: loadReports,
  };
  loaders[viewName] && loaders[viewName]();
}

views.forEach((v) => {
  document.getElementById(`nav-${v}`).addEventListener("click", () => navigate(v));
});

// ---------- Dashboard ----------
async function loadDashboard() {
  const box = document.getElementById("dashboard-stats");
  box.innerHTML = "<p>Loading...</p>";
  try {
    const [meds, lowStock, expiring, alerts] = await Promise.all([
      api.listMedicines(), api.lowStock(), api.expiringBatches(60), api.listAlerts(),
    ]);
    box.innerHTML = `
      <div class="stats-row">
        <div class="stat-box"><div class="num">${meds.length}</div><div class="label">Active Medicines</div></div>
        <div class="stat-box"><div class="num">${lowStock.length}</div><div class="label">Low Stock Items</div></div>
        <div class="stat-box"><div class="num">${expiring.length}</div><div class="label">Batches Expiring (60d)</div></div>
        <div class="stat-box"><div class="num">${alerts.length}</div><div class="label">Open Alerts</div></div>
      </div>`;
  } catch (err) {
    box.innerHTML = `<p class="msg-box error">${err.message}</p>`;
  }
}

// ---------- Medicines ----------
let _medicinesSkip = 0;
const MEDICINES_PAGE_SIZE = 50;

async function loadMedicines(reset = true) {
  const tbody = document.querySelector("#medicines-table tbody");
  if (reset) {
    _medicinesSkip = 0;
    tbody.innerHTML = "<tr><td colspan='7'>Loading...</td></tr>";
    window._medicineCache = [];
  }
  try {
    const search = document.getElementById("medicine-search").value.trim();
    const meds = await api.listMedicines(search, _medicinesSkip, MEDICINES_PAGE_SIZE);
    const rowsHtml = meds.map((m) => `
      <tr>
        <td>${m.name}</td>
        <td>${m.generic_name || "-"}</td>
        <td>${m.category || "-"}</td>
        <td>₹${m.unit_price.toFixed(2)}</td>
        <td>${m.total_stock}${m.total_stock <= m.reorder_level ? ' <span class="badge medium">low</span>' : ""}</td>
        <td><button class="btn secondary" onclick="viewBatches(${m.id}, '${m.name.replace(/'/g, "")}')">Batches</button></td>
        <td><button class="btn secondary" onclick="showSubstitutes(${m.id})">Substitutes</button></td>
      </tr>`).join("");

    if (reset) {
      tbody.innerHTML = rowsHtml || "<tr><td colspan='7'>No medicines found.</td></tr>";
      window._medicineCache = meds;
    } else {
      tbody.insertAdjacentHTML("beforeend", rowsHtml);
      window._medicineCache = window._medicineCache.concat(meds);
    }

    document.getElementById("medicines-load-more").style.display = meds.length === MEDICINES_PAGE_SIZE ? "inline-block" : "none";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='7'>${err.message}</td></tr>`;
  }
}

document.getElementById("medicines-load-more").addEventListener("click", () => {
  _medicinesSkip += MEDICINES_PAGE_SIZE;
  loadMedicines(false);
});

function exportMedicinesCsv() {
  const meds = window._medicineCache || [];
  exportArrayAsCsv(meds.map((m) => ({
    name: m.name, generic_name: m.generic_name, category: m.category,
    unit_price: m.unit_price, total_stock: m.total_stock, reorder_level: m.reorder_level,
  })), "medicines.csv");
}

document.getElementById("medicine-search").addEventListener("input", () => loadMedicines());

document.getElementById("medicine-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    name: document.getElementById("med-name").value,
    generic_name: document.getElementById("med-generic").value,
    category: document.getElementById("med-category").value,
    dosage_form: document.getElementById("med-form").value,
    manufacturer: document.getElementById("med-manufacturer").value,
    unit_price: parseFloat(document.getElementById("med-price").value),
    reorder_level: parseInt(document.getElementById("med-reorder").value || "20", 10),
  };
  try {
    await api.createMedicine(payload);
    flash("medicine-msg", "Medicine added.", "success");
    e.target.reset();
    loadMedicines();
  } catch (err) {
    flash("medicine-msg", err.message, "error");
  }
});

async function showSubstitutes(medicineId) {
  const box = document.getElementById("substitutes-result");
  box.style.display = "block";
  box.className = "msg-box success";
  box.textContent = "Looking up substitutes...";
  try {
    const result = await api.substitutes(medicineId);
    if (result.substitutes.length === 0) {
      box.textContent = `No substitutes found in the catalog for ${result.medicine}.`;
    } else {
      box.textContent = `Substitutes for ${result.medicine}: ` +
        result.substitutes.map((s) => `${s.name}${s.generic_name ? " (" + s.generic_name + ")" : ""}`).join(", ");
    }
  } catch (err) {
    box.className = "msg-box error";
    box.textContent = err.message;
  }
}

async function viewBatches(medicineId, name) {
  document.getElementById("batch-medicine-id").value = medicineId;
  document.getElementById("batch-panel-title").textContent = `Batches — ${name}`;
  document.getElementById("batch-panel").style.display = "block";
  const tbody = document.querySelector("#batches-table tbody");
  tbody.innerHTML = "<tr><td colspan='5'>Loading...</td></tr>";
  try {
    const batches = await api.listBatches(medicineId);
    tbody.innerHTML = batches.map((b) => `
      <tr>
        <td>${b.batch_number}</td>
        <td>${b.quantity}</td>
        <td>${b.expiry_date}</td>
        <td>₹${b.cost_price.toFixed(2)}</td>
        <td>${b.received_date.substring(0, 10)}</td>
      </tr>`).join("") || "<tr><td colspan='5'>No batches yet.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='5'>${err.message}</td></tr>`;
  }
}

document.getElementById("batch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    medicine_id: parseInt(document.getElementById("batch-medicine-id").value, 10),
    batch_number: document.getElementById("batch-number").value,
    quantity: parseInt(document.getElementById("batch-qty").value, 10),
    cost_price: parseFloat(document.getElementById("batch-cost").value || "0"),
    expiry_date: document.getElementById("batch-expiry").value,
  };
  try {
    await api.addBatch(payload);
    flash("batch-msg", "Batch added.", "success");
    e.target.reset();
    document.getElementById("batch-medicine-id").value = payload.medicine_id;
    viewBatches(payload.medicine_id, document.getElementById("batch-panel-title").textContent.replace("Batches — ", ""));
    loadMedicines();
  } catch (err) {
    flash("batch-msg", err.message, "error");
  }
});

// ---------- Prescriptions ----------
async function loadPrescriptions() {
  const tbody = document.querySelector("#prescriptions-table tbody");
  tbody.innerHTML = "<tr><td colspan='5'>Loading...</td></tr>";
  try {
    const list = await api.listPrescriptions();
    tbody.innerHTML = list.map((p) => `
      <tr>
        <td>#${p.id}</td>
        <td>${p.created_at.substring(0, 16).replace("T", " ")}</td>
        <td><span class="badge ${p.status === "approved" ? "low" : p.status === "rejected" ? "high" : "medium"}">${p.status}</span></td>
        <td>${p.items.map((it) => `${it.extracted_name}${it.dosage ? " " + it.dosage : ""}${it.frequency ? " (" + it.frequency + ")" : ""}${it.warning_flag ? ` <span class="badge medium">⚠ ${it.warning_flag}</span>` : ""}`).join("<br>")}</td>
        <td>${p.status === "pending_review" ? `
          <button class="btn secondary" onclick="reviewPrescriptionAction(${p.id}, 'approved')">Approve</button>
          <button class="btn secondary" onclick="reviewPrescriptionAction(${p.id}, 'rejected')">Reject</button>
        ` : "-"}</td>
      </tr>`).join("") || "<tr><td colspan='5'>No prescriptions yet.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='5'>${err.message}</td></tr>`;
  }
}

async function reviewPrescriptionAction(id, status) {
  try {
    await api.reviewPrescription(id, status);
    loadPrescriptions();
  } catch (err) {
    flash("prescription-msg", err.message, "error");
  }
}

document.getElementById("extract-text-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("prescription-image");
  const file = fileInput.files[0];
  if (!file) {
    flash("ocr-msg", "Choose an image file first.", "error");
    return;
  }
  const btn = document.getElementById("extract-text-btn");
  btn.disabled = true;
  btn.textContent = "Reading image...";
  try {
    const result = await api.extractText(file);
    const box = document.getElementById("prescription-text");
    box.value = result.extracted_text
      ? result.extracted_text
      : "";
    if (!result.extracted_text) {
      flash("ocr-msg", "OCR ran but found no readable text. Try a clearer image, or type the prescription manually.", "error");
    } else {
      flash("ocr-msg", "Text extracted from image. Review and edit below before processing.", "success");
    }
  } catch (err) {
    flash("ocr-msg", err.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Extract Text from Image";
  }
});

document.getElementById("prescription-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const rawText = document.getElementById("prescription-text").value;
  try {
    await api.createPrescription({ raw_text: rawText });
    flash("prescription-msg", "Prescription processed by AI assist. Review items below.", "success");
    e.target.reset();
    loadPrescriptions();
  } catch (err) {
    flash("prescription-msg", err.message, "error");
  }
});

// ---------- Billing ----------
let invoiceItemCount = 0;

async function loadBilling() {
  if (!window._medicineCache) {
    window._medicineCache = await api.listMedicines();
  }
  await refreshInvoiceList();
}

async function refreshInvoiceList() {
  const tbody = document.querySelector("#invoices-table tbody");
  tbody.innerHTML = "<tr><td colspan='4'>Loading...</td></tr>";
  try {
    const list = await api.listInvoices();
    tbody.innerHTML = list.map((inv) => `
      <tr>
        <td>#${inv.id}</td>
        <td>${inv.created_at.substring(0, 16).replace("T", " ")}</td>
        <td>₹${inv.total_amount.toFixed(2)}</td>
        <td>${inv.payment_status}</td>
      </tr>`).join("") || "<tr><td colspan='4'>No invoices yet.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='4'>${err.message}</td></tr>`;
  }
}

function addInvoiceItemRow() {
  invoiceItemCount++;
  const id = invoiceItemCount;
  const meds = window._medicineCache || [];
  const container = document.getElementById("invoice-items");
  const row = document.createElement("div");
  row.className = "item-row";
  row.id = `invoice-item-${id}`;
  row.innerHTML = `
    <select id="inv-med-${id}" onchange="loadBatchOptionsForRow(${id})" style="flex:2">
      <option value="">Select medicine</option>
      ${meds.map((m) => `<option value="${m.id}">${m.name} (stock: ${m.total_stock})</option>`).join("")}
    </select>
    <select id="inv-batch-${id}" style="flex:2"><option value="">Select batch</option></select>
    <input type="number" id="inv-qty-${id}" placeholder="Qty" min="1" style="flex:1">
    <button type="button" class="remove-row" onclick="document.getElementById('invoice-item-${id}').remove()">✕</button>
  `;
  container.appendChild(row);
}

async function loadBatchOptionsForRow(id) {
  const medId = document.getElementById(`inv-med-${id}`).value;
  const batchSelect = document.getElementById(`inv-batch-${id}`);
  batchSelect.innerHTML = "<option value=''>Loading...</option>";
  if (!medId) return;
  const batches = await api.listBatches(medId);
  batchSelect.innerHTML = batches.filter((b) => b.quantity > 0).map((b) =>
    `<option value="${b.id}">${b.batch_number} (qty ${b.quantity}, exp ${b.expiry_date})</option>`
  ).join("") || "<option value=''>No stock available</option>";
}

document.getElementById("add-invoice-item-btn").addEventListener("click", addInvoiceItemRow);

document.getElementById("invoice-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const rows = document.querySelectorAll("#invoice-items .item-row");
  const items = [];
  rows.forEach((row) => {
    const id = row.id.split("-").pop();
    const medicine_id = parseInt(document.getElementById(`inv-med-${id}`).value, 10);
    const batch_id = parseInt(document.getElementById(`inv-batch-${id}`).value, 10);
    const quantity = parseInt(document.getElementById(`inv-qty-${id}`).value, 10);
    if (medicine_id && batch_id && quantity) items.push({ medicine_id, batch_id, quantity });
  });
  if (items.length === 0) {
    flash("invoice-msg", "Add at least one valid line item.", "error");
    return;
  }
  try {
    const discount = parseFloat(document.getElementById("invoice-discount").value || "0");
    const invoice = await api.createInvoice({ items, discount_amount: discount });
    flash("invoice-msg", `Invoice #${invoice.id} created. Total: ₹${invoice.total_amount.toFixed(2)}`, "success");
    document.getElementById("invoice-items").innerHTML = "";
    document.getElementById("invoice-discount").value = "";
    loadMedicines();
    refreshInvoiceList();
  } catch (err) {
    flash("invoice-msg", err.message, "error");
  }
});

// ---------- Suppliers & Purchase Orders ----------
async function loadSuppliers() {
  const tbody = document.querySelector("#suppliers-table tbody");
  tbody.innerHTML = "<tr><td colspan='4'>Loading...</td></tr>";
  try {
    const suppliers = await api.listSuppliers();
    tbody.innerHTML = suppliers.map((s) => `
      <tr><td>${s.name}</td><td>${s.contact_person || "-"}</td><td>${s.phone || "-"}</td><td>${s.lead_time_days} days</td></tr>
    `).join("") || "<tr><td colspan='4'>No suppliers yet.</td></tr>";

    window._supplierCache = suppliers;
    const poTbody = document.querySelector("#po-table tbody");
    const pos = await api.listPurchaseOrders();
    poTbody.innerHTML = pos.map((po) => `
      <tr>
        <td>#${po.id}</td>
        <td>${suppliers.find((s) => s.id === po.supplier_id)?.name || po.supplier_id}</td>
        <td>₹${po.total_amount.toFixed(2)}</td>
        <td>${po.status}</td>
        <td>${po.status === "pending" ? `<button class="btn secondary" onclick="markReceived(${po.id})">Mark Received</button>` : "-"}</td>
      </tr>
    `).join("") || "<tr><td colspan='5'>No purchase orders yet.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='4'>${err.message}</td></tr>`;
  }
}

async function markReceived(poId) {
  try {
    await api.receivePO(poId);
    flash("po-msg", `Purchase order #${poId} marked received. Add batches under Medicines once stock physically arrives.`, "success");
    loadSuppliers();
  } catch (err) {
    flash("po-msg", err.message, "error");
  }
}

document.getElementById("supplier-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    name: document.getElementById("sup-name").value,
    contact_person: document.getElementById("sup-contact").value,
    phone: document.getElementById("sup-phone").value,
    email: document.getElementById("sup-email").value,
    lead_time_days: parseInt(document.getElementById("sup-lead").value || "7", 10),
  };
  try {
    await api.createSupplier(payload);
    flash("supplier-msg", "Supplier added.", "success");
    e.target.reset();
    loadSuppliers();
  } catch (err) {
    flash("supplier-msg", err.message, "error");
  }
});

let poItemCount = 0;
function addPoItemRow() {
  poItemCount++;
  const id = poItemCount;
  const meds = window._medicineCache || [];
  const container = document.getElementById("po-items");
  const row = document.createElement("div");
  row.className = "item-row";
  row.id = `po-item-${id}`;
  row.innerHTML = `
    <select id="po-med-${id}" style="flex:2">
      <option value="">Select medicine</option>
      ${meds.map((m) => `<option value="${m.id}">${m.name}</option>`).join("")}
    </select>
    <input type="number" id="po-qty-${id}" placeholder="Qty" min="1" style="flex:1">
    <input type="number" id="po-cost-${id}" placeholder="Unit cost" min="0" step="0.01" style="flex:1">
    <button type="button" class="remove-row" onclick="document.getElementById('po-item-${id}').remove()">✕</button>
  `;
  container.appendChild(row);
}

document.getElementById("add-po-item-btn").addEventListener("click", async () => {
  if (!window._medicineCache) window._medicineCache = await api.listMedicines();
  addPoItemRow();
});

document.getElementById("po-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const supplierId = parseInt(document.getElementById("po-supplier").value, 10);
  const rows = document.querySelectorAll("#po-items .item-row");
  const items = [];
  rows.forEach((row) => {
    const id = row.id.split("-").pop();
    const medicine_id = parseInt(document.getElementById(`po-med-${id}`).value, 10);
    const quantity = parseInt(document.getElementById(`po-qty-${id}`).value, 10);
    const unit_cost = parseFloat(document.getElementById(`po-cost-${id}`).value);
    if (medicine_id && quantity && unit_cost >= 0) items.push({ medicine_id, quantity, unit_cost });
  });
  if (!supplierId || items.length === 0) {
    flash("po-msg", "Select a supplier and add at least one item.", "error");
    return;
  }
  try {
    const po = await api.createPurchaseOrder({ supplier_id: supplierId, items });
    flash("po-msg", `Purchase order #${po.id} created. Total ₹${po.total_amount.toFixed(2)}`, "success");
    document.getElementById("po-items").innerHTML = "";
    loadSuppliers();
  } catch (err) {
    flash("po-msg", err.message, "error");
  }
});

async function populatePoSupplierDropdown() {
  const suppliers = window._supplierCache || (await api.listSuppliers());
  const select = document.getElementById("po-supplier");
  select.innerHTML = "<option value=''>Select supplier</option>" +
    suppliers.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
}

// ---------- Alerts ----------
async function loadAlerts() {
  const tbody = document.querySelector("#alerts-table tbody");
  tbody.innerHTML = "<tr><td colspan='4'>Loading...</td></tr>";
  try {
    const alerts = await api.listAlerts();
    tbody.innerHTML = alerts.map((a) => `
      <tr>
        <td><span class="badge ${a.severity}">${a.type}</span></td>
        <td>${a.message}</td>
        <td>${a.created_at.substring(0, 16).replace("T", " ")}</td>
        <td><button class="btn secondary" onclick="resolveAlertRow(${a.id})">Resolve</button></td>
      </tr>`).join("") || "<tr><td colspan='4'>No open alerts. Click 'Scan Now' to run the expiry/low-stock engine.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='4'>${err.message}</td></tr>`;
  }
}

async function resolveAlertRow(id) {
  await api.resolveAlert(id);
  loadAlerts();
}

document.getElementById("scan-alerts-btn").addEventListener("click", async () => {
  try {
    const created = await api.scanAlerts();
    flash("alerts-msg", `Scan complete. ${created.length} new alert(s) generated.`, "success");
    loadAlerts();
  } catch (err) {
    flash("alerts-msg", err.message, "error");
  }
});

// ---------- Reports ----------
async function loadReports() {
  await runReport("fast-moving");
}

async function runReport(type) {
  document.querySelectorAll("#reports-tabs button").forEach((b) => b.classList.remove("active"));
  document.getElementById(`report-tab-${type}`).classList.add("active");
  window._lastReportType = type;
  window._lastReportRows = [];

  const box = document.getElementById("report-output");
  box.innerHTML = "<p>Loading...</p>";
  try {
    let html = "";
    if (type === "fast-moving") {
      const data = await api.reportFastMoving();
      html = renderTable(["Medicine", "Total Sold (30d)"], data.map((d) => [d.name, d.total_sold]));
      window._lastReportRows = data;
    } else if (type === "dead-stock") {
      const data = await api.reportDeadStock();
      html = renderTable(["Medicine", "Current Stock"], data.map((d) => [d.name, d.current_stock]));
      window._lastReportRows = data;
    } else if (type === "expiry-loss") {
      const data = await api.reportExpiryLoss();
      html = `<p><strong>Total estimated loss: ₹${data.total_estimated_loss.toFixed(2)}</strong></p>` +
        renderTable(["Batch", "Medicine ID", "Qty", "Expiry", "Loss"],
          data.batches.map((b) => [b.batch_number, b.medicine_id, b.quantity, b.expiry_date, `₹${b.estimated_loss.toFixed(2)}`]));
      window._lastReportRows = data.batches;
    } else if (type === "daily-sales") {
      const data = await api.reportDailySales();
      html = `<div class="stats-row">
        <div class="stat-box"><div class="num">${data.invoice_count}</div><div class="label">Invoices Today</div></div>
        <div class="stat-box"><div class="num">₹${data.total_sales.toFixed(2)}</div><div class="label">Total Sales Today</div></div>
      </div>`;
      window._lastReportRows = [data];
    } else if (type === "reorder-needs") {
      const data = await api.reportReorderNeeds();
      html = renderTable(["Medicine", "Current Stock", "Reorder Level", "Projected Demand (30d)"],
        data.map((d) => [d.name, d.current_stock, d.reorder_level, d.projected_demand_next_30_days]));
      window._lastReportRows = data;
    } else if (type === "pharmacist-workload") {
      const data = await api.reportPharmacistWorkload();
      html = renderTable(["Staff", "Role", "Prescriptions", "Invoices", "Purchase Orders", "Total Activity"],
        data.staff.map((w) => [w.username, w.role, w.prescriptions_processed, w.invoices_generated, w.purchase_orders_created, w.total_activity]));
      if (data.staff.length === 0) html = "<p>No staff activity recorded in the last 30 days yet.</p>";
      window._lastReportRows = data.staff;
    }
    box.innerHTML = html || "<p>No data available.</p>";
  } catch (err) {
    box.innerHTML = `<p class="msg-box error">${err.message}</p>`;
  }
}

function exportCurrentReportCsv() {
  const type = window._lastReportType || "report";
  exportArrayAsCsv(window._lastReportRows, `${type}.csv`);
}

function renderTable(headers, rows) {
  if (rows.length === 0) return "<p>No data available.</p>";
  return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

// ---------- Init ----------
window.addEventListener("DOMContentLoaded", async () => {
  if (getToken()) {
    try {
      await api.me();
      showApp();
    } catch {
      showLogin();
    }
  } else {
    showLogin();
  }
  populatePoSupplierDropdown().catch(() => {});
});
