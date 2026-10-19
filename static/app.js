const status = document.querySelector("#status");
const slip = document.querySelector("#slip");
const labels = {
  free_comeback: "Free comeback",
  labor_only: "Labor only",
  new_paid: "New paid job",
  collect_first: "Collect first",
};

function rupees(amount) {
  return `Rs ${Number(amount || 0).toLocaleString("en-IN")}`;
}

async function send(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function fillPolicy(policy) {
  const form = document.querySelector("#policy");
  for (const key of ["comeback_days", "labor_inr", "touch_quote", "battery_quote", "charging_quote"]) {
    form.elements[key].value = policy[key];
  }
}

function paint(board) {
  fillPolicy(board.policy);
  document.querySelector("#techs").innerHTML = board.technicians.length
    ? board.technicians.map((tech) => `<li><strong>${tech.name}</strong> · ${(tech.skills || []).join(", ")}</li>`).join("")
    : "<li>No technicians yet.</li>";
  document.querySelector("#customers").innerHTML = board.customers.length
    ? board.customers.map((customer) => `<li><strong>${customer.name}</strong> · ${customer.phone}<br />${customer.model}</li>`).join("")
    : "<li>No customers yet.</li>";
  document.querySelector("#jobs").innerHTML = board.jobs.length
    ? board.jobs.map((job) => `<li><strong>${job.id}</strong> ${job.customer_name} · ${job.fault} · ${job.paid ? "paid" : "unpaid"} · ${rupees(job.amount_inr)}</li>`).join("")
    : "<li>No jobs yet.</li>";
  document.querySelector("#decisions").innerHTML = board.decisions.length
    ? board.decisions.map((item) => `<li><span class="tag">${labels[item.outcome] || item.outcome}</span> <strong>${item.customer_name}</strong> · ${rupees(item.amount_inr)}<br />${item.summary}</li>`).join("")
    : "<li>No decisions yet.</li>";
  if (board.decisions[0]) showSlip(board.decisions[0]);
}

function showSlip(item) {
  slip.innerHTML = `
    <article class="slip-card ${item.outcome}">
      <p class="outcome">${labels[item.outcome] || item.outcome}</p>
      <p class="amount">${rupees(item.amount_inr)}</p>
      <p>${item.summary}</p>
      <p>${item.assignee ? `Floor: ${item.assignee}` : "No technician assigned."}</p>
      <p class="hint">${item.model} · based on ${(item.based_on || []).join(", ") || "no earlier job"}</p>
    </article>`;
}

async function loadBoard() {
  const response = await fetch("/api/board");
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "The book is not connected.");
  paint(data);
}

async function listen() {
  const config = await fetch("/api/config").then((response) => response.json());
  if (!config.supabaseUrl || !config.supabaseAnonKey) {
    status.textContent = "Realtime needs SUPABASE_URL and SUPABASE_ANON_KEY. Saving still works.";
    return;
  }
  const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
  const supabase = createClient(config.supabaseUrl, config.supabaseAnonKey);
  supabase
    .channel("dobara")
    .on("postgres_changes", { event: "*", schema: "public", table: "decisions" }, loadBoard)
    .on("postgres_changes", { event: "*", schema: "public", table: "jobs" }, loadBoard)
    .on("postgres_changes", { event: "*", schema: "public", table: "customers" }, loadBoard)
    .subscribe();
}

document.querySelector("#policy").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  status.textContent = "Saving the rule…";
  try {
    const raw = Object.fromEntries(new FormData(form).entries());
    const body = Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, Number(value)]));
    await send("/api/policy", body);
    status.textContent = "Rule saved.";
    await loadBoard();
  } catch (error) {
    status.textContent = error.message;
  }
});

document.querySelector("#tech").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const skills = ["touch", "battery", "charging"].filter((skill) => form.elements[skill].checked);
  status.textContent = "Adding technician…";
  try {
    await send("/api/technicians", { name: form.elements.name.value, skills });
    form.reset();
    status.textContent = "Technician added.";
    await loadBoard();
  } catch (error) {
    status.textContent = error.message;
  }
});

document.querySelector("#customer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget).entries());
  status.textContent = "Adding customer…";
  try {
    await send("/api/customers", body);
    event.currentTarget.reset();
    status.textContent = "Customer added.";
    await loadBoard();
  } catch (error) {
    status.textContent = error.message;
  }
});

document.querySelector("#job").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form).entries());
    body.paid = form.elements.paid.checked;
    body.amount_inr = Number(body.amount_inr);
    body.warranty_days = body.warranty_days === "" ? null : Number(body.warranty_days);
  status.textContent = "Adding job…";
  try {
    await send("/api/jobs", body);
    form.reset();
    status.textContent = "Job added.";
    await loadBoard();
  } catch (error) {
    status.textContent = error.message;
  }
});

document.querySelector("#complaint").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget).entries());
  status.textContent = "Gemma is reading the book…";
  try {
    const data = await send("/api/decide", body);
    showSlip(data.decision);
    status.textContent = "Decision saved.";
    await loadBoard();
  } catch (error) {
    status.textContent = error.message;
  }
});

loadBoard()
  .then(listen)
  .catch((error) => {
    status.textContent = error.message;
  });
