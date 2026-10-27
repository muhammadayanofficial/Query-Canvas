(() => {
  const initial = window.QUERYCANVAS_INITIAL || {};
  let datasets = Array.isArray(initial.datasets) ? initial.datasets : [];
  let savedQueries = Array.isArray(initial.savedQueries) ? initial.savedQueries : [];
  let selectedId = initial.selectedId || (datasets[0] && datasets[0].id) || "";
  let lastResult = null;
  let toastTimer = null;

  const el = (id) => document.getElementById(id);
  const sqlInput = el("sqlInput");

  function selectedDataset() {
    return datasets.find((dataset) => dataset.id === selectedId) || datasets[0] || null;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
  }

  function showToast(message) {
    const toast = el("toast");
    toast.textContent = message;
    toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
  }

  function updateMessage(target, message, type = "") {
    target.textContent = message;
    target.classList.remove("error", "success");
    if (type) target.classList.add(type);
  }

  function setQueryMessage(message, type = "") {
    const node = el("queryMessage");
    node.textContent = message;
    node.classList.toggle("show", Boolean(message));
    node.classList.toggle("success", type === "success");
  }

  function renderDatasets() {
    const list = el("datasetList");
    list.replaceChildren();
    datasets.forEach((dataset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `dataset-row${dataset.id === selectedId ? " active" : ""}`;
      button.innerHTML = `<span class="dataset-glyph"><svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="5" rx="7" ry="3"></ellipse><path d="M5 5v14c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"></path></svg></span><span class="dataset-row-text"><strong>${escapeHtml(dataset.name)}</strong><small>${Number(dataset.row_count).toLocaleString()} rows · ${dataset.columns.length} fields</small></span><span class="dataset-active-mark"></span>`;
      button.addEventListener("click", () => chooseDataset(dataset.id));
      list.appendChild(button);
    });
    el("datasetCount").textContent = String(datasets.length);
  }

  function renderSchema(dataset) {
    if (!dataset) return;
    el("activeDatasetName").textContent = dataset.name;
    el("schemaTableName").textContent = dataset.table_name;
    el("schemaRowCount").textContent = `${Number(dataset.row_count).toLocaleString()} rows`;
    el("schemaColumnCount").textContent = `${dataset.columns.length} fields`;
    const holder = el("schemaColumns");
    holder.replaceChildren();
    dataset.columns.forEach((column) => {
      const row = document.createElement("div");
      row.className = "schema-column";
      const type = String(column.type || "TEXT").toUpperCase();
      const badge = type.includes("INT") || type.includes("REAL") || type.includes("NUM") || type.includes("DEC") ? "123" : "Aa";
      row.innerHTML = `<span class="type-pill${badge === "123" ? " number" : ""}">${badge}</span><span class="schema-column-name" title="${escapeHtml(column.name)}">${escapeHtml(column.name)}</span><span class="schema-column-type">${escapeHtml(type)}</span>`;
      holder.appendChild(row);
    });
    renderDatasets();
  }

  function renderSavedQueries() {
    const list = el("savedQueryList");
    list.replaceChildren();
    el("savedCount").textContent = String(savedQueries.length);
    el("savedEmpty").style.display = savedQueries.length ? "none" : "block";
    savedQueries.forEach((query) => {
      const row = document.createElement("div");
      row.className = "saved-query-row-wrap";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "saved-query-row";
      button.title = query.sql;
      button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h12v16l-6-4-6 4z"></path></svg><span>${escapeHtml(query.title)}</span>`;
      button.addEventListener("click", () => {
        selectedId = query.dataset_id;
        const ds = selectedDatasetById(query.dataset_id);
        if (ds) renderSchema(ds);
        sqlInput.value = query.sql;
        updateLineNumbers();
        setQueryMessage(`Loaded “${query.title}”. Run it when ready.`, "success");
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "saved-delete";
      remove.title = "Delete saved query";
      remove.setAttribute("aria-label", `Delete ${query.title}`);
      remove.textContent = "×";
      remove.addEventListener("click", async (event) => {
        event.stopPropagation();
        await deleteSavedQuery(query.id);
      });
      row.append(button, remove);
      list.appendChild(row);
    });
  }

  function selectedDatasetById(id) {
    return datasets.find((dataset) => dataset.id === id) || null;
  }

  async function refreshDatasets() {
    try {
      const response = await fetch("/api/datasets");
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not load datasets.");
      datasets = data.datasets || [];
      if (!selectedDatasetById(selectedId)) selectedId = (datasets[0] && datasets[0].id) || "";
      renderDatasets();
      renderSchema(selectedDataset());
    } catch (error) {
      showToast(error.message || "Could not refresh datasets.");
    }
  }

  async function refreshSavedQueries() {
    try {
      const response = await fetch("/api/queries");
      const data = await response.json();
      if (response.ok) {
        savedQueries = data.queries || [];
        renderSavedQueries();
      }
    } catch (_error) {
      // Existing saved queries remain usable if a refresh fails.
    }
  }

  function chooseDataset(id) {
    const dataset = selectedDatasetById(id);
    if (!dataset) return;
    selectedId = dataset.id;
    renderSchema(dataset);
    sqlInput.value = `SELECT *\nFROM ${dataset.table_name}\nLIMIT 10;`;
    updateLineNumbers();
    lastResult = null;
    el("exportCsv").disabled = true;
    el("resultSummary").textContent = "Run a query to see results";
    el("resultDuration").textContent = "";
    renderEmptyResults("Dataset selected", "Run a query to explore this table.");
    setQueryMessage("");
  }

  function updateLineNumbers() {
    const count = Math.max(1, sqlInput.value.split("\n").length);
    el("lineNumbers").innerHTML = Array.from({ length: count }, (_, index) => index + 1).join("<br>");
  }

  function renderEmptyResults(title, description) {
    const holder = el("resultTableWrap");
    holder.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty-results";
    empty.innerHTML = `<div class="empty-results-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 10h16M4 15h10M4 20h16"></path><path d="M8 3v4M16 3v4"></path></svg></div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(description)}</span>`;
    holder.appendChild(empty);
  }

  function renderResults(result) {
    lastResult = result;
    const holder = el("resultTableWrap");
    holder.replaceChildren();
    if (!result.columns || result.columns.length === 0) {
      renderEmptyResults("Query returned no columns", "Try a SELECT query that returns rows.");
      return;
    }
    const table = document.createElement("table");
    table.className = "data-table";
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    result.columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    const tbody = document.createElement("tbody");
    result.rows.forEach((values) => {
      const tr = document.createElement("tr");
      values.forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value === null ? "" : String(value);
        if (typeof value === "number" || (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value))) td.classList.add("numeric");
        td.title = td.textContent;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    holder.appendChild(table);
    const countText = `${result.row_count} row${result.row_count === 1 ? "" : "s"}${result.truncated ? " shown (capped at 200)" : ""}`;
    el("resultSummary").textContent = countText;
    el("resultDuration").textContent = `${result.duration_ms} ms`;
    el("resultFootNote").textContent = result.truncated ? "Showing the first 200 rows. Refine the query for a smaller result." : "Results are read-only and limited to 200 rows.";
    el("exportCsv").disabled = result.rows.length === 0;
  }

  async function runQuery() {
    const dataset = selectedDataset();
    if (!dataset) {
      setQueryMessage("Import a CSV dataset before running a query.");
      return;
    }
    const button = el("runQuery");
    button.disabled = true;
    button.querySelector("span").textContent = "Running…";
    setQueryMessage("");
    try {
      const response = await fetch("/api/query/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id, sql: sqlInput.value })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Query could not be run.");
      renderResults(data);
      setQueryMessage(`Query completed — ${data.row_count} row${data.row_count === 1 ? "" : "s"} returned.`, "success");
    } catch (error) {
      setQueryMessage(error.message || "Query could not be run.");
      renderEmptyResults("Query did not run", error.message || "Check your SQL and try again.");
      el("resultSummary").textContent = "Query error";
      el("resultDuration").textContent = "";
      el("exportCsv").disabled = true;
    } finally {
      button.disabled = false;
      button.querySelector("span").textContent = "Run query";
    }
  }

  async function generateSql() {
    const question = el("naturalQuestion").value.trim();
    const dataset = selectedDataset();
    if (!question) {
      updateMessage(el("aiMessage"), "Describe what you want to find in the dataset first.", "error");
      return;
    }
    const button = el("generateSql");
    button.disabled = true;
    button.firstChild.textContent = "Generating… ";
    updateMessage(el("aiMessage"), "Asking Gemini to draft a read-only query…");
    try {
      const response = await fetch("/api/query/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.id, question })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not generate SQL.");
      sqlInput.value = data.sql;
      updateLineNumbers();
      updateMessage(el("aiMessage"), `Query drafted with ${data.model}. Review it, then run it.`, "success");
      setQueryMessage("AI drafted a query. Review it before running.", "success");
    } catch (error) {
      updateMessage(el("aiMessage"), error.message || "Could not generate SQL.", "error");
    } finally {
      button.disabled = false;
      button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 14 9l6 3-6 2-2 7-2-7-6-2 6-3z"></path></svg> Generate SQL <span>↗</span>';
    }
  }

  async function saveQuery() {
    const dataset = selectedDataset();
    const sql = sqlInput.value.trim();
    if (!dataset || !sql) {
      showToast("Add a query before saving.");
      return;
    }
    const title = window.prompt("Name this query:", "Revenue by region");
    if (!title || !title.trim()) return;
    try {
      const response = await fetch("/api/queries/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), sql, dataset_id: dataset.id })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save query.");
      savedQueries.unshift(data.query);
      savedQueries = savedQueries.filter((query, index, arr) => arr.findIndex((other) => other.id === query.id) === index).slice(0, 30);
      renderSavedQueries();
      showToast("Query saved to your workspace.");
    } catch (error) {
      showToast(error.message || "Could not save query.");
    }
  }

  async function deleteSavedQuery(id) {
    try {
      const response = await fetch(`/api/queries/${id}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not delete query.");
      savedQueries = savedQueries.filter((query) => query.id !== id);
      renderSavedQueries();
      showToast("Saved query deleted.");
    } catch (error) {
      showToast(error.message || "Could not delete query.");
    }
  }

  function exportResults() {
    if (!lastResult || !lastResult.columns || !lastResult.rows.length) return;
    const fields = [...lastResult.columns, ...lastResult.rows.map((row) => row)];
    const allRows = [lastResult.columns, ...lastResult.rows];
    const csv = allRows.map((row) => row.map((value) => {
      const text = String(value ?? "");
      return `"${text.replace(/"/g, '""')}"`;
    }).join(",")).join("\r\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `querycanvas-results-${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    showToast("CSV export downloaded.");
  }

  async function importSelectedFile(file) {
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    showToast("Importing CSV…");
    try {
      const response = await fetch("/api/datasets", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "CSV import failed.");
      datasets.push(data.dataset);
      selectedId = data.dataset.id;
      renderSchema(data.dataset);
      sqlInput.value = `SELECT *\nFROM ${data.dataset.table_name}\nLIMIT 10;`;
      updateLineNumbers();
      renderEmptyResults("Dataset imported", "Run the sample query to inspect your imported data.");
      el("resultSummary").textContent = "Run a query to see results";
      lastResult = null;
      el("exportCsv").disabled = true;
      setQueryMessage(`Imported ${data.dataset.row_count.toLocaleString()} rows from ${data.dataset.name}.`, "success");
      showToast("CSV imported successfully.");
    } catch (error) {
      showToast(error.message || "CSV import failed.");
    } finally {
      el("csvFileInput").value = "";
    }
  }

  function basicFormatQuery() {
    const sql = sqlInput.value.trim();
    if (!sql) return;
    const keywords = ["SELECT", "FROM", "WHERE", "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "UNION ALL", "UNION", "LEFT JOIN", "INNER JOIN", "JOIN", "ON"];
    let formatted = sql.replace(/\s+/g, " ");
    keywords.sort((a, b) => b.length - a.length).forEach((keyword) => {
      const pattern = new RegExp(`\\b${keyword.replace(/ /g, "\\s+")}\\b`, "ig");
      formatted = formatted.replace(pattern, `\n${keyword}`);
    });
    formatted = formatted.trim().replace(/^\n/, "");
    sqlInput.value = formatted;
    updateLineNumbers();
  }

  el("runQuery").addEventListener("click", runQuery);
  el("sqlInput").addEventListener("input", updateLineNumbers);
  el("sqlInput").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      runQuery();
    }
    if (event.key === "Tab") {
      event.preventDefault();
      const start = sqlInput.selectionStart;
      const end = sqlInput.selectionEnd;
      sqlInput.setRangeText("    ", start, end, "end");
      updateLineNumbers();
    }
  });
  el("formatQuery").addEventListener("click", basicFormatQuery);
  el("clearQuery").addEventListener("click", () => {
    sqlInput.value = "";
    updateLineNumbers();
    setQueryMessage("");
    sqlInput.focus();
  });
  el("generateSql").addEventListener("click", generateSql);
  el("saveQuery")?.addEventListener("click", saveQuery);
  el("exportCsv").addEventListener("click", exportResults);
  el("schemaTab").addEventListener("click", () => {
    const dataset = selectedDataset();
    if (!dataset) return;
    showToast(`${dataset.columns.length} fields in ${dataset.table_name}`);
  });
  ["importCsv", "addSource", "railImport"].forEach((id) => el(id).addEventListener("click", () => el("csvFileInput").click()));
  el("csvFileInput").addEventListener("change", (event) => importSelectedFile(event.target.files && event.target.files[0]));
  el("refreshDatasets").addEventListener("click", refreshDatasets);
  el("railSaved").addEventListener("click", () => el("savedSection").scrollIntoView({ behavior: "smooth", block: "start" }));
  el("savedSection").addEventListener("dblclick", saveQuery);
  document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => {
    el("naturalQuestion").value = button.dataset.question || "";
    el("naturalQuestion").focus();
  }));

  // Add a save action beside Format/Clear without changing the editor's layout.
  const editorActions = document.querySelector(".editor-actions");
  const saveButton = document.createElement("button");
  saveButton.type = "button";
  saveButton.className = "text-button";
  saveButton.textContent = "Save query";
  saveButton.addEventListener("click", saveQuery);
  editorActions.prepend(saveButton);

  renderDatasets();
  renderSavedQueries();
  renderSchema(selectedDataset());
  updateLineNumbers();
  if (selectedDataset()) {
    runQuery();
  }
})();
