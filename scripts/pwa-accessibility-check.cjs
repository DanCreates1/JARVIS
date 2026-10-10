"use strict";

// Isolated synthetic desktop evidence. No Core, account, provider or private route is loaded.
// Usage: rtk proxy node scripts/pwa-accessibility-check.cjs
// PWA_TEST_BROWSER can select another Chromium executable. Output stays under ignored runtime/.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const assets = path.join(root, "src/jarvis/pwa");
const outputDir = path.join(root, "runtime/mvp4-fixes");
fs.mkdirSync(outputDir, { recursive: true });
const browserPath = process.env.PWA_TEST_BROWSER || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const profile = fs.mkdtempSync(path.join(outputDir, "edge-profile-"));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json" };
const allowed = new Set(["index.html", "app.js", "app.css", "sw.js", "manifest.webmanifest", "icon.svg"]);
const server = http.createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  const file = url.pathname === "/app/" ? "index.html" : url.pathname.slice(5);
  if (request.method !== "GET" || !url.pathname.startsWith("/app/") || !allowed.has(file)) {
    response.writeHead(404); response.end(); return;
  }
  let content = fs.readFileSync(path.join(assets, file));
  if (file === "app.js") content = Buffer.from(content.toString("utf8") + "\nglobalThis.pwaTest={row,processEvent,logout,setConnected,renderGarmin,state};\n");
  response.writeHead(200, { "Content-Type": types[path.extname(file)], "Cache-Control": "no-store" });
  response.end(content);
});
let browser, ws, call;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  browser = spawn(browserPath, ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
  let debugPort;
  for (let turn = 0; turn < 100; turn++) {
    try { debugPort = Number(fs.readFileSync(path.join(profile, "DevToolsActivePort"), "utf8").split("\n")[0]); break; } catch { await pause(100); }
  }
  assert.ok(debugPort, "Chromium debugging port unavailable");
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
  ws = new WebSocket(targets.find(target => target.type === "page").webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener("open", resolve, { once: true }));
  let id = 0; const pending = new Map();
  ws.addEventListener("message", event => {
    const message = JSON.parse(event.data), item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id); clearTimeout(item.timer);
    if (message.error) item.reject(new Error(JSON.stringify(message.error))); else item.resolve(message.result);
  });
  call = (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id, timer = setTimeout(() => { pending.delete(next); reject(new Error(`CDP timeout: ${method}`)); }, 10000);
    pending.set(next, { resolve, reject, timer }); ws.send(JSON.stringify({ id: next, method, params }));
  });
  const evaluate = async expression => {
    const result = await call("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const key = async (name, code, shift = false) => {
    for (const type of ["keyDown", "keyUp"]) await call("Input.dispatchKeyEvent", { type, key: name, code: name, windowsVirtualKeyCode: code, modifiers: shift ? 8 : 0 });
  };
  await call("Page.enable"); await call("Page.navigate", { url: `http://127.0.0.1:${port}/app/` });
  let loaded = false;
  for (let turn = 0; turn < 100; turn++) {
    loaded = await evaluate("Boolean(globalThis.pwaTest)&&document.readyState==='complete'");
    if (loaded) break; await pause(50);
  }
  assert.ok(loaded, "PWA script failed to initialize");
  const output = { version: await call("Browser.getVersion"), limitations: "Desktop geometry, browser default-font resizing and keyboard/AX evidence; no physical Safari, spoken screen reader or actual browser 400% zoom acceptance.", cases: [] };
  await evaluate(`pwaTest.renderGarmin({date:'Synthetic date',refreshed_at:'invalid',steps:null,activities:[{name:'SyntheticLongActivityName'.repeat(8),type:'walking'}]});document.querySelector('#device-status').innerHTML='<div><dt>Session</dt><dd>session:'+ '0123456789'.repeat(20)+'</dd></div>';document.querySelector('#tasks').textContent='SyntheticTask'.repeat(20);document.querySelector('#connection').textContent='Reconnecting — checking authenticated live connection';`);
  for (const width of [320, 375, 390, 430, 844, 1280]) {
    await call("Emulation.setDeviceMetricsOverride", { width, height: 844, deviceScaleFactor: 1, mobile: false });
    for (const font of [16, 32]) {
      // Changes browser's default font, exercising the user-relative root size.
      await call("Page.setFontSizes", { fontSizes: { standard: font, fixed: font } });
      for (const spacing of [false, true]) {
        await evaluate(`(()=>{document.querySelector('#spacing')?.remove();${spacing ? "const style=document.createElement('style');style.id='spacing';style.textContent='*:not(.sr-only){line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important}p{margin-bottom:2em!important}';document.head.append(style);" : ""}})()`);
        const geometry = await evaluate(`({width:innerWidth,font:parseFloat(getComputedStyle(document.documentElement).fontSize),scrollWidth:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('button:not([hidden])')].map(e=>({id:e.id,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height,font:parseFloat(getComputedStyle(e).fontSize)})),overflow:[...document.querySelectorAll('header,.panel,.metrics dd,.device dd')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({id:e.id,tag:e.tagName,scroll:e.scrollWidth,client:e.clientWidth}))})`);
        geometry.spacing = spacing; output.cases.push(geometry);
        assert.equal(geometry.font, font); assert.ok(geometry.scrollWidth <= width + 1, JSON.stringify(geometry));
        assert.equal(geometry.overflow.length, 0, JSON.stringify(geometry));
        for (const button of geometry.buttons) { assert.equal(button.font, font); assert.ok(button.width >= 43.99 && button.height >= 43.99, JSON.stringify(button)); }
      }
    }
  }
  await evaluate("document.querySelector('#spacing')?.remove()"); await call("Page.setFontSizes", { fontSizes: { standard: 16, fixed: 16 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 320, height: 211, deviceScaleFactor: 1, mobile: false });
  output.reflowReference = await evaluate("({referenceWidth:1280,layoutWidth:innerWidth,scrollWidth:document.documentElement.scrollWidth,note:'320 CSS px equivalent to 1280px at 400%; viewport simulation, not actual browser zoom'})");
  assert.ok(output.reflowReference.scrollWidth <= 321);
  await call("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  await evaluate("document.querySelectorAll('button,textarea').forEach(e=>e.disabled=false);for(let i=0;i<80;i++)pwaTest.row('jarvis','Synthetic history '+i);document.querySelector('#ticket').focus()");
  output.tabOrder = ["ticket"];
  for (let turn = 0; turn < 10; turn++) { await key("Tab", 9); output.tabOrder.push(await evaluate("document.activeElement.id||document.activeElement.tagName")); }
  assert.ok(output.tabOrder.includes("log"));
  await evaluate("document.querySelector('#log').focus();document.querySelector('#log').scrollTop=0");
  await key("PageDown", 34); await pause(350);
  output.keyboardScroll = await evaluate("document.querySelector('#log').scrollTop"); assert.ok(output.keyboardScroll > 0);
  await key("Tab", 9, true); output.shiftTab = await evaluate("document.activeElement.id"); assert.equal(output.shiftTab, "notify");
  output.history = await evaluate(`(()=>{const log=document.querySelector('#log');log.scrollTop=120;const before=log.scrollTop;pwaTest.row('jarvis','Incoming synthetic delta','synthetic-stream');const after=log.scrollTop;const visible=!document.querySelector('#jump-latest').hidden;document.querySelector('#jump-latest').click();return {before,after,visible,atEnd:Math.abs(log.scrollHeight-log.clientHeight-log.scrollTop)<=1,focus:document.activeElement.id};})()`);
  assert.equal(output.history.before, output.history.after); assert.ok(output.history.visible && output.history.atEnd); assert.equal(output.history.focus, "log");
  output.selection = await evaluate(`(()=>{const log=document.querySelector('#log'),range=document.createRange();range.selectNodeContents(log.firstChild);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);const before=log.scrollTop;pwaTest.row('jarvis','Selected history delta','synthetic-stream');const result={before,after:log.scrollTop,selection:selection.toString(),jump:!document.querySelector('#jump-latest').hidden};selection.removeAllRanges();return result;})()`);
  assert.equal(output.selection.before, output.selection.after); assert.ok(output.selection.selection && output.selection.jump);
  const ax = await call("Accessibility.getFullAXTree");
  output.accessibility = ax.nodes.filter(n => ["button", "textbox", "log", "status"].includes(n.role?.value)).map(n => ({ role: n.role.value, name: n.name?.value }));
  assert.ok(output.accessibility.some(n => n.role === "log" && n.name === "Conversation"));
  assert.ok(output.accessibility.some(n => n.role === "button" && n.name === "Refresh tasks"));
  output.colors = await evaluate(`(()=>{const s=e=>getComputedStyle(document.querySelector(e));return {danger:[s('#logout').color,s('#logout').backgroundColor],input:[s('#ticket').borderTopColor,s('#ticket').backgroundColor],panel:s('#setup').backgroundColor,focus:s('#ticket').outlineColor};})()`);
  const luminance = color => { const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { const s = v / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; }); return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]; };
  const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  output.contrast = { danger: contrast(...output.colors.danger), inputFill: contrast(...output.colors.input), inputPanel: contrast(output.colors.input[0], output.colors.panel), focusFill: contrast("rgb(85,207,255)", output.colors.input[1]), focusButton: contrast("rgb(85,207,255)", "rgb(37,67,94)") };
  assert.ok(output.contrast.danger >= 4.5); assert.ok(output.contrast.inputFill >= 3 && output.contrast.inputPanel >= 3); assert.ok(output.contrast.focusFill >= 3 && output.contrast.focusButton >= 3);
  await call("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  output.reducedMotion = await evaluate("getComputedStyle(document.querySelector('.panel')).animationName"); assert.equal(output.reducedMotion, "none");
  await evaluate("pwaTest.state.hasIdentity=true;pwaTest.setConnected(false);document.querySelector('#logout').focus();pwaTest.logout()");
  output.logoutFocus = await evaluate("document.activeElement.id"); assert.equal(output.logoutFocus, "ticket");
  await call("Page.setFontSizes", { fontSizes: { standard: 32, fixed: 32 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 320, height: 844, deviceScaleFactor: 1, mobile: false });
  await evaluate("scrollTo(0,0)");
  const screenshot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(path.join(outputDir, "enlarged-320.png"), Buffer.from(screenshot.data, "base64"));
  fs.writeFileSync(path.join(outputDir, "desktop.json"), JSON.stringify(output, null, 2));
  console.log(JSON.stringify({ pass: true, cases: output.cases.length, contrast: output.contrast, keyboard: true, history: true, namedLog: true, output: "runtime/mvp4-fixes/desktop.json" }));
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (call) { try { await call("Browser.close"); } catch {} }
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close();
});
