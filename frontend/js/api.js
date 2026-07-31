const API_BASE = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("pharmacy_token");
}

function setSession(token, role, username) {
  localStorage.setItem("pharmacy_token", token);
  localStorage.setItem("pharmacy_role", role);
  localStorage.setItem("pharmacy_username", username);
}

function clearSession() {
  localStorage.removeItem("pharmacy_token");
  localStorage.removeItem("pharmacy_role");
  localStorage.removeItem("pharmacy_username");
}

async function apiRequest(path, { method = "GET", body = null, form = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload = undefined;
  if (body !== null) {
    if (form) {
      payload = body; // URLSearchParams
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
  }

  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });

  if (res.status === 401) {
    clearSession();
    showLogin();
    throw new Error("Session expired. Please log in again.");
  }

  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : null;

  if (!res.ok) {
    const detail = data && data.detail ? data.detail : res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

const api = {
  login: (username, password) => {
    const form = new URLSearchParams();
    form.append("username", username);
    form.append("password", password);
    return apiRequest("/api/auth/login", { method: "POST", body: form, form: true });
  },
  me: () => apiRequest("/api/auth/me"),

  listMedicines: (search = "") => apiRequest(`/api/medicines${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  createMedicine: (payload) => apiRequest("/api/medicines", { method: "POST", body: payload }),
  listBatches: (medicineId) => apiRequest(`/api/medicines/${medicineId}/batches`),
  addBatch: (payload) => apiRequest("/api/medicines/batches", { method: "POST", body: payload }),
  expiringBatches: (days = 60) => apiRequest(`/api/medicines/alerts/expiring?days=${days}`),
  lowStock: () => apiRequest("/api/medicines/alerts/low-stock"),

  listSuppliers: () => apiRequest("/api/suppliers"),
  createSupplier: (payload) => apiRequest("/api/suppliers", { method: "POST", body: payload }),
  listPurchaseOrders: () => apiRequest("/api/purchase-orders"),
  createPurchaseOrder: (payload) => apiRequest("/api/purchase-orders", { method: "POST", body: payload }),
  receivePO: (id) => apiRequest(`/api/purchase-orders/${id}/receive`, { method: "POST" }),

  listCustomers: () => apiRequest("/api/customers"),
  createCustomer: (payload) => apiRequest("/api/customers", { method: "POST", body: payload }),

  listPrescriptions: () => apiRequest("/api/prescriptions"),
  createPrescription: (payload) => apiRequest("/api/prescriptions", { method: "POST", body: payload }),
  reviewPrescription: (id, status) => apiRequest(`/api/prescriptions/${id}/review`, { method: "PATCH", body: { status } }),

  listInvoices: () => apiRequest("/api/invoices"),
  createInvoice: (payload) => apiRequest("/api/invoices", { method: "POST", body: payload }),

  listAlerts: () => apiRequest("/api/alerts?resolved=false"),
  scanAlerts: () => apiRequest("/api/alerts/scan", { method: "POST" }),
  resolveAlert: (id) => apiRequest(`/api/alerts/${id}/resolve`, { method: "PATCH" }),

  reportFastMoving: () => apiRequest("/api/reports/fast-moving"),
  reportDeadStock: () => apiRequest("/api/reports/dead-stock"),
  reportExpiryLoss: () => apiRequest("/api/reports/expiry-loss"),
  reportDailySales: () => apiRequest("/api/reports/daily-sales"),
  reportReorderNeeds: () => apiRequest("/api/reports/reorder-needs"),

  checkInteractions: (medicine_names) => apiRequest("/api/ai/check-interactions", { method: "POST", body: { medicine_names } }),
  substitutes: (medicine_id) => apiRequest("/api/ai/substitutes", { method: "POST", body: { medicine_id } }),
};
