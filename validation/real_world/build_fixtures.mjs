/** Generate independent XLSX inputs for the real-world generalization suite. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCENARIOS = path.join(HERE, "scenarios");
const RENDERS = path.join(HERE, "rendered_sources");


function rectangular(rows) {
  const width = Math.max(...rows.map((row) => row.length));
  return rows.map((row) => Array.from({ length: width }, (_, index) => row[index] ?? null));
}


function addSheet(workbook, name, rows, headerRows = []) {
  const values = rectangular(rows);
  const sheet = workbook.worksheets.add(name);
  const used = sheet.getRangeByIndexes(0, 0, values.length, values[0].length);
  used.values = values;
  used.format.font = { name: "Arial", size: 10, color: "#111827" };
  used.format.autofitColumns();
  used.format.autofitRows();
  for (const rowNumber of headerRows) {
    sheet.getRangeByIndexes(rowNumber, 0, 1, values[0].length).format = {
      fill: "#1F4E78",
      font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
    };
  }
  sheet.getRangeByIndexes(0, 0, values.length, 1).format.columnWidth = 24;
  if (values[0].length > 1) {
    sheet.getRangeByIndexes(0, 1, values.length, 1).format.columnWidth = 36;
  }
  if (values[0].length > 2) {
    sheet.getRangeByIndexes(0, 2, values.length, values[0].length - 2).format.columnWidth = 18;
  }
  return sheet;
}


function financialRows({ code, period, actual, budget, ytdFactor, leading = 0 }) {
  const ytd = (value) => value * ytdFactor;
  const annual = (value) => value * 4;
  const row = (account, label, a, b) => [account, label, a, b, a - b, b ? (a - b) / Math.abs(b) : null, ytd(a), ytd(b), ytd(a - b), b ? (a - b) / Math.abs(b) : null, annual(b)];
  const head = [
    [`Property = ${code} ${code}con`],
    ["Budget Comparison"],
    [`Period = ${period}`],
    ["Book = Accrual ; Tree = rp-cashflow"],
    [null, null, "PTD Actual", "PTD Budget", "Variance", "% Var", "YTD Actual", "YTD Budget", "Variance", "% Var", "Annual Budget"],
  ];
  const rows = [
    ...Array.from({ length: leading }, () => [null]),
    ...head,
    ["3998-0000", "    REVENUE"],
    ["3999-0000", "      RENTAL INCOME"],
    row("4000-0000", "        Gross Potential Rent", actual.gpr, budget.gpr),
    row("4001-0000", "        Loss/Gain to Lease", actual.gain, budget.gain),
    row("4004-0000", "        Less: Concessions", actual.concessions, budget.concessions),
    row("4006-0000", "        Less: Vacancy", actual.vacancy, budget.vacancy),
    row("4016-0000", "        Pet Rent", actual.pet, budget.pet),
    row("4060-0000", "        NET RENTAL INCOME", actual.netRental, budget.netRental),
    ["4080-9999", "    UTILITY INCOME"],
    row("4081-0100", "        TOTAL UTILITY INCOME", actual.utility, budget.utility),
    ["4400-0000", "    OTHER INCOME"],
    row("4407-0050", "        Less: Write Off Bad Debt", -10000, -8000),
    row("4407-0055", "        Former Resident Collections", 5000, 4000),
    row("4699-0000", "        TOTAL OTHER INCOME", actual.other, budget.other),
    row("4999-0000", "            TOTAL REVENUE", actual.revenue, budget.revenue),
    ["5000-0000", "    EXPENSES"],
    ["5019-0000", "      PAYROLL"],
    row("5055-0000", "        TOTAL PAYROLL", actual.payroll, budget.payroll),
    ["5056-0000", "      GENERAL & ADMINISTRATIVE"],
    row("5056-1000", "        TOTAL GENERAL & ADMINISTRATIVE", actual.ga, budget.ga),
    ["5095-0000", "      MARKETING"],
    row("5108-0000", "        TOTAL MARKETING", actual.marketing, budget.marketing),
    ["5200-0000", "      REPAIRS & MAINTENANCE"],
    row("5215-0000", "        TOTAL REPAIRS & MAINTENANCE", actual.repairs, budget.repairs),
    ["5299-0000", "      UTILITIES"],
    row("5399-0000", "        TOTAL UTILITIES", actual.utilities, budget.utilities),
    ["5460-0000", "      MANAGEMENT FEES"],
    row("5465-0000", "        TOTAL MANAGEMENT FEES", actual.management, budget.management),
    ["5499-0000", "      TAXES"],
    row("5515-0000", "        TOTAL TAXES", actual.taxes, budget.taxes),
    ["5519-9999", "      INSURANCE"],
    row("5520-0010", "        TOTAL INSURANCE", actual.insurance, budget.insurance),
    row("6500-0000", "            TOTAL EXPENSES", actual.opex, budget.opex),
    row("6700-0000", "            NET OPERATING INCOME/(LOSS)", actual.noi, budget.noi),
    ["6800-0000", "      DEBT SERVICE"],
    row("6810-0000", "        TOTAL DEBT SERVICE", actual.debt, budget.debt),
    row("7000-0000", "            NET CASH FLOW AFTER DEBT SERVICE", actual.cashFlow, budget.cashFlow),
    [null, "    INTERIOR RENOVATIONS"],
    row("7100-0016", "        Plumbing Replacement", actual.capexPlumbing, budget.capexPlumbing),
    row("7100-0020", "        HVAC Additions", actual.capexHvac, budget.capexHvac),
    row("7100-0009", "        Paint", actual.capexPaint, budget.capexPaint),
    [null, "          TOTAL INTERIOR RENOVATIONS", actual.capex, budget.capex, actual.capex - budget.capex, null, ytd(actual.capex), ytd(budget.capex), ytd(actual.capex - budget.capex), null, annual(budget.capex)],
    [null, null, actual.capex, budget.capex, null, null, ytd(actual.capex), ytd(budget.capex), null, null, annual(budget.capex)],
  ];
  return rows;
}


function ptdOnly(rows) {
  return rows.map((row) => [row[0] ?? null, row[1] ?? null, row[2] ?? null, row[3] ?? null, row[10] ?? null]);
}


function balanceRows({ code, period, purchase, furniture, equity, loan, interest }) {
  return [
    [`Property = ${code} ${code}con`],
    ["Balance Sheet (With Period Change)"],
    [`Period = ${period}`],
    ["Book = Accrual ; Tree = ysi_bs"],
    [null, null, "Balance", "Beginning", "Net"],
    [null, null, "Current Period", "Balance", "Change"],
    ["0999-0000", "    ASSETS"],
    ["1500-0029", "        Total Building", purchase - furniture, purchase - furniture, 0],
    ["1500-0049", "        Total Furniture & Fixtures", furniture, furniture, 0],
    ["1995-0000", "        TOTAL ASSETS", purchase + 850000, purchase + 740000, 110000],
    ["1997-0000", "    LIABILITIES"],
    ["2139-0001", "        Accrued Interest", interest, interest - 2500, 2500],
    ["2310-0000", "        Mortgage Payable", loan, loan, 0],
    ["2310-0020", "        TOTAL MORTGAGE PAYABLE", loan, loan, 0],
    ["2999-0000", "    EQUITY"],
    ["3015-0000", "        Owner Contributions", equity, equity, 0],
    ["3994-0000", "        TOTAL EQUITY", equity - 125000, equity - 150000, 25000],
  ];
}


function rentRollRows({ name, code, asOf, units, occupied, future, marketRent, residentRent, leading = 0 }) {
  const pct = (occupied / units) * 100;
  return [
    ...Array.from({ length: leading }, () => [null]),
    ["Rent Roll"],
    [`${name} (${code})`],
    [`As Of = ${asOf}`],
    [null],
    ["Property", "State", "Total Units", "Name", "Market Rent", "Resident Rent", "Average Market Rent", "Average Resident Rent"],
    [code, "TX", units, name, marketRent * units, residentRent * occupied, marketRent, residentRent],
    [null],
    ["Summary Groups", "Square Footage", "Market Rent", "Actual Rent", "# Of Units", "% Unit Occupancy"],
    ["Current/Notice/Vacant Residents", units * 825, marketRent * units, residentRent * occupied, units, pct],
    ["Future Residents/Applicants", future * 825, future * marketRent, 0, future, null],
    ["Occupied Units", occupied * 825, marketRent * occupied, residentRent * occupied, occupied, pct],
    ["Total Vacant Units", (units - occupied) * 825, marketRent * (units - occupied), 0, units - occupied, 100 - pct],
    ["Totals:", units * 825, marketRent * units, residentRent * occupied, units, 100],
  ];
}


function scheduleRows({ name, code, asOf, types, leading = 0 }) {
  const totalUnits = types.reduce((sum, item) => sum + item.units, 0);
  const totalOccupied = types.reduce((sum, item) => sum + item.occupied, 0);
  const weighted = (key, weight) => types.reduce((sum, item) => sum + item[key] * item[weight], 0) / types.reduce((sum, item) => sum + item[weight], 0);
  return [
    ...Array.from({ length: leading }, () => [null]),
    ["Market Rent Schedule"],
    [`${name} (${code})`],
    [`As Of = ${asOf}`],
    ["Unit Type", "Units", "Unit Type Rent", "Sq Ft", "Total Unit Type Rent", "Occupied Units", "Average Resident Rent"],
    ...types.map((item) => [`${item.label} (${item.code})`, item.units, item.market, item.sqft, item.units * item.market, item.occupied, item.resident]),
    ["Grand Total", totalUnits, weighted("market", "units"), weighted("sqft", "units"), types.reduce((sum, item) => sum + item.units * item.market, 0), totalOccupied, weighted("resident", "occupied")],
  ];
}


function ltoRows({ name, start, end, rows, leading = 0 }) {
  const group = [null, null, null, null, null, "New Lease Term", null, null, null, null, null, null, "Previous Lease Term"];
  const header = ["Property", "Resident Name", "Unit Type", "Sqft", "Unit", "Lease Start", "Lease Term", "Market Rent", "Lease Rent", "Total Concessions", "# Months Free", "Effective Rent", "Lease Rent", "Total Concessions", "Lease Term", "Effective Rent", "Rent Change", "% Change"];
  const make = (record) => [name, record.resident, record.type, record.sqft, record.unit, record.date, 12, record.market, record.current, record.concession ?? 0, 0, record.current - (record.concession ?? 0) / 12, record.prior, 0, 12, record.prior, record.current - record.prior, (record.current - record.prior) / record.prior];
  const renewals = rows.filter((item) => item.kind === "renewal");
  const moveIns = rows.filter((item) => item.kind === "move_in");
  return [
    ...Array.from({ length: leading }, () => [null]),
    [null, "Lease Renewals"],
    [null, `Lease Renewals between ${start} and ${end}`],
    [null],
    group,
    header,
    ...renewals.map(make),
    [null],
    [null, "Move Ins"],
    [null, `Move In between ${start} and ${end}`],
    [null],
    group,
    header,
    ...moveIns.map(make),
  ];
}


function listingsRows(properties, leading = 0) {
  const rows = [
    ...Array.from({ length: leading }, () => [null]),
    ["Unit-Level Data"],
    ["Property Name", "Address", "Floorplan", "Unit #", "Beds", "Baths", "Sqft", "First Listed", "Leased Date", "Active Listing?", "Days on Mkt", "Asking Rent", "Effective Rent"],
  ];
  for (const property of properties) {
    for (const listing of property.listings) {
      rows.push([property.name, property.address, listing.plan, listing.unit, listing.beds, listing.baths, listing.sqft, listing.listed, listing.leased, listing.active, listing.days, listing.asking, listing.effective]);
    }
  }
  return rows;
}


function compsRows(properties, leading = 0) {
  return [
    ...Array.from({ length: leading }, () => [null]),
    ["Rent Comps"],
    ["Property", "Address", "Similarity", "Dist. (mi)", "Quality", "Yr Built", "# Units", "Stories", "Avg Sqft", "Leased %", "Exposure %"],
    ...properties.map((property) => [property.name, property.address, property.similarity ?? "--", property.distance ?? "--", property.quality ?? 0.75, property.year, property.units, property.stories ?? 3, property.sqft, property.leased, property.exposure ?? 0.08]),
  ];
}


function costarRows(series, leading = 0) {
  return [
    ...Array.from({ length: leading }, () => [null]),
    ["Period", "Vacancy Rate", "Market Asking Rent/Unit", "Annual Rent Growth", "Inventory Units", "Under Construction Units", "Under Construction % of Inventory", "12 Mo Absorp Units", "Market Sale Price/Unit", "12 Mo Sales Vol", "Market Cap Rate"],
    ...series.map((row) => [row.period, row.vacancy, row.rent, row.growth, row.inventory, row.construction, row.construction / row.inventory, row.absorption, row.sale, row.volume, row.cap]),
  ];
}


function rentTrendRows(subject, comp, startYear, startMonth, subjectBase, compBase, leading = 0) {
  const rows = [
    ...Array.from({ length: leading }, () => [null]),
    [`${subject} vs. ${comp}`],
    ["T12 New Lease Rent Trend"],
    ["Month", `${subject} / Lease Count`, `${subject} / Gross PSF`, `${subject} / Effective PSF`, `${comp} / Lease Count`, `${comp} / Gross PSF`, `${comp} / Effective PSF`],
  ];
  for (let index = 0; index < 12; index += 1) {
    const date = new Date(Date.UTC(startYear, startMonth - 1 + index, 1));
    rows.push([date.toISOString().slice(0, 10), 4 + (index % 4), subjectBase + index * 0.012, subjectBase - 0.08 + index * 0.011, 9 + (index % 5), compBase + index * 0.01, compBase - 0.07 + index * 0.009]);
  }
  rows.push(["Total / Weighted", 66, subjectBase + 0.066, subjectBase - 0.02, 132, compBase + 0.055, compBase - 0.02]);
  return rows;
}


async function saveWorkbook(relativePath, sheets, previewSheet) {
  const workbook = Workbook.create();
  for (const spec of sheets) addSheet(workbook, spec.name, spec.rows, spec.headers ?? []);
  const outputPath = path.join(SCENARIOS, relativePath);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);

  const keyRange = await workbook.inspect({
    kind: "table",
    range: `${previewSheet}!A1:K20`,
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 11,
  });
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
    options: { useRegex: true, maxResults: 100 },
    summary: `formula error scan for ${relativePath}`,
  });
  await fs.mkdir(RENDERS, { recursive: true });
  const preview = await workbook.render({ sheetName: previewSheet, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(RENDERS, `${path.basename(relativePath, ".xlsx")}-${previewSheet.replaceAll(/[^A-Za-z0-9]+/g, "-")}.png`), new Uint8Array(await preview.arrayBuffer()));
  return { outputPath, keyRange: keyRange.ndjson, formulaErrors: formulaErrors.ndjson };
}


const HARBOR_ACTUAL = { gpr: 1200000, gain: 50000, concessions: -30000, vacancy: -80000, pet: 5000, netRental: 1145000, utility: 150000, other: 45000, revenue: 1340000, payroll: 170000, ga: 40000, marketing: 25000, repairs: 55000, utilities: 180000, management: 45000, taxes: 160000, insurance: 70000, opex: 745000, noi: 595000, debt: 420000, cashFlow: 175000, capexPlumbing: 30000, capexHvac: 20000, capexPaint: 10000, capex: 60000 };
const HARBOR_BUDGET = { gpr: 1180000, gain: 60000, concessions: -24000, vacancy: -90000, pet: 4500, netRental: 1130500, utility: 145000, other: 56500, revenue: 1332000, payroll: 168000, ga: 38000, marketing: 27000, repairs: 50000, utilities: 175000, management: 45000, taxes: 160000, insurance: 90000, opex: 753000, noi: 579000, debt: 420000, cashFlow: 159000, capexPlumbing: 35000, capexHvac: 25000, capexPaint: 8000, capex: 68000 };
const PINE_ACTUAL = { gpr: 1750000, gain: 45000, concessions: -55000, vacancy: -135000, pet: 15000, netRental: 1620000, utility: 180000, other: 80000, revenue: 1880000, payroll: 250000, ga: 70000, marketing: 35000, repairs: 90000, utilities: 250000, management: 70000, taxes: 210000, insurance: 115000, opex: 1090000, noi: 790000, debt: 500000, cashFlow: 290000, capexPlumbing: 40000, capexHvac: 35000, capexPaint: 18000, capex: 93000 };
const PINE_BUDGET = { gpr: 1780000, gain: 55000, concessions: -45000, vacancy: -120000, pet: 14000, netRental: 1684000, utility: 175000, other: 71000, revenue: 1930000, payroll: 245000, ga: 68000, marketing: 40000, repairs: 85000, utilities: 240000, management: 69000, taxes: 210000, insurance: 108000, opex: 1065000, noi: 865000, debt: 500000, cashFlow: 365000, capexPlumbing: 45000, capexHvac: 30000, capexPaint: 20000, capex: 95000 };
const LAKE_ACTUAL = { gpr: 980000, gain: 25000, concessions: -28000, vacancy: -65000, pet: 8000, netRental: 920000, utility: 90000, other: 40000, revenue: 1050000, payroll: 140000, ga: 35000, marketing: 20000, repairs: 50000, utilities: 140000, management: 35000, taxes: 120000, insurance: 70000, opex: 610000, noi: 440000, debt: 260000, cashFlow: 180000, capexPlumbing: 22000, capexHvac: 18000, capexPaint: 12000, capex: 52000 };
const LAKE_BUDGET = { gpr: 965000, gain: 30000, concessions: -25000, vacancy: -70000, pet: 7000, netRental: 907000, utility: 92000, other: 41000, revenue: 1040000, payroll: 138000, ga: 34000, marketing: 22000, repairs: 48000, utilities: 138000, management: 35000, taxes: 120000, insurance: 65000, opex: 600000, noi: 440000, debt: 260000, cashFlow: 180000, capexPlumbing: 25000, capexHvac: 20000, capexPaint: 10000, capex: 55000 };


async function main() {
  const harborTypes = [
    { label: "Studio 1 Bathroom", code: "HP.S1", units: 24, occupied: 22, sqft: 540, market: 1425, resident: 1375 },
    { label: "1 Bedroom 1 Bathroom", code: "HP.A1", units: 96, occupied: 91, sqft: 710, market: 1675, resident: 1605 },
    { label: "2 Bedroom 2 Bathroom", code: "HP.B2", units: 112, occupied: 104, sqft: 1010, market: 2100, resident: 1985 },
    { label: "3 Bedroom 2 Bathroom", code: "HP.C2", units: 32, occupied: 29, sqft: 1240, market: 2475, resident: 2320 },
  ];
  const harborListings = [
    { name: "Harbor Point", address: "880 Marina Drive, Corpus Christi, TX 78401", listings: [{ plan: "A1", unit: "A-104", beds: 1, baths: 1, sqft: 710, listed: "2026-07-02", leased: "2026-07-21", active: false, days: 19, asking: 1675, effective: 1615 }, { plan: "B2", unit: "C-208", beds: 2, baths: 2, sqft: 1010, listed: "2026-08-11", leased: null, active: true, days: 50, asking: 2125, effective: 2040 }] },
    { name: "Mariner Flats", address: "215 Shoreline Blvd, Corpus Christi, TX 78401", listings: [{ plan: "A2", unit: "310", beds: 1, baths: 1, sqft: 745, listed: "2026-06-20", leased: "2026-07-08", active: false, days: 18, asking: 1795, effective: 1720 }, { plan: "B1", unit: "414", beds: 2, baths: 2, sqft: 990, listed: "2026-08-05", leased: "2026-09-01", active: false, days: 27, asking: 2180, effective: 2085 }] },
  ];
  const harbor = await saveWorkbook("harbor_point_3q26/sources/2026_Q3_reporting_export.xlsx", [
    { name: "Read Me", rows: [["Northstar operational export"], ["Prepared for independent application validation"]] },
    { name: "Lease Activity", rows: ltoRows({ name: "Harbor Point", start: "2026-07-01", end: "2026-09-30", leading: 1, rows: [{ kind: "renewal", resident: "Resident 101", type: "HP.A1", sqft: 710, unit: "A-101", date: "2026-07-15", market: 1675, current: 1600, prior: 1540 }, { kind: "renewal", resident: "Resident 203", type: "HP.B2", sqft: 1010, unit: "C-203", date: "2026-08-01", market: 2100, current: 2010, prior: 1940 }, { kind: "move_in", resident: "Resident 118", type: "HP.A1", sqft: 710, unit: "A-118", date: "2026-09-05", market: 1695, current: 1625, prior: 1580 }, { kind: "move_in", resident: "Resident 307", type: "HP.C2", sqft: 1240, unit: "D-307", date: "2026-09-18", market: 2475, current: 2350, prior: 2290 }] }), headers: [5, 13] },
    { name: "Q3 Financial Detail", rows: financialRows({ code: "81001", period: "Jul 2026-Sep 2026", actual: HARBOR_ACTUAL, budget: HARBOR_BUDGET, ytdFactor: 3, leading: 1 }), headers: [5] },
    { name: "June Rent Position", rows: rentRollRows({ name: "Harbor Point", code: "81001", asOf: "2026-06-30", units: 264, occupied: 242, future: 7, marketRent: 1910, residentRent: 1805 }), headers: [8] },
    { name: "September Unit Mix", rows: scheduleRows({ name: "Harbor Point", code: "81001", asOf: "2026-09-30", types: harborTypes, leading: 2 }), headers: [6] },
    { name: "September Rent Position", rows: rentRollRows({ name: "Harbor Point", code: "81001", asOf: "2026-09-30", units: 264, occupied: 246, future: 8, marketRent: 1940, residentRent: 1845, leading: 1 }), headers: [9] },
    { name: "June Unit Mix", rows: scheduleRows({ name: "Harbor Point", code: "81001", asOf: "2026-06-30", types: harborTypes.map((item) => ({ ...item, resident: item.resident - 35 })) }), headers: [4] },
    { name: "Balance Detail", rows: balanceRows({ code: "81001", period: "Jul 2026-Sep 2026", purchase: 42240000, furniture: 440000, equity: 12500000, loan: 28000000, interest: 120000 }), headers: [4, 5] },
    { name: "Market Listings", rows: listingsRows(harborListings, 2), headers: [3] },
    { name: "Peer Summary", rows: compsRows([{ name: "Harbor Point", address: "880 Marina Drive, Corpus Christi, TX 78401", year: 1988, units: 264, sqft: 856, leased: 0.932 }, { name: "Mariner Flats", address: "215 Shoreline Blvd, Corpus Christi, TX 78401", similarity: 0.91, distance: 1.4, year: 1996, units: 308, sqft: 875, leased: 0.945 }, { name: "Bayview Landing", address: "1201 Ocean Drive, Corpus Christi, TX 78404", similarity: 0.86, distance: 2.7, year: 2002, units: 240, sqft: 902, leased: 0.938 }], 1), headers: [2] },
    { name: "Submarket History", rows: costarRows([{ period: "2026 Q3", vacancy: 0.08, rent: 1780, growth: 0.025, inventory: 15420, construction: 380, absorption: 275, sale: 145000, volume: 82500000, cap: 0.057 }, { period: "2026 Q2", vacancy: 0.085, rent: 1750, growth: 0.02, inventory: 15260, construction: 420, absorption: 240, sale: 143500, volume: 79000000, cap: 0.058 }, { period: "2026 Q1", vacancy: 0.089, rent: 1715, growth: 0.016, inventory: 15120, construction: 460, absorption: 215, sale: 141000, volume: 74500000, cap: 0.059 }], 2), headers: [2] },
    { name: "New Lease Trend", rows: rentTrendRows("Harbor Point", "Coastal Comp Set", 2025, 10, 2.16, 2.28, 1), headers: [3] },
  ], "Q3 Financial Detail");

  const pineTypes = [
    { label: "1 Bedroom 1 Bathroom", code: "PR.A1", units: 160, occupied: 137, sqft: 690, market: 1510, resident: 1435 },
    { label: "2 Bedroom 1 Bathroom", code: "PR.B1", units: 148, occupied: 125, sqft: 905, market: 1780, resident: 1685 },
    { label: "2 Bedroom 2 Bathroom", code: "PR.B2", units: 80, occupied: 69, sqft: 1040, market: 1950, resident: 1840 },
    { label: "3 Bedroom 2 Bathroom", code: "PR.C2", units: 24, occupied: 19, sqft: 1260, market: 2250, resident: 2105 },
  ];
  const pine = await saveWorkbook("pine_ridge_4q26/sources/Property_Ops_December.xlsx", [
    { name: "Market Conditions", rows: costarRows([{ period: "2026 Q4", vacancy: 0.112, rent: 1645, growth: -0.008, inventory: 22400, construction: 720, absorption: 180, sale: 126000, volume: 108000000, cap: 0.061 }, { period: "2026 Q3", vacancy: 0.106, rent: 1658, growth: 0.004, inventory: 22160, construction: 810, absorption: 205, sale: 127500, volume: 111000000, cap: 0.06 }], 1), headers: [1] },
    { name: "Prior Unit Mix", rows: scheduleRows({ name: "Pine Ridge", code: "92002", asOf: "2026-09-30", types: pineTypes.map((item) => ({ ...item, resident: item.resident - 22 })), leading: 1 }), headers: [5] },
    { name: "December Operations", rows: financialRows({ code: "92002", period: "Oct 2026-Dec 2026", actual: PINE_ACTUAL, budget: PINE_BUDGET, ytdFactor: 4, leading: 2 }), headers: [6] },
    { name: "December Occupancy", rows: rentRollRows({ name: "Pine Ridge", code: "92002", asOf: "2026-12-31", units: 412, occupied: 350, future: 12, marketRent: 1735, residentRent: 1630, leading: 2 }), headers: [10] },
    { name: "September Occupancy", rows: rentRollRows({ name: "Pine Ridge", code: "92002", asOf: "2026-09-30", units: 412, occupied: 355, future: 9, marketRent: 1700, residentRent: 1605 }), headers: [8] },
    { name: "Current Unit Mix", rows: scheduleRows({ name: "Pine Ridge", code: "92002", asOf: "2026-12-31", types: pineTypes }), headers: [4] },
    { name: "Trade Outs", rows: ltoRows({ name: "Pine Ridge", start: "2026-10-01", end: "2026-12-31", rows: [{ kind: "renewal", resident: "Resident 44", type: "PR.A1", sqft: 690, unit: "1044", date: "2026-10-20", market: 1510, current: 1440, prior: 1395 }, { kind: "move_in", resident: "Resident 211", type: "PR.B2", sqft: 1040, unit: "2211", date: "2026-11-14", market: 1950, current: 1830, prior: 1780 }, { kind: "move_in", resident: "Resident 85", type: "PR.B1", sqft: 905, unit: "1085", date: "2026-12-08", market: 1780, current: 1675, prior: 1640 }] }), headers: [4, 11] },
    { name: "Competitive Set", rows: compsRows([{ name: "Pine Ridge", address: "4100 Cedar Loop, Raleigh, NC 27606", year: 2004, units: 412, sqft: 862, leased: 0.85 }, { name: "Cedar Grove", address: "4255 Cedar Loop, Raleigh, NC 27606", similarity: 0.88, distance: 0.8, year: 2008, units: 360, sqft: 890, leased: 0.91 }, { name: "Westlake Terrace", address: "120 Westlake Road, Raleigh, NC 27607", similarity: 0.84, distance: 2.2, year: 2001, units: 296, sqft: 845, leased: 0.89 }], 2), headers: [3] },
    { name: "Lease Trend", rows: rentTrendRows("Pine Ridge", "West Raleigh Comp Set", 2026, 1, 1.93, 2.02, 2), headers: [4] },
  ], "December Operations");

  const lakeTypes = [
    { label: "Studio 1 Bathroom", code: "LC.S1", units: 20, occupied: 18, sqft: 515, market: 1550, resident: 1480 },
    { label: "1 Bedroom 1 Bathroom", code: "LC.A1", units: 80, occupied: 75, sqft: 735, market: 1810, resident: 1725 },
    { label: "2 Bedroom 2 Bathroom", code: "LC.B2", units: 80, occupied: 74, sqft: 1035, market: 2240, resident: 2110 },
    { label: "3 Bedroom 2 Bathroom", code: "LC.C2", units: 16, occupied: 14, sqft: 1285, market: 2595, resident: 2450 },
  ];
  const current = await saveWorkbook("lakeside_commons_1q27/sources/Current_Quarter_Pack.xlsx", [
    { name: "Current Occupancy", rows: rentRollRows({ name: "Lakeside Commons", code: "73003", asOf: "2027-03-31", units: 196, occupied: 181, future: 5, marketRent: 2010, residentRent: 1902, leading: 1 }), headers: [9] },
    { name: "Operating Statement", rows: financialRows({ code: "73003", period: "Jan 2027-Mar 2027", actual: LAKE_ACTUAL, budget: LAKE_BUDGET, ytdFactor: 1, leading: 2 }), headers: [6] },
    { name: "Current Unit Mix", rows: scheduleRows({ name: "Lakeside Commons", code: "73003", asOf: "2027-03-31", types: lakeTypes }), headers: [4] },
    { name: "Prior Occupancy", rows: rentRollRows({ name: "Lakeside Commons", code: "73003", asOf: "2026-12-31", units: 196, occupied: 184, future: 7, marketRent: 1975, residentRent: 1870 }), headers: [8] },
    { name: "Prior Unit Mix", rows: scheduleRows({ name: "Lakeside Commons", code: "73003", asOf: "2026-12-31", types: lakeTypes.map((item) => ({ ...item, resident: item.resident - 28 })), leading: 1 }), headers: [5] },
    { name: "Rent Comps", rows: compsRows([{ name: "Lakeside Commons", address: "77 Lakefront Avenue, Orlando, FL 32801", year: 2011, units: 196, sqft: 823, leased: 0.923 }, { name: "Cypress Landing", address: "140 Cypress Street, Orlando, FL 32801", similarity: 0.9, distance: 1.1, year: 2014, units: 224, sqft: 845, leased: 0.948 }, { name: "Parkline East", address: "900 Parkline Drive, Orlando, FL 32803", similarity: 0.82, distance: 2.6, year: 2009, units: 180, sqft: 810, leased: 0.936 }]), headers: [2] },
    { name: "CoStar Table", rows: costarRows([{ period: "2027 Q1", vacancy: 0.067, rent: 2015, growth: 0.031, inventory: 18750, construction: 510, absorption: 330, sale: 182000, volume: 134000000, cap: 0.053 }, { period: "2026 Q4", vacancy: 0.071, rent: 1988, growth: 0.027, inventory: 18540, construction: 560, absorption: 305, sale: 180500, volume: 128000000, cap: 0.054 }], 2), headers: [2] },
    { name: "Rent Trend", rows: rentTrendRows("Lakeside Commons", "Central Orlando Comp Set", 2026, 4, 2.31, 2.45), headers: [2] },
  ], "Operating Statement");

  const archiveActual = { ...LAKE_ACTUAL, revenue: 999999, noi: 389999 };
  const archive = await saveWorkbook("lakeside_commons_1q27/sources/Archive_Export.xlsx", [
    { name: "Re-exported Current Quarter", rows: ptdOnly(financialRows({ code: "73003", period: "Jan 2027-Mar 2027", actual: archiveActual, budget: LAKE_BUDGET, ytdFactor: 1, leading: 1 })), headers: [5] },
    { name: "Historical Quarter", rows: financialRows({ code: "73003", period: "Oct 2026-Dec 2026", actual: { ...LAKE_ACTUAL, revenue: 970000, opex: 585000, noi: 385000, cashFlow: 135000 }, budget: LAKE_BUDGET, ytdFactor: 4 }), headers: [4] },
  ], "Re-exported Current Quarter");

  const regional = await saveWorkbook("lakeside_commons_1q27/sources/Regional_Support.xlsx", [
    { name: "Regional Occupancy", rows: rentRollRows({ name: "Regional Oaks", code: "99117", asOf: "2027-03-31", units: 540, occupied: 529, future: 20, marketRent: 2450, residentRent: 2325 }), headers: [8] },
  ], "Regional Occupancy");

  const checks = [harbor, pine, current, archive, regional];
  for (const check of checks) {
    if (check.formulaErrors.includes("#")) throw new Error(`Formula error found in ${check.outputPath}: ${check.formulaErrors}`);
  }
  console.log(JSON.stringify(checks.map((check) => ({ output: check.outputPath, inspected: check.keyRange.slice(0, 500), formulaScan: check.formulaErrors })), null, 2));
}


await main();
