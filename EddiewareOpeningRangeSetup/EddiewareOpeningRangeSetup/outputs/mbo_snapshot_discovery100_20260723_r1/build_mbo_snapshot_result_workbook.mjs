import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir =
  "C:/Users/k_99_/Desktop/codding/OpeningRangeSetup/EddiewareOpeningRangeSetup/EddiewareOpeningRangeSetup/outputs/mbo_snapshot_discovery100_20260723_r1";
const previewsDir = path.join(outputDir, "workbook_previews");
await fs.mkdir(previewsDir, { recursive: true });

const sources = [
  ["Metrics", "mbo_snapshot_discovery_metrics.csv"],
  ["Direction Cells", "mbo_snapshot_direction_stability_cells.csv"],
  ["Direction Detail", "mbo_snapshot_direction_stability_detail.csv"],
  ["Feature Summary", "mbo_snapshot_feature_summary_by_family.csv"],
  ["Predictions", "mbo_snapshot_discovery_loyo_predictions.csv"],
  ["Feature Ledger", "mbo_snapshot_8_feature_ledger_100.csv"],
];

const metricsText = await fs.readFile(
  path.join(outputDir, sources[0][1]),
  "utf8",
);
const workbook = await Workbook.fromCSV(metricsText, {
  sheetName: sources[0][0],
});
for (const [sheetName, fileName] of sources.slice(1)) {
  const csvText = await fs.readFile(path.join(outputDir, fileName), "utf8");
  await workbook.fromCSV(csvText, { sheetName });
}

const results = workbook.worksheets.add("Results");
results.showGridLines = false;
results.freezePanes.freezeRows(2);
results.getRange("A1:H1").merge();
results.getRange("A1").values = [
  ["MBO Snapshot 8 — validación discovery causal"],
];
results.getRange("A1:H1").format = {
  fill: "#0F172A",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
results.getRange("A1:H1").format.rowHeight = 30;

results.getRange("A3:B3").values = [["Veredicto", null]];
results.getRange("B3").formulas = [
  ["=IF('Metrics'!X4=\"SUPERA_PUERTA_DISCOVERY\",\"CAPAZ EN DISCOVERY\",\"NO CAPAZ EN DISCOVERY\")"],
];
results.getRange("A3:B3").format = {
  fill: "#FEE2E2",
  font: { bold: true, color: "#991B1B" },
  borders: { preset: "outside", style: "medium", color: "#DC2626" },
};

results.getRange("A5:H5").values = [[
  "BA",
  "AUC",
  "Sensibilidad A",
  "Especificidad B",
  "IC95% inferior",
  "p permutación",
  "Mínimo año/lado",
  "Celdas coherentes",
]];
results.getRange("A5:H5").format = {
  fill: "#E2E8F0",
  font: { bold: true, color: "#0F172A" },
  horizontalAlignment: "center",
};
results.getRange("A6:H6").formulas = [[
  "='Metrics'!H4",
  "='Metrics'!I4",
  "='Metrics'!J4",
  "='Metrics'!K4",
  "='Metrics'!L4",
  "='Metrics'!N4",
  "='Metrics'!O4",
  "='Metrics'!P4",
]];
results.getRange("A6:G6").format.numberFormat = "0.000";
results.getRange("H6").format.numberFormat = "0";
results.getRange("A6:H6").format = {
  font: { bold: true, color: "#0F172A", size: 12 },
  horizontalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: "#94A3B8" },
};

results.getRange("A8:C8").values = [[
  "Puerta",
  "Valor combinado",
  "Umbral",
]];
results.getRange("A8:C8").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
results.getRange("A9:A16").values = [
  ["Balanced accuracy"],
  ["ROC AUC"],
  ["Sensibilidad A"],
  ["Especificidad B"],
  ["IC95% inferior BA"],
  ["p permutación"],
  ["Mínimo año/lado"],
  ["Coherencia física"],
];
results.getRange("B9:B16").formulas = [
  ["='Metrics'!H4"],
  ["='Metrics'!I4"],
  ["='Metrics'!J4"],
  ["='Metrics'!K4"],
  ["='Metrics'!L4"],
  ["='Metrics'!N4"],
  ["='Metrics'!O4"],
  ["='Metrics'!P4"],
];
results.getRange("C9:C16").values = [
  [0.65],
  [0.68],
  [0.60],
  [0.60],
  [0.55],
  [0.05],
  [0.55],
  [5],
];
results.getRange("B9:C15").format.numberFormat = "0.000";
results.getRange("B16:C16").format.numberFormat = "0";
results.getRange("A8:C16").format.borders = {
  preset: "outside",
  style: "thin",
  color: "#94A3B8",
};

results.getRange("E8:G8").values = [["Bloque", "BA LOYO", "AUC LOYO"]];
results.getRange("E8:G8").format = {
  fill: "#1D4ED8",
  font: { bold: true, color: "#FFFFFF" },
};
results.getRange("E9:E11").formulas = [
  ["='Metrics'!A2"],
  ["='Metrics'!A3"],
  ["='Metrics'!A4"],
];
results.getRange("F9:G11").formulas = [
  ["='Metrics'!H2", "='Metrics'!I2"],
  ["='Metrics'!H3", "='Metrics'!I3"],
  ["='Metrics'!H4", "='Metrics'!I4"],
];
results.getRange("F9:G11").format.numberFormat = "0.000";

results.getRange("A18:H20").merge();
results.getRange("A18").values = [[
  "Interpretación: MBO Snapshot 8 no mejora MATRIX y no supera permutación ni estabilidad. Estas métricas son de clasificación A/B, no WR ni PF. 2025–2026 permanece sellado.",
]];
results.getRange("A18:H20").format = {
  fill: "#FFF7ED",
  font: { color: "#9A3412" },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: "#FDBA74" },
};

const chart = results.charts.add("bar", results.getRange("E8:G11"));
chart.title = "Separación fuera de año: MATRIX vs MBO";
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.yAxis = {
  numberFormatCode: "0.00",
  min: 0,
  max: 1,
};
chart.setPosition("J2", "Q18");

results.getRange("A:Q").format.font = { name: "Aptos", size: 10 };
results.getRange("A1:Q20").format.autofitColumns();
results.getRange("A1:Q20").format.autofitRows();
results.getRange("A:A").format.columnWidth = 25;
results.getRange("E:E").format.columnWidth = 42;
results.getRange("A18:H20").format.rowHeight = 26;

for (const [sheetName] of sources) {
  const sheet = workbook.worksheets.getItem(sheetName);
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  const used = sheet.getUsedRange();
  used.format.font = { name: "Aptos", size: 9 };
  used.getRow(0).format = {
    fill: "#334155",
    font: { bold: true, color: "#FFFFFF", size: 9 },
    wrapText: true,
  };
  used.format.autofitColumns();
  used.format.autofitRows();
}

const inspect = await workbook.inspect({
  kind: "table",
  range: "Results!A1:H20",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 8,
});
console.log(inspect.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const previewTargets = [
  ["Results", "A1:Q20"],
  ["Metrics", "A1:X4"],
  ["Direction Cells", "A1:G7"],
  ["Direction Detail", "A1:J12"],
  ["Feature Summary", "A1:Q10"],
  ["Predictions", "A1:M12"],
  ["Feature Ledger", "A1:V12"],
];
for (const [sheetName, range] of previewTargets) {
  const blob = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  const fileName = sheetName.toLowerCase().replaceAll(" ", "_") + ".png";
  await fs.writeFile(
    path.join(previewsDir, fileName),
    new Uint8Array(await blob.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "MBO_SNAPSHOT_DISCOVERY_100_RESULTS.xlsx"));
