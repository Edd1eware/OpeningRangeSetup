import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const resultsRoot = String.raw`C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score`;
const runRoot = path.join(resultsRoot, "visual_tests", "04_run_replay_lb_dom_three_families_dst_2025_2026_runs");
const outputDir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, "$1").replaceAll("/", "\\"));
const outputPath = path.join(outputDir, "R2_DOM_features_para_Claude_Fable_20260721.xlsx");
const detectorVersion = "liquidity-burst-detector-2026-07-20-v5-dom-geometry";

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(field); field = ""; }
    else if (ch === '\n') { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += ch;
  }
  if (field.length || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  return rows.filter(r => r.some(v => v !== ""));
}

async function readObjects(filePath) {
  const rows = parseCsv(await fs.readFile(filePath, "utf8"));
  if (!rows.length) return [];
  const headers = rows[0].map(v => v.replace(/^\uFEFF/, ""));
  return rows.slice(1).map(values => Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""])));
}

function scalar(value, header = "") {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value).trim();
  if (/^(TRUE|FALSE)$/i.test(text)) return text.toUpperCase() === "TRUE";
  if (!/(Id|ID|Timestamp|Time|fecha|Side|Label|Reason|Source|VERSION|Window|Status|Mask|Type)/i.test(header)
      && /^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$/.test(text)) return Number(text);
  return text;
}

function matrix(rows, columns) {
  return [columns, ...rows.map(row => columns.map(column => scalar(row[column], column)))];
}

function finite(value) { return Number.isFinite(Number(value)); }

function family(row) {
  const result = String(row.Result_Label || "").toUpperCase();
  const mae = Number(row.MAE_ticks), mfe = Number(row.MFE_ticks);
  const sl = Number(row.Initial_SL_ticks), tp = Number(row.Initial_TP_ticks);
  const valid = [mae, mfe, sl, tp].every(Number.isFinite) && sl > 0 && tp > 0;
  if (result === "TP" && valid && mae <= 10 && mfe >= tp) return "A_CLEAN_ABSORPTION";
  if (result === "SL" && valid && mfe <= 10 && mae >= sl) return "B_CLEAN_CONTINUATION";
  if (valid) return "C_VARIABLE_TRADE";
  return "EXCLUDED_NO_PATH_METRICS";
}

const domFeatures = [
  "DOM_Spread_Ticks",
  "DOM_Directional_Microprice_Ticks",
  "DOM_Directional_Depth_Imbalance_L1",
  "DOM_Directional_Depth_Imbalance_L3",
  "DOM_Directional_Depth_Imbalance_L5",
  "DOM_Ahead_Depth_Per_Aggressive_L3",
  "DOM_Ahead_L1_Concentration_L5",
  "DOM_Directional_PullStack_1s",
  "DOM_Directional_PullStack_3s",
  "DOM_Ahead_Stack_Share_1s",
  "DOM_Near_Churn_Per_Aggressive_1s",
];
const domAudit = [
  "DOM_Snapshot_Valid", "DOM_Exclusion_Reason", "DOM_Bid_Level_Count", "DOM_Ask_Level_Count",
  "DOM_Best_Bid", "DOM_Best_Ask", "DOM_Ahead_Depth_L3", "DOM_Behind_Depth_L3",
  "DOM_Near_Update_Count_1s", "DOM_Near_Update_Count_3s",
];

const bursts = (await readObjects(path.join(resultsRoot, "burst_events.csv")))
  .filter(row => row.Detector_VERSION === detectorVersion);
const responses = (await readObjects(path.join(resultsRoot, "burst_response_events.csv")))
  .filter(row => row.Detector_VERSION === detectorVersion);
const inputs = await readObjects(path.join(resultsRoot, "trade_inputs.csv"));

const sessionFolder = path.join(runRoot, "X10_R1");
const sessionFiles = (await fs.readdir(sessionFolder))
  .filter(name => /^score_trade_result_\d{4}-\d{2}-\d{2}_NY\.csv$/.test(name)).sort();
const sessionRows = [];
for (const name of sessionFiles) {
  const rows = await readObjects(path.join(sessionFolder, name));
  if (rows[0]) sessionRows.push(rows[0]);
}
const outcomeByDate = new Map(sessionRows.map(row => [row.fecha, row]));
const burstById = new Map(bursts.map(row => [row.BurstId, row]));

const labeled = [];
for (const input of inputs) {
  if (!/^(TRUE|1)$/i.test(String(input.Liquidity_Burst_AtEntry || ""))) continue;
  const burst = burstById.get(input.Liquidity_Burst_ID_AtEntry);
  const outcome = outcomeByDate.get(input.fecha);
  if (!burst || !outcome) continue;
  labeled.push({
    fecha: input.fecha,
    BurstId: burst.BurstId,
    family: family(outcome),
    Result_Label: outcome.Result_Label,
    MAE_ticks: outcome.MAE_ticks,
    MFE_ticks: outcome.MFE_ticks,
    Initial_SL_ticks: outcome.Initial_SL_ticks,
    Initial_TP_ticks: outcome.Initial_TP_ticks,
    Execution_Side: input.Side,
    Burst_Side: burst.Side,
    Entry_price: outcome.Entry_price,
    Burst_Timestamp_UTC: burst.Timestamp_UTC,
    ...Object.fromEntries(domAudit.map(c => [c, burst[c]])),
    ...Object.fromEntries(domFeatures.map(c => [c, burst[c]])),
  });
}

const burstColumns = ["BurstId", "Timestamp_UTC", "Timestamp_NY", "Side", "Price", ...domAudit, ...domFeatures];
const labeledColumns = [
  "fecha", "BurstId", "family", "Result_Label", "MAE_ticks", "MFE_ticks",
  "Initial_SL_ticks", "Initial_TP_ticks", "Execution_Side", "Burst_Side", "Entry_price",
  "Burst_Timestamp_UTC", ...domAudit, ...domFeatures,
];
const responseColumns = [
  "BurstId", "Burst_Timestamp_UTC", "Response_Available_Timestamp_UTC", "Response_Horizon_Seconds",
  "Side", "Burst_Price", "Response_Price", "Directional_Displacement_Ticks", "Response_MFE_Ticks",
  "Response_MAE_Ticks", "Acceptance_Dwell_Ratio", "Reclaim_Count", "Directional_Delta",
  "Response_Volume", "Counterflow_Share", "Path_Efficiency", "Model_Eligibility",
];
const sessionColumns = [
  "fecha", "Side", "Signal_Source", "EntryTime_NY", "ExitTime_NY", "Entry_price",
  "Initial_SL_ticks", "Initial_TP_ticks", "Initial_RR", "Result_Label", "result TP SL BE",
  "MAE_ticks", "MFE_ticks", "Exit_Reason", "Exporter_VERSION",
];

const dictionary = [
  ["DOM_Spread_Ticks", "(best ask-best bid)/tick", "B > A esperado", "t0", "ticks"],
  ["DOM_Directional_Microprice_Ticks", "burst_sign*(microprice-midpoint)/tick", "B > A esperado", "t0", "ticks"],
  ["DOM_Directional_Depth_Imbalance_L1", "burst_sign*(bid L1-ask L1)/(bid+ask)", "B > A esperado", "t0", "ratio"],
  ["DOM_Directional_Depth_Imbalance_L3", "burst_sign*(bid L3-ask L3)/(bid+ask)", "B > A esperado", "t0", "ratio"],
  ["DOM_Directional_Depth_Imbalance_L5", "burst_sign*(bid L5-ask L5)/(bid+ask)", "B > A esperado", "t0", "ratio"],
  ["DOM_Ahead_Depth_Per_Aggressive_L3", "ahead passive depth L3/max(gross aggression,1)", "A > B esperado", "t0", "ratio"],
  ["DOM_Ahead_L1_Concentration_L5", "ahead L1/sum(ahead L1:L5)", "A > B esperado", "t0", "ratio"],
  ["DOM_Directional_PullStack_1s", "(behind net add-ahead net add)/churn top5", "B > A esperado", "[-1s,t0]", "ratio"],
  ["DOM_Directional_PullStack_3s", "(behind net add-ahead net add)/churn top5", "B > A esperado", "[-3s,t0]", "ratio"],
  ["DOM_Ahead_Stack_Share_1s", "ahead adds/(ahead adds+removes)", "A > B esperado", "[-1s,t0]", "ratio"],
  ["DOM_Near_Churn_Per_Aggressive_1s", "sum(abs(depth changes top5))/aggression", "A > B esperado", "[-1s,t0]", "ratio"],
];

const workbook = Workbook.create();
const navy = "#17365D", blue = "#D9EAF7", pale = "#EEF5FA", orange = "#FCE4D6";

function addDataSheet(name, data, columns, tableName) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const values = matrix(data, columns);
  const range = sheet.getRangeByIndexes(0, 0, values.length, columns.length);
  range.values = values;
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format = {
    fill: navy, font: { bold: true, color: "#FFFFFF" }, wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRangeByIndexes(1, 0, Math.max(1, values.length - 1), columns.length).format = {
    fill: "#FFFFFF", font: { color: "#1F2937" },
  };
  range.format.autofitColumns();
  range.format.autofitRows();
  for (let col = 0; col < columns.length; col++) {
    const header = columns[col];
    const colRange = sheet.getRangeByIndexes(0, col, values.length, 1);
    if (/Timestamp|Time|Reason|Exclusion|family|Source|VERSION/i.test(header)) colRange.format.columnWidth = 22;
    else colRange.format.columnWidth = 14;
    if (/ticks|Price|Depth|Ratio|Imbalance|Share|Churn|Count|MAE|MFE|RR|Volume/i.test(header)) {
      sheet.getRangeByIndexes(1, col, Math.max(1, values.length - 1), 1).format.numberFormat = "0.000";
    }
  }
  sheet.freezePanes.freezeRows(1);
  if (values.length > 1) sheet.tables.add(range, true, tableName);
  return sheet;
}

const readme = workbook.worksheets.add("README");
readme.showGridLines = false;
readme.getRange("A1:F1").merge();
readme.getRange("A1").values = [["R2 DOM — paquete exploratorio para Claude Fable"]];
readme.getRange("A1:F1").format = { fill: navy, font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 30 };
const readmeRows = [
  ["Objetivo", "Proponer hipótesis causales que separen ABSORCIÓN LIMPIA (A) de CONTINUACIÓN LIMPIA (B) usando exclusivamente features DOM disponibles en t0."],
  ["Estado", "R2 incompleta y exploratoria. No usar como validación final ni mezclar con la R3 limpia."],
  ["Familia A", "TP con MAE <=10 ticks y MFE >= TP inicial."],
  ["Familia B", "SL con MFE <=10 ticks y MAE >= SL inicial."],
  ["Familia C", "Trayectoria terminal medible que no cumple A ni B; tratar como abstención/descriptiva."],
  ["Predictores permitidos", "Solo las 11 columnas DOM_* de la hoja DOM_Labeled."],
  ["Prohibido como predictor", "Result_Label, MAE, MFE, respuesta 1/3/5s, salida y cualquier variable posterior a t0."],
  ["Bursts v5", bursts.length],
  ["Entradas etiquetadas", labeled.length],
  ["Sesiones X10 guardadas", sessionRows.length],
  ["Respuestas post-burst", responses.length],
  ["Fuente", runRoot],
];
readme.getRangeByIndexes(2, 0, readmeRows.length, 2).values = readmeRows;
readme.getRange("A3:A14").format = { fill: blue, font: { bold: true, color: navy }, wrapText: true };
readme.getRange("B3:B14").format = { fill: "#FFFFFF", wrapText: true };
readme.getRange("A3:B14").format.borders = { preset: "inside", style: "thin", color: "#D9E2F3" };
readme.getRange("A:B").format.columnWidth = 26;
readme.getRange("B:B").format.columnWidth = 95;
readme.getRange("A3:B14").format.autofitRows();
readme.freezePanes.freezeRows(1);

addDataSheet("DOM_Labeled", labeled, labeledColumns, "DomLabeledTable");
addDataSheet("DOM_All_Bursts", bursts, burstColumns, "DomBurstsTable");
addDataSheet("Responses_Audit", responses, responseColumns, "ResponseAuditTable");
addDataSheet("Session_Results", sessionRows, sessionColumns, "SessionResultsTable");

const dictSheet = workbook.worksheets.add("Data_Dictionary");
dictSheet.showGridLines = false;
const dictValues = [["Feature", "Fórmula física", "Dirección preregistrada", "Ventana causal", "Unidad"], ...dictionary];
dictSheet.getRangeByIndexes(0, 0, dictValues.length, 5).values = dictValues;
dictSheet.getRange("A1:E1").format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, wrapText: true };
dictSheet.getRange("A2:E12").format = { fill: pale, wrapText: true };
dictSheet.getRange("A1:E12").format.autofitRows();
dictSheet.getRange("A:A").format.columnWidth = 38;
dictSheet.getRange("B:B").format.columnWidth = 48;
dictSheet.getRange("C:E").format.columnWidth = 22;
dictSheet.tables.add(dictSheet.getRange("A1:E12"), true, "DomDictionaryTable");
dictSheet.freezePanes.freezeRows(1);

await fs.mkdir(path.join(outputDir, "previews"), { recursive: true });
const renderRanges = {
  README: "A1:B14",
  DOM_Labeled: `A1:L${Math.min(20, labeled.length + 1)}`,
  DOM_All_Bursts: `A1:L${Math.min(20, bursts.length + 1)}`,
  Responses_Audit: `A1:Q${Math.min(20, responses.length + 1)}`,
  Session_Results: `A1:O${Math.min(20, sessionRows.length + 1)}`,
  Data_Dictionary: "A1:E12",
};
for (const [sheetName, range] of Object.entries(renderRanges)) {
  const blob = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, "previews", `${sheetName}.png`), new Uint8Array(await blob.arrayBuffer()));
}

const inspect = await workbook.inspect({ kind: "table", range: "README!A1:B14", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 4 });
console.log(inspect.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, bursts: bursts.length, labeled: labeled.length, sessions: sessionRows.length, responses: responses.length }));
