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
const allowed = new Set(["index.html", "app.js", "app.css", "sw.js", "pcm-worklet.js", "manifest.webmanifest", "icon.svg"]);
const apiRequests = [];
const server = http.createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname.startsWith("/api/")) apiRequests.push({ method: request.method, path: url.pathname });
  const file = url.pathname === "/app/" ? "index.html" : url.pathname.slice(5);
  if (request.method !== "GET" || !url.pathname.startsWith("/app/") || !allowed.has(file)) {
    response.writeHead(404); response.end(); return;
  }
  let content = fs.readFileSync(path.join(assets, file));
  if (file === "app.js") content = Buffer.from(content.toString("utf8").replace('catch{if(state.voice===op)discardVoice("Microphone unavailable', 'catch(error){globalThis.voiceTestError=String(error);if(state.voice===op)discardVoice("Microphone unavailable') + "\nglobalThis.pwaTest={row,processEvent,logout,setConnected,renderGarmin,state,selectView,navigation,updateControls};\n");
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
    for (const type of ["keyDown", "keyUp"]) await call("Input.dispatchKeyEvent", { type, key: name, code: name===" "?"Space":name, windowsVirtualKeyCode: code, modifiers: shift ? 8 : 0, ...(type==="keyDown"&&["Enter"," "].includes(name)?{text:name==="Enter"?"\r":" "}:{}) });
  };
  await call("Page.enable"); await call("Page.navigate", { url: `http://127.0.0.1:${port}/app/` });
  let loaded = false;
  for (let turn = 0; turn < 100; turn++) {
    loaded = await evaluate("Boolean(globalThis.pwaTest)&&document.readyState==='complete'");
    if (loaded) break; await pause(50);
  }
  assert.ok(loaded, "PWA script failed to initialize");
  const output = { version: await call("Browser.getVersion"), limitations: "Desktop geometry, browser default-font resizing and keyboard/AX evidence; no physical Safari, spoken screen reader or actual browser 400% zoom acceptance.", cases: [] };
  const viewState = () => evaluate(`({view:pwaTest.navigation.view,title:document.title,focus:document.activeElement.id,visible:[...document.querySelectorAll('.view')].filter(e=>e.getClientRects().length).map(e=>e.id),current:[...document.querySelectorAll('nav [aria-current=page]')].map(e=>e.id),connectionVisible:Boolean(document.querySelector('#connection').getClientRects().length)})`);
  const checkView = async name => {
    const value = await viewState(); assert.equal(value.view, name); assert.deepEqual(value.visible, [`view-${name}`]);
    assert.deepEqual(value.current, [`nav-${name}`]); assert.ok(value.connectionVisible); return value;
  };
  const select = async name => { await evaluate(`document.querySelector('#nav-${name}').click()`); return checkView(name); };
  await checkView("chat");
  output.navigation = { initial: await viewState() };
  assert.equal((await select("garmin")).focus, "garmin-title");
  assert.equal((await select("settings")).focus, "settings-title");
  const waitView = async name => {
    for (let turn = 0; turn < 100; turn++) { if ((await viewState()).view === name) return checkView(name); await pause(20); }
    throw new Error(`Browser did not navigate to ${name}`);
  };
  await evaluate("history.back()"); output.navigation.back = await waitView("garmin");
  assert.equal(output.navigation.back.focus, "garmin-title");
  await evaluate("history.forward()"); output.navigation.forward = await waitView("settings");
  assert.equal(output.navigation.forward.focus, "settings-title");
  await evaluate("location.hash='#/unknown'"); await waitView("chat");
  assert.equal(await evaluate("location.hash"), "#/chat");
  await evaluate("document.querySelector('#nav-settings').focus()"); await key("Enter", 13);
  assert.equal((await checkView("settings")).focus, "settings-title");
  await key("Tab", 9); assert.equal(await evaluate("document.activeElement.id"), "ticket");
  assert.equal(apiRequests.length, 0, "View selection must never call Core");
  await evaluate(`pwaTest.renderGarmin({date:'Synthetic date',refreshed_at:'invalid',steps:null,activities:[{name:'SyntheticLongActivityName'.repeat(8),type:'walking'}]});document.querySelector('#device-status').innerHTML='<div><dt>Session</dt><dd>session:'+ '0123456789'.repeat(20)+'</dd></div>';document.querySelector('#tasks').textContent='SyntheticTask'.repeat(20);document.querySelector('#connection').textContent='Reconnecting — checking authenticated live connection';`);
  for (const width of [320, 375, 390, 430, 844, 1280]) {
    await call("Emulation.setDeviceMetricsOverride", { width, height: 844, deviceScaleFactor: 1, mobile: false });
    for (const font of [16, 32]) {
      // Changes browser's default font, exercising the user-relative root size.
      await call("Page.setFontSizes", { fontSizes: { standard: font, fixed: font } });
      for (const spacing of [false, true]) {
        await evaluate(`(()=>{document.querySelector('#spacing')?.remove();${spacing ? "const style=document.createElement('style');style.id='spacing';style.textContent='*:not(.sr-only){line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important}p{margin-bottom:2em!important}';document.head.append(style);" : ""}})()`);
        for (const view of ["chat", "garmin", "settings"]) {
        await select(view);
        const geometry = await evaluate(`({view:pwaTest.navigation.view,width:innerWidth,font:parseFloat(getComputedStyle(document.documentElement).fontSize),scrollWidth:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('button,nav a')].filter(e=>e.getClientRects().length).map(e=>({id:e.id,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height,font:parseFloat(getComputedStyle(e).fontSize)})),overflow:[...document.querySelectorAll('header,nav,.view,.panel,.metrics dd,.device dd')].filter(e=>e.getClientRects().length&&e.scrollWidth>e.clientWidth+1).map(e=>({id:e.id,tag:e.tagName,scroll:e.scrollWidth,client:e.clientWidth}))})`);
        geometry.spacing = spacing; output.cases.push(geometry);
        assert.equal(geometry.font, font); assert.ok(geometry.scrollWidth <= width + 1, JSON.stringify(geometry));
        assert.equal(geometry.overflow.length, 0, JSON.stringify(geometry));
        for (const button of geometry.buttons) { assert.equal(button.font, font); assert.ok(button.width >= 43.99 && button.height >= 43.99, JSON.stringify(button)); }
        }
      }
    }
  }
  await evaluate("document.querySelector('#spacing')?.remove()"); await call("Page.setFontSizes", { fontSizes: { standard: 16, fixed: 16 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 320, height: 211, deviceScaleFactor: 1, mobile: false });
  output.reflowReference = await evaluate("({referenceWidth:1280,layoutWidth:innerWidth,scrollWidth:document.documentElement.scrollWidth,note:'320 CSS px equivalent to 1280px at 400%; viewport simulation, not actual browser zoom'})");
  assert.ok(output.reflowReference.scrollWidth <= 321);
  output.navigation.shortViewport = [];
  for (const font of [16, 32]) {
    await call("Page.setFontSizes", { fontSizes: { standard: font, fixed: font } });
    for (const name of ["chat", "garmin", "settings"]) {
      await select(name);
      const geometry = await evaluate("(()=>{const nav=document.querySelector('nav'),r=document.activeElement.getBoundingClientRect();return {position:getComputedStyle(nav).position,scrollWidth:document.documentElement.scrollWidth,top:r.top,bottom:r.bottom,headingVisible:r.top>=-1&&r.bottom<=innerHeight+1};})()");
      assert.equal(geometry.position, "static"); assert.ok(geometry.headingVisible, JSON.stringify({name,font,...geometry})); assert.ok(geometry.scrollWidth <= 321);
      output.navigation.shortViewport.push({ name, font, ...geometry });
    }
  }
  await call("Page.setFontSizes", { fontSizes: { standard: 16, fixed: 16 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
  await select("chat");
  await evaluate("document.querySelectorAll('button,textarea,select').forEach(e=>e.disabled=false);for(let i=0;i<80;i++)pwaTest.row('jarvis','Synthetic history '+i);document.querySelector('#nav-chat').focus()");
  output.tabOrder = ["nav-chat"];
  for (let turn = 0; turn < 16; turn++) { await key("Tab", 9); output.tabOrder.push(await evaluate("document.activeElement.id||document.activeElement.tagName")); }
  assert.ok(output.tabOrder.includes("log"));
  for(const id of ["conversation-list","new-conversation","refresh-history","cancel-chat"])assert.ok(output.tabOrder.includes(id),`Keyboard cannot reach ${id}`);
  await evaluate("document.querySelector('#log').focus();document.querySelector('#log').scrollTop=0");
  await key("PageDown", 34); await pause(350);
  output.keyboardScroll = await evaluate("document.querySelector('#log').scrollTop"); assert.ok(output.keyboardScroll > 0);
  await key("Tab", 9, true); output.shiftTab = await evaluate("document.activeElement.id"); assert.equal(output.shiftTab, "refresh-history");
  output.history = await evaluate(`(()=>{const log=document.querySelector('#log');log.scrollTop=120;const before=log.scrollTop;pwaTest.row('jarvis','Incoming synthetic delta','synthetic-stream');const after=log.scrollTop;const visible=!document.querySelector('#jump-latest').hidden;document.querySelector('#jump-latest').click();return {before,after,visible,atEnd:Math.abs(log.scrollHeight-log.clientHeight-log.scrollTop)<=1,focus:document.activeElement.id};})()`);
  assert.equal(output.history.before, output.history.after); assert.ok(output.history.visible && output.history.atEnd); assert.equal(output.history.focus, "log");
  output.selection = await evaluate(`(()=>{const log=document.querySelector('#log'),range=document.createRange();range.selectNodeContents(log.firstChild);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);const before=log.scrollTop;pwaTest.row('jarvis','Selected history delta','synthetic-stream');const result={before,after:log.scrollTop,selection:selection.toString(),jump:!document.querySelector('#jump-latest').hidden};selection.removeAllRanges();return result;})()`);
  assert.equal(output.selection.before, output.selection.after); assert.ok(output.selection.selection && output.selection.jump);
  output.streamSelection = await evaluate(`(()=>{const row=pwaTest.row('jarvis','JARVIS: Selected streamed text','selected-stream'),range=document.createRange();range.setStart(row.firstChild,8);range.setEnd(row.firstChild,16);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);const before=selection.toString();pwaTest.row('jarvis','JARVIS: Selected streamed text plus delta','selected-stream');const after=selection.toString();selection.removeAllRanges();return {before,after};})()`);
  assert.equal(output.streamSelection.before, "Selected"); assert.equal(output.streamSelection.after, output.streamSelection.before);
  const readingPosition = await evaluate("document.querySelector('#log').scrollTop=120");
  await select("garmin"); assert.equal(await evaluate("document.querySelector('#log').clientHeight"), 0);
  await evaluate("pwaTest.row('jarvis','Hidden synthetic reply','off-screen-request')");
  await select("chat"); output.navigation.readingPosition = await evaluate("document.querySelector('#log').scrollTop");
  assert.equal(output.navigation.readingPosition, readingPosition);
  const ax = await call("Accessibility.getFullAXTree");
  output.accessibility = ax.nodes.filter(n => ["button", "textbox", "log", "status"].includes(n.role?.value)).map(n => ({ role: n.role.value, name: n.name?.value }));
  assert.ok(output.accessibility.some(n => n.role === "log" && n.name === "Conversation"));
  assert.ok(output.accessibility.some(n => n.role === "button" && n.name === "Refresh tasks"));
  assert.ok(output.accessibility.some(n => n.role === "button" && n.name === "Cancel reply"));
  assert.ok(!output.accessibility.some(n => n.role === "button" && ["Refresh Garmin", "Connect existing device"].includes(n.name)));
  const navAx = ax.nodes.filter(n => n.role?.value === "link").map(n => n.name?.value);
  assert.deepEqual(navAx, ["Chat", "Garmin", "Settings"]);
  output.navigation.accessibleLinks = navAx;
  await select("settings");
  const settingsAx = await call("Accessibility.getFullAXTree");
  assert.ok(!settingsAx.nodes.some(n => n.role?.value === "log"));
  assert.ok(settingsAx.nodes.some(n => n.role?.value === "button" && n.name?.value === "Connect existing device"));
  output.colors = await evaluate(`(()=>{const s=e=>getComputedStyle(document.querySelector(e));return {danger:[s('#logout').color,s('#logout').backgroundColor],input:[s('#ticket').borderTopColor,s('#ticket').backgroundColor],panel:s('#setup').backgroundColor,focus:s('#ticket').outlineColor};})()`);
  const luminance = color => { const rgb = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(v => { const s = v / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; }); return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]; };
  const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  output.contrast = { danger: contrast(...output.colors.danger), inputFill: contrast(...output.colors.input), inputPanel: contrast(output.colors.input[0], output.colors.panel), focusFill: contrast("rgb(85,207,255)", output.colors.input[1]), focusButton: contrast("rgb(85,207,255)", "rgb(37,67,94)") };
  assert.ok(output.contrast.danger >= 4.5); assert.ok(output.contrast.inputFill >= 3 && output.contrast.inputPanel >= 3); assert.ok(output.contrast.focusFill >= 3 && output.contrast.focusButton >= 3);
  await call("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  output.reducedMotion = await evaluate("getComputedStyle(document.querySelector('.panel')).animationName"); assert.equal(output.reducedMotion, "none");
  await select("chat");
  // Actual browser AudioWorklet, synthetic oscillator MediaStream, fake transcription response.
  // No real microphone permission, Core request or private speech.
  await evaluate(`(()=>{
    const original=window.fetch;window.voiceEvidence={permissionCalls:0,uploads:0,bytes:0};
    window.fetch=async(url,options)=>{if(String(url).endsWith('/client/voice/transcriptions')){voiceEvidence.uploads++;voiceEvidence.bytes=options.body.byteLength;voiceEvidence.stopped=voiceEvidence.stream.getTracks().every(t=>t.readyState==='ended');return new Response(JSON.stringify({text:'Synthetic editable browser draft',duration_ms:Math.round(options.body.byteLength/32)}),{headers:{'Content-Type':'application/json'}});}return original(url,options);};
    navigator.mediaDevices.getUserMedia=async()=>{voiceEvidence.permissionCalls++;const context=new AudioContext({sampleRate:48000}),oscillator=context.createOscillator(),destination=context.createMediaStreamDestination();oscillator.frequency.value=440;oscillator.connect(destination);oscillator.start();await context.resume();voiceEvidence.generator=context;voiceEvidence.stream=destination.stream;return destination.stream;};
    pwaTest.state.csrf='synthetic';pwaTest.state.historyReady=true;pwaTest.state.voiceReady=true;pwaTest.state.chatActive.clear();pwaTest.state.pendingRequest=null;pwaTest.state.sending=false;pwaTest.state.historyBusy=false;pwaTest.state.chatAction=null;document.querySelector('#message').value='';pwaTest.setConnected(true);document.querySelector('#record-message').focus();
  })()`);
  assert.equal(await evaluate("voiceEvidence.permissionCalls"),0);
  assert.equal(await evaluate("document.querySelector('#record-message').disabled"),false,JSON.stringify(await evaluate("({online:pwaTest.state.online,ready:pwaTest.state.voiceReady,history:pwaTest.state.historyReady,hidden:document.hidden,focus:document.activeElement.id,nav:pwaTest.navigation.view})")));
  await key("Enter",13);
  for(let turn=0;turn<100;turn++){if(await evaluate("pwaTest.state.voice?.phase==='recording'"))break;await pause(30);}
  assert.equal(await evaluate("pwaTest.state.voice?.phase"),"recording",JSON.stringify(await evaluate("({error:globalThis.voiceTestError,status:document.querySelector('#voice-status').textContent,evidence:{...voiceEvidence,generator:undefined,stream:undefined}})")));
  assert.equal(await evaluate("document.activeElement.id"),"stop-recording");
  const voiceAx=await call("Accessibility.getFullAXTree");
  for(const name of ["Stop recording","Discard recording"])assert.ok(voiceAx.nodes.some(n=>n.role?.value==='button'&&n.name?.value===name));
  assert.ok(!voiceAx.nodes.some(n=>n.role?.value==='button'&&n.name?.value==='Record message'));
  output.voice={geometry:[]};
  for(const width of [320,375,390,430,844,1280])for(const font of [16,32]){
    await call("Emulation.setDeviceMetricsOverride",{width,height:844,deviceScaleFactor:1,mobile:false});await call("Page.setFontSizes",{fontSizes:{standard:font,fixed:font}});
    const geometry=await evaluate(`({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,controls:['stop-recording','discard-recording'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();return {width:r.width,height:r.height};})})`);
    assert.ok(geometry.scrollWidth<=width+1);for(const control of geometry.controls)assert.ok(control.width>=44&&control.height>=44);output.voice.geometry.push({font,...geometry});
  }
  for(let turn=0;turn<200;turn++){if(await evaluate("(pwaTest.state.voice?.bytes||0)>=4096"))break;await pause(30);}
  assert.ok(await evaluate("(pwaTest.state.voice?.bytes||0)>=4096"),"Actual worklet must deliver PCM before Stop");
  await evaluate("document.querySelector('#stop-recording').focus()");await key(" ",32);
  for(let turn=0;turn<100;turn++){if(await evaluate("!pwaTest.state.voice"))break;await pause(30);}
  Object.assign(output.voice,await evaluate("({...voiceEvidence,generator:undefined,stream:undefined,draft:document.querySelector('#message').value,readOnly:document.querySelector('#message').readOnly,focus:document.activeElement.id,status:document.querySelector('#voice-status').textContent})"));
  assert.equal(output.voice.uploads,1,JSON.stringify(output.voice));assert.ok(output.voice.bytes>=3840&&output.voice.bytes<=960000);assert.ok(output.voice.stopped);assert.equal(output.voice.draft,'Synthetic editable browser draft');assert.equal(output.voice.readOnly,false);assert.equal(output.voice.focus,'message');
  await evaluate("voiceEvidence.generator.close();document.querySelector('#message').value='';pwaTest.updateControls();document.querySelector('#record-message').focus()");await key(" ",32);await pause(150);await key("Escape",27);
  assert.equal(await evaluate("pwaTest.state.voice"),null);assert.equal(await evaluate("voiceEvidence.uploads"),1);await evaluate("voiceEvidence.generator.close()");
  await select("garmin");
  await evaluate("pwaTest.state.csrf=null;pwaTest.state.hasIdentity=true;pwaTest.setConnected(false);pwaTest.logout()");
  output.logoutFocus = await evaluate("document.activeElement.id"); assert.equal(output.logoutFocus, "ticket");
  await call("Page.setFontSizes", { fontSizes: { standard: 32, fixed: 32 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 320, height: 844, deviceScaleFactor: 1, mobile: false });
  await evaluate("scrollTo(0,0)");
  const screenshot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(path.join(outputDir, "enlarged-320.png"), Buffer.from(screenshot.data, "base64"));
  output.navigation.apiRequests = apiRequests; assert.equal(apiRequests.length, 0);
  fs.writeFileSync(path.join(outputDir, "desktop.json"), JSON.stringify(output, null, 2));
  console.log(JSON.stringify({ pass: true, cases: output.cases.length, contrast: output.contrast, keyboard: true, history: true, namedLog: true, output: "runtime/mvp4-fixes/desktop.json" }));
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (call) { try { await call("Browser.close"); } catch {} }
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close();
});
