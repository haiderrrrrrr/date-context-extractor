// Store extracted dates globally so downloads always have fresh data
let extractedDates = [];

document.getElementById("scrapeButton").addEventListener("click", scrapeData);
document.getElementById("downloadPdfButton").addEventListener("click", downloadPDF);
document.getElementById("downloadCsvButton").addEventListener("click", downloadCSV);

async function scrapeData() {
  const url = document.getElementById("urlInput").value.trim();
  const datesListSection = document.getElementById("datesList");
  const downloadButtons = document.getElementById("downloadButtons");
  const loader = document.getElementById("loader");

  if (!url) {
    displayMessage("Please enter a valid URL!", "error");
    return;
  }

  // Reset state on every new scrape
  extractedDates = [];
  document.getElementById("dateList").innerHTML = "";
  datesListSection.style.display = "none";
  downloadButtons.style.display = "none";

  loader.style.display = "block";
  document.getElementById("scrapedData").style.display = "none";

  try {
    const response = await fetch(`/scrape?url=${encodeURIComponent(url)}`);
    const data = await response.json();
    loader.style.display = "none";

    if (data.dates && data.dates.length > 0) {
      extractedDates = data.dates;
      displayMessage(`✔ Found ${data.dates.length} date(s)`, "success");
      displayDatesList(data.dates);
      datesListSection.style.display = "block";
      downloadButtons.style.display = "flex";
    } else {
      displayMessage(data.message || "No dates found on the page.", "error");
    }
  } catch (err) {
    loader.style.display = "none";
    displayMessage("Network error — could not reach the server.", "error");
  }
}

function displayMessage(message, type) {
  const div = document.getElementById("scrapedData");
  div.style.display = "block";
  div.className = type === "success" ? "success" : type === "error" ? "error" : "loading-msg";
  div.textContent = message;
}

function displayDatesList(dates) {
  const list = document.getElementById("dateList");
  list.innerHTML = "";

  dates.forEach((item, i) => {
    const li = document.createElement("li");

    // Highlight the matched date inside context safely
    const escapedDate = item.date.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`(${escapedDate})`, "gi");
    const safeCtx = (item.context || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const markedCtx = safeCtx.replace(regex, `<mark>$1</mark>`);

    li.innerHTML = `
      <div class="date-entry-header">
        <span class="date-index">#${i + 1}</span>
        <span class="date-raw">${item.date}</span>
        <span class="date-parsed">${item.parsed || ""}</span>
      </div>
      <div class="date-context">…${markedCtx}…</div>
    `;
    list.appendChild(li);
  });
}

/* ── Downloads ── */

function downloadCSV() {
  if (!extractedDates.length) { alert("No data to download."); return; }

  const header = ["#", "Date", "Parsed (YYYY-MM-DD)", "Context"];
  const rows = extractedDates.map((d, i) => [
    i + 1,
    `"${d.date.replace(/"/g, '""')}"`,
    d.parsed || "",
    `"${(d.context || "").replace(/"/g, '""')}"`,
  ]);

  const csv = [header.join(","), ...rows.map(r => r.join(","))].join("\n");
  triggerDownload(new Blob([csv], { type: "text/csv" }), "extracted_dates.csv");
}

function downloadPDF() {
  if (!extractedDates.length) { alert("No data to download."); return; }

  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 15;
  const colW = [8, 38, 32, pageW - margin * 2 - 8 - 38 - 32]; // #, Date, Parsed, Context
  let y = margin;

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("Extracted Dates Report", margin, y);
  y += 6;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(100);
  doc.text(`Total: ${extractedDates.length} dates   |   Generated: ${new Date().toLocaleString()}`, margin, y);
  y += 8;

  // Table header
  doc.setFillColor(255, 204, 0);
  doc.setTextColor(0);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.rect(margin, y, pageW - margin * 2, 7, "F");
  const headers = ["#", "Date Found", "Parsed Date", "Context"];
  let x = margin + 1;
  headers.forEach((h, i) => { doc.text(h, x, y + 5); x += colW[i]; });
  y += 8;

  // Rows
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);

  extractedDates.forEach((d, idx) => {
    const contextLines = doc.splitTextToSize(d.context || "", colW[3] - 2);
    const rowH = Math.max(6, contextLines.length * 4 + 2);

    if (y + rowH > doc.internal.pageSize.getHeight() - margin) {
      doc.addPage();
      y = margin;
    }

    // Alternating row background
    if (idx % 2 === 0) {
      doc.setFillColor(245, 245, 245);
      doc.rect(margin, y, pageW - margin * 2, rowH, "F");
    }

    doc.setTextColor(0);
    x = margin + 1;
    doc.text(String(idx + 1), x, y + 4); x += colW[0];
    doc.setFont("helvetica", "bold");
    doc.text(d.date, x, y + 4, { maxWidth: colW[1] - 2 }); x += colW[1];
    doc.setFont("helvetica", "normal");
    doc.setTextColor(60, 100, 180);
    doc.text(d.parsed || "", x, y + 4); x += colW[2];
    doc.setTextColor(60);
    doc.text(contextLines, x, y + 4);

    y += rowH;

    // Row separator
    doc.setDrawColor(220);
    doc.line(margin, y, pageW - margin, y);
  });

  doc.save("extracted_dates.pdf");
}

function triggerDownload(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
