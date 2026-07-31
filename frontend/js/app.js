// ---------- Screen switching ----------
function showLogin() {
  document.getElementById("login-screen").style.display = "flex";
  document.getElementById("app-screen").style.display = "none";
}

function showApp() {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("app-screen").style.display = "block";
  document.getElementById("who-label").textContent =
    `${localStorage.getItem("pharmacy_username")} (${localStorage.getItem("pharmacy_role")})`;
  navigate("dashboard");
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
    setSession(data.access_token, data.role, data.username);
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
async function loadMedicines() {
  const tbody = document.querySelector("#medicines-table tbody");
  tbody.innerHTML = "<tr><td colspan='6'>Loading...</td></tr>";
  try {
    const meds = await api.listMedicines(document.getElementById("medicine-search").value.trim());
    tbody.innerHTML = meds.map((m) => `
      <tr>
        <td>${m.name}</td>
        <td>${m.generic_name || "-"}</td>
        <td>${m.category || "-"}</td>
        <td>₹${m.unit_price.toFixed(2)}</td>
        <td>${m.total_stock}${m.total_stock <= m.reorder_level ? ' <span class="badge medium">low</span>' : ""}</td>
        <td><button class="btn secondary" onclick="viewBatches(${m.id}, '${m.name.replace(/'/g, "")}')">Batches</button></td>
      </tr>`).join("") || "<tr><td colspan='6'>No medicines found.</td></tr>";
    window._medicineCache = meds;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='6'>${err.message}</td></tr>`;
  }
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
  tbody.innerHTML = "<tr><td colspan='4'>Loading...</td></tr>";
  try {
    const list = await api.listPrescriptions();
    tbody.innerHTML = list.map((p) => `
      <tr>
        <td>#${p.id}</td>
        <td>${p.created_at.substring(0, 16).replace("T", " ")}</td>
        <td>${p.status}</td>
        <td>${p.items.map((it) => `${it.extracted_name}${it.dosage ? " " + it.dosage : ""}${it.frequency ? " (" + it.frequency + ")" : ""}${it.warning_flag ? ` <span class="badge medium">⚠ ${it.warning_flag}</span>` : ""}`).join("<br>")}</td>
      </tr>`).join("") || "<tr><td colspan='4'>No prescriptions yet.</td></tr>";
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan='4'>${err.message}</td></tr>`;
  }
}

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

  const box = document.getElementById("report-output");
  box.innerHTML = "<p>Loading...</p>";
  try {
    let html = "";
    if (type === "fast-moving") {
      const data = await api.reportFastMoving();
      html = renderTable(["Medicine", "Total Sold (30d)"], data.map((d) => [d.name, d.total_sold]));
    } else if (type === "dead-stock") {
      const data = await api.reportDeadStock();
      html = renderTable(["Medicine", "Current Stock"], data.map((d) => [d.name, d.current_stock]));
    } else if (type === "expiry-loss") {
      const data = await api.reportExpiryLoss();
      html = `<p><strong>Total estimated loss: ₹${data.total_estimated_loss.toFixed(2)}</strong></p>` +
        renderTable(["Batch", "Medicine ID", "Qty", "Expiry", "Loss"],
          data.batches.map((b) => [b.batch_number, b.medicine_id, b.quantity, b.expiry_date, `₹${b.estimated_loss.toFixed(2)}`]));
    } else if (type === "daily-sales") {
      const data = await api.reportDailySales();
      html = `<div class="stats-row">
        <div class="stat-box"><div class="num">${data.invoice_count}</div><div class="label">Invoices Today</div></div>
        <div class="stat-box"><div class="num">₹${data.total_sales.toFixed(2)}</div><div class="label">Total Sales Today</div></div>
      </div>`;
    } else if (type === "reorder-needs") {
      const data = await api.reportReorderNeeds();
      html = renderTable(["Medicine", "Current Stock", "Reorder Level", "Projected Demand (30d)"],
        data.map((d) => [d.name, d.current_stock, d.reorder_level, d.projected_demand_next_30_days]));
    }
    box.innerHTML = html || "<p>No data available.</p>";
  } catch (err) {
    box.innerHTML = `<p class="msg-box error">${err.message}</p>`;
  }
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
