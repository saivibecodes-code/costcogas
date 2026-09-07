/**
 * ==============================================================================
 * COSTCO DATA COLLECTOR FOR GOOGLE SHEETS (Google Apps Script)
 * ==============================================================================
 * Tracks:
 *   1. Costco Gold Bullion (1 oz PAMP Suisse #1943308, RCM, etc.)
 *      - Live Costco price, stock status, gold spot price, 4% cash-back arbitrage,
 *        and live dealer buyback bid.
 *   2. Costco Gas Stations
 *      - Live pump rates (Regular and Premium) across DFW and custom warehouses.
 *   3. Automated Background Trigger
 *      - Runs hands-free every 15 minutes, 30 minutes, or hourly via Google Triggers.
 * ==============================================================================
 */

// ------------------------------------------------------------------------------
// CONFIGURATION
// ------------------------------------------------------------------------------

// Gold SKUs to track on costcogoldinventory.com
const GOLD_SKUS = [
  { sku: '1943308', name: '1 oz Gold Bar PAMP Suisse Lady Fortuna Veriscan' },
  { sku: '1982254', name: '1 oz Royal Canadian Mint Gold Bar (New in Assay)' },
  { sku: '2026791', name: '2026 1 oz American Buffalo Gold Coin' },
  { sku: '2026479', name: '2026 1 oz American Eagle Gold Coin' }
];

// Warehouse locations for gas tracking (ID: Store Name)
const GAS_LOCATIONS = {
  '664':  'East Plano Costco',
  '683':  'Lewisville Costco',
  '684':  'West Plano Costco',
  '1097': 'Frisco Costco',
  '1284': 'McKinney Costco',
  '1694': 'Prosper Costco',
  '1739': 'Allen Costco',
  '1645': 'Celina Costco'
};

// Email notification settings (optional)
const ALERT_SETTINGS = {
  enableEmailAlerts: false, // Set to true to receive email when in stock
  alertEmail: Session.getActiveUser().getEmail(), // Defaults to your Google email
  onlyAlertWhenInStock: true
};


// ------------------------------------------------------------------------------
// 1. MENU CREATION (Adds dropdown menu to Google Sheets UI)
// ------------------------------------------------------------------------------

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('⛽ Costco Data Hub')
    .addItem('🥇 Collect Gold Prices Now', 'collectCostcoGoldData')
    .addItem('⛽ Collect Gas Prices Now', 'collectCostcoGasData')
    .addSeparator()
    .addItem('🔄 Collect ALL Data Now', 'collectAllCostcoData')
    .addSeparator()
    .addItem('⏰ Enable 15-Minute Auto-Collection', 'setupTrigger15Min')
    .addItem('⏰ Enable Hourly Auto-Collection', 'setupTriggerHourly')
    .addItem('⛔ Stop All Auto-Collection Triggers', 'clearAllTriggers')
    .addToUi();
}


// ------------------------------------------------------------------------------
// 2. MASTER RUNNER
// ------------------------------------------------------------------------------

function collectAllCostcoData() {
  Logger.log("Starting full Costco data collection...");
  collectCostcoGoldData();
  collectCostcoGasData();
  Logger.log("Full collection complete!");
}


// ------------------------------------------------------------------------------
// 3. GOLD DATA COLLECTOR & ARBITRAGE TRACKER
// ------------------------------------------------------------------------------

function collectCostcoGoldData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("Costco Gold");
  
  if (!sheet) {
    sheet = ss.insertSheet("Costco Gold");
  }

  // Add and format headers if empty
  if (sheet.getLastRow() === 0) {
    const headers = [
      "Timestamp",
      "Product Name",
      "Costco Item #",
      "Stock Status",
      "Costco List Price ($)",
      "Gold Spot Price ($)",
      "Costco Over Spot (%)",
      "Executive Net (2% Off)",
      "Combined Net (4% Off)",
      "Best Buyback Bid ($)",
      "Net Profit (4% vs Bid)",
      "ROI (%)",
      "Product URL"
    ];
    sheet.appendRow(headers);
    
    // Style Header: Costco Blue #005DAA with white bold text
    const headerRange = sheet.getRange(1, 1, 1, headers.length);
    headerRange.setBackground("#005DAA")
               .setFontColor("#FFFFFF")
               .setFontWeight("bold")
               .setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
  }

  // 1. Fetch live gold spot price from free API
  let spotPrice = getLiveGoldSpotPrice();
  const fetchOptions = {
    method: 'get',
    muteHttpExceptions: true
  };

  const rowsToAppend = [];
  const now = new Date();

  // 2. Loop through monitored gold SKUs
  for (let i = 0; i < GOLD_SKUS.length; i++) {
    const item = GOLD_SKUS[i];
    const url = `https://costcogoldinventory.com/online-inventory/${item.sku}`;

    try {
      const response = UrlFetchApp.fetch(url, fetchOptions);
      if (response.getResponseCode() === 200) {
        const html = response.getContentText();
        
        // Extract Structured Data (JSON-LD)
        let price = null;
        let inStock = false;

        const jsonLdMatch = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/i);
        if (jsonLdMatch && jsonLdMatch[1]) {
          try {
            const data = JSON.parse(jsonLdMatch[1]);
            const graph = data["@graph"] || [data];
            for (let j = 0; j < graph.length; j++) {
              if (graph[j]["@type"] === "Product" && graph[j]["offers"]) {
                price = parseFloat(graph[j]["offers"]["price"]);
                inStock = graph[j]["offers"]["availability"] && graph[j]["offers"]["availability"].indexOf("InStock") !== -1;
                break;
              }
            }
          } catch (jsonErr) {
            Logger.log(`JSON-LD parse error on SKU ${item.sku}: ` + jsonErr.toString());
          }
        }

        // Fallback HTML Regex for Price if JSON-LD missing
        if (!price) {
          const priceMatch = html.match(/class=["']price-big["']>\$([0-9,]+\.[0-9]{2})/i);
          if (priceMatch) {
            price = parseFloat(priceMatch[1].replace(/,/g, ''));
          }
        }

        // Fallback for Stock
        if (!inStock) {
          inStock = html.indexOf('class="badge in">In stock') !== -1;
        }

        // Extract Best Buyback Bid from page (e.g. "best live buyback bid we track for this item is <b>$4,374.55</b>")
        let buybackBid = null;
        const bidMatch = html.match(/best live buyback bid we track for this item is[\s\S]*?\$([0-9,]+\.[0-9]{2})/i);
        if (bidMatch) {
          buybackBid = parseFloat(bidMatch[1].replace(/,/g, ''));
        }

        // Extract Spot price from page if external spot API failed
        if (!spotPrice) {
          const pageSpotMatch = html.match(/Spot \$([0-9,]+\.[0-9]{2})\/oz/i);
          if (pageSpotMatch) {
            spotPrice = parseFloat(pageSpotMatch[1].replace(/,/g, ''));
          }
        }

        if (price) {
          // Calculations
          const execNet = price * 0.98;         // 2% Executive Membership rebate
          const combinedNet = price * 0.96;     // 4% Combined (2% Exec + 2% Card)
          const overSpotPct = spotPrice ? ((price - spotPrice) / spotPrice) : 0;
          const netProfit = buybackBid ? (buybackBid - combinedNet) : 0;
          const roiPct = buybackBid ? (netProfit / combinedNet) : 0;
          const stockLabel = inStock ? "IN STOCK 🟢" : "OUT OF STOCK 🔴";

          rowsToAppend.push([
            now,
            item.name,
            item.sku,
            stockLabel,
            price,
            spotPrice || "N/A",
            overSpotPct,
            execNet,
            combinedNet,
            buybackBid || "N/A",
            buybackBid ? netProfit : "N/A",
            buybackBid ? roiPct : "N/A",
            `https://www.costco.com/.product.${item.sku}.html`
          ]);

          Logger.log(`[GOLD] Logged ${item.name}: $${price} (${stockLabel})`);

          // Optional Email Alert if In Stock
          if (ALERT_SETTINGS.enableEmailAlerts && inStock && ALERT_SETTINGS.alertEmail) {
            sendStockAlertEmail(item.name, item.sku, price, buybackBid, netProfit);
          }
        } else {
          Logger.log(`[GOLD] Price not found for SKU ${item.sku}`);
        }
      }
    } catch (err) {
      Logger.log(`[GOLD ERROR] Failed to fetch SKU ${item.sku}: ` + err.toString());
    }

    // Gentle rate limit pause
    Utilities.sleep(1200);
  }

  // Batch append rows and format columns
  if (rowsToAppend.length > 0) {
    const startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, rowsToAppend.length, rowsToAppend[0].length).setValues(rowsToAppend);

    // Number formats:
    // Col 1: Date, Col 5, 6, 8, 9, 10, 11: Currency ($#,##0.00), Col 7, 12: Percent (0.00%)
    sheet.getRange(startRow, 1, rowsToAppend.length, 1).setNumberFormat("yyyy-mm-dd hh:mm:ss");
    sheet.getRange(startRow, 5, rowsToAppend.length, 2).setNumberFormat("$#,##0.00");
    sheet.getRange(startRow, 7, rowsToAppend.length, 1).setNumberFormat("0.00%");
    sheet.getRange(startRow, 8, rowsToAppend.length, 4).setNumberFormat("$#,##0.00");
    sheet.getRange(startRow, 12, rowsToAppend.length, 1).setNumberFormat("0.00%");
  }
}


// ------------------------------------------------------------------------------
// 4. GAS DATA COLLECTOR
// ------------------------------------------------------------------------------

function collectCostcoGasData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("Costco Gas") || ss.insertSheet("Costco Gas");

  if (sheet.getLastRow() === 0) {
    const headers = ["Timestamp", "Store Name", "Warehouse ID", "Regular Pump ($)", "Premium Pump ($)", "Premium Spread ($)"];
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length)
         .setBackground("#005DAA")
         .setFontColor("#FFFFFF")
         .setFontWeight("bold")
         .setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
  }

  const options = {
    method: 'get',
    headers: {
      'accept': '*/*',
      'accept-language': 'en-US,en;q=0.9',
      'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
    },
    muteHttpExceptions: true
  };

  const rowsToAppend = [];
  const now = new Date();

  for (let warehouseId in GAS_LOCATIONS) {
    const storeName = GAS_LOCATIONS[warehouseId];
    const url = `https://www.costco.com/AjaxGetGasPricesService?warehouseid=${warehouseId}`;

    try {
      const response = UrlFetchApp.fetch(url, options);
      if (response.getResponseCode() === 200) {
        const json = JSON.parse(response.getContentText().trim());
        const stationData = json[warehouseId];

        if (stationData && stationData.regular) {
          const regularPrice = parseFloat(stationData.regular);
          const premiumPrice = stationData.premium ? parseFloat(stationData.premium) : null;
          const spread = premiumPrice ? (premiumPrice - regularPrice) : null;

          rowsToAppend.push([
            now,
            storeName,
            warehouseId,
            regularPrice,
            premiumPrice || "N/A",
            spread !== null ? spread : "N/A"
          ]);

          Logger.log(`[GAS] Logged ${storeName}: Reg $${regularPrice}, Prem $${premiumPrice}`);
        }
      }
    } catch (e) {
      Logger.log(`[GAS ERROR] ${storeName}: ` + e.toString());
    }

    Utilities.sleep(800);
  }

  if (rowsToAppend.length > 0) {
    const startRow = sheet.getLastRow() + 1;
    sheet.getRange(startRow, 1, rowsToAppend.length, rowsToAppend[0].length).setValues(rowsToAppend);
    sheet.getRange(startRow, 1, rowsToAppend.length, 1).setNumberFormat("yyyy-mm-dd hh:mm:ss");
    sheet.getRange(startRow, 4, rowsToAppend.length, 3).setNumberFormat("$#,##0.000");
  }
}


// ------------------------------------------------------------------------------
// 5. HELPER: LIVE GOLD SPOT PRICE
// ------------------------------------------------------------------------------

function getLiveGoldSpotPrice() {
  try {
    const response = UrlFetchApp.fetch("https://api.gold-api.com/price/XAU", { muteHttpExceptions: true });
    if (response.getResponseCode() === 200) {
      const data = JSON.parse(response.getContentText());
      return parseFloat(data.price);
    }
  } catch (e) {
    Logger.log("Failed to fetch gold spot price: " + e.toString());
  }
  return null;
}


// ------------------------------------------------------------------------------
// 6. HELPER: EMAIL ALERT
// ------------------------------------------------------------------------------

function sendStockAlertEmail(productName, sku, price, buybackBid, netProfit) {
  const subject = `🚨 Costco Gold Restock Alert: ${productName} is IN STOCK!`;
  const buyUrl = `https://www.costco.com/.product.${sku}.html`;
  
  let body = `Costco Gold Bar Alert!\n\n`;
  body += `Product: ${productName}\n`;
  body += `Costco Item #: ${sku}\n`;
  body += `Costco Price: $${price.toFixed(2)}\n`;
  if (buybackBid) {
    body += `Dealer Buyback Bid: $${buybackBid.toFixed(2)}\n`;
    body += `Estimated Net Profit (with 4% cashback): $${netProfit.toFixed(2)}\n`;
  }
  body += `\nBuy Now on Costco: ${buyUrl}\n`;

  MailApp.sendEmail(ALERT_SETTINGS.alertEmail, subject, body);
  Logger.log(`[EMAIL] Alert sent to ${ALERT_SETTINGS.alertEmail}`);
}


// ------------------------------------------------------------------------------
// 7. TIME-DRIVEN AUTOMATION TRIGGERS
// ------------------------------------------------------------------------------

function setupTrigger15Min() {
  clearAllTriggers();
  ScriptApp.newTrigger('collectAllCostcoData')
    .timeBased()
    .everyMinutes(15)
    .create();
  SpreadsheetApp.getUi().alert("✅ Automation Enabled!\n\nCostco data will be collected every 15 minutes automatically.");
}

function setupTriggerHourly() {
  clearAllTriggers();
  ScriptApp.newTrigger('collectAllCostcoData')
    .timeBased()
    .everyHours(1)
    .create();
  SpreadsheetApp.getUi().alert("✅ Automation Enabled!\n\nCostco data will be collected every hour automatically.");
}

function clearAllTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  Logger.log("All triggers cleared.");
}
