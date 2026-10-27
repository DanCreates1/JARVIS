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
const textProfile = process.env.PWA_TEST_PROFILE;
const textPrototype = ["prototype-text", "daily-text"].includes(textProfile);
const server = http.createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname.startsWith("/api/")) apiRequests.push({ method: request.method, path: url.pathname });
  const uploadId=url.pathname.match(/^\/api\/v1\/client\/attachments\/([0-9a-f]{32})$/)?.[1];
  if(uploadId&&request.headers['x-jarvis-csrf']==='synthetic'){
    let size=0;request.on('data',chunk=>{size+=chunk.length;});request.on('end',()=>{
      response.writeHead(request.method==='POST'?201:200,{'Content-Type':'application/json','Cache-Control':'no-store'});
      response.end(JSON.stringify(request.method==='POST'?{id:uploadId,status:'staged',bytes:size}:{discarded:true}));
    });return;
  }
  const file = url.pathname === "/app/" ? "index.html" : url.pathname.slice(5);
  if (request.method !== "GET" || !url.pathname.startsWith("/app/") || !allowed.has(file)) {
    response.writeHead(404); response.end(); return;
  }
  let content = fs.readFileSync(path.join(assets, file));
  if (file === "index.html" && textPrototype) content = Buffer.from(content.toString("utf8").replace('data-profile="standard"', `data-profile="${textProfile}"`));
  if (file === "app.js") content = Buffer.from(content.toString("utf8").replace('catch{if(state.voice===op)discardVoice("Microphone unavailable', 'catch(error){globalThis.voiceTestError=String(error);if(state.voice===op)discardVoice("Microphone unavailable') + "\nglobalThis.pwaTest={row,processEvent,logout,setConnected,renderGarmin,state,selectView,navigation,updateControls,selectAttachments,clearAttachments,searchHistory,clearSearch,loadTask,loadLibrary,chooseConversation,renderReply,formatReply,loadAttachmentMetadata,renderAttachmentMetadata,refreshTasks,loadTaskTimeline,renderTaskTimeline};\n");
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
  if (textPrototype) {
    const visible = selector => evaluate(`Boolean(document.querySelector(${JSON.stringify(selector)}).getClientRects().length)`);
    assert.equal(await evaluate("pwaTest.navigation.view"), "chat");
    for (const selector of ["#nav-chat", "#nav-settings", "#log"]) assert.ok(await visible(selector));
    for (const selector of ["#nav-garmin", "#task-panel", "#attachment-file", "#record-message", "#notify"]) assert.equal(await visible(selector), false);
    await evaluate("pwaTest.selectView('garmin')");
    assert.equal(await evaluate("pwaTest.navigation.view"), "chat");
    await evaluate("pwaTest.selectView('settings')");
    assert.ok(await visible("#recovery-title"));
    assert.equal(await evaluate("document.activeElement.id"), "settings-title");
    await key("Tab", 9);
    assert.equal(await evaluate("document.activeElement.id"), "ticket");
    assert.ok((await evaluate("document.querySelector('#view-settings').textContent")).includes("Core unreachable"));
    await evaluate("(async()=>{pwaTest.selectView('chat'); pwaTest.state.csrf='synthetic'; pwaTest.setConnected(true); await pwaTest.refreshTasks(); await pwaTest.loadAttachmentMetadata();})()");
    assert.equal(await evaluate("document.querySelector('#send').disabled"), true, "profile never bypasses authenticated history readiness");
    for (const width of [320, 1280]) {
      await call("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false });
      assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth"));
    }
    const ax = await call("Accessibility.getFullAXTree");
    assert.ok(ax.nodes.some(node => node.role?.value === "log" && node.name?.value === "Conversation"));
    assert.equal(apiRequests.length, 0, "navigation makes no health, task, capture, cloud or research request");
    output.cases = ["Chat/Settings only", "dormant controls hidden", "Garmin deep link normalized", "Settings focus and keyboard", "specific recovery", "Send retains readiness gate", "320/1280 reflow", "named conversation log", "zero optional navigation requests"];
    fs.writeFileSync(path.join(outputDir, `${textProfile}-desktop.json`), JSON.stringify(output, null, 2));
    console.log(JSON.stringify({ profile: textProfile, cases: output.cases.length, passed: true }));
    return;
  }
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
  await evaluate("document.querySelectorAll('button,textarea,select,input').forEach(e=>e.disabled=false);for(let i=0;i<80;i++)pwaTest.row('jarvis','Synthetic history '+i);document.querySelector('#nav-chat').focus()");
  output.tabOrder = ["nav-chat"];
  for (let turn = 0; turn < 24; turn++) { await key("Tab", 9); output.tabOrder.push(await evaluate("document.activeElement.id||document.activeElement.tagName")); }
  assert.ok(output.tabOrder.includes("log"));
  for(const id of ["library-archived","library-refresh","new-conversation","refresh-history","cancel-chat"])assert.ok(output.tabOrder.includes(id),`Keyboard cannot reach ${id}`);
  await evaluate("document.querySelector('#log').focus();document.querySelector('#log').scrollTop=0");
  await key("PageDown", 34); await pause(350);
  output.keyboardScroll = await evaluate("document.querySelector('#log').scrollTop"); assert.ok(output.keyboardScroll > 0);
  await key("Tab", 9, true); output.shiftTab = await evaluate("document.activeElement.id"); assert.equal(output.shiftTab, "search-clear");
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
  // Real File/Blob/XHR/preview lifecycle against this isolated synthetic HTTP fixture.
  await evaluate(`(async()=>{
    pwaTest.state.csrf='synthetic';pwaTest.state.historyReady=true;pwaTest.state.attachmentsAllowed=true;pwaTest.state.chatActive.clear();pwaTest.state.pendingRequest=null;pwaTest.state.sending=false;pwaTest.state.historyBusy=false;pwaTest.state.chatAction=null;pwaTest.setConnected(true);
    const canvas=document.createElement('canvas');canvas.width=2;canvas.height=2;canvas.getContext('2d').fillRect(0,0,2,2);
    const photo=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    await pwaTest.selectAttachments([new File(['<script>synthetic text</script>'],'fixture.txt'),new File([photo],'fixture.png'),new File(['synthetic PDF selection'],'fixture.pdf')]);
  })()`);
  for(let turn=0;turn<100;turn++){if(await evaluate("pwaTest.state.attachments.length===3&&pwaTest.state.attachments.every(item=>item.phase==='ready')"))break;await pause(20);}
  assert.equal(await evaluate("pwaTest.state.attachments.every(item=>item.phase==='ready')"),true);
  assert.equal(await evaluate("document.querySelector('#attachments img').naturalWidth"),2);
  assert.equal(await evaluate("document.querySelector('#attachments pre').textContent"),'<script>synthetic text</script>');
  assert.equal(await evaluate("document.querySelectorAll('#attachments script').length"),0);
  await evaluate(`(()=>{const original=window.fetch;window.workflowFetch=original;window.fetch=async(url,options)=>{
    if(String(url).endsWith('/client/conversations/search'))return new Response(JSON.stringify({results:[{conversation_id:'synthetic',sequence:1,role:'user',excerpt:'<script>synthetic search</script>'}],has_more:false,next_before:null}));
    if(String(url).endsWith('/client/tasks/synthetic'))return new Response(JSON.stringify({id:'synthetic',objective:'Synthetic task',status:'failed',nodes:[{id:'first',status:'completed',attempts:1},{id:'second',status:'failed',attempts:2,failure_class:'denied'}]}));
    return original(url,options);};document.querySelector('#history-query').value='synthetic';})()`);
  await evaluate("pwaTest.searchHistory();pwaTest.loadTask('synthetic')");
  for(let turn=0;turn<100;turn++){if(await evaluate("!pwaTest.state.search&&!pwaTest.state.taskRead"))break;await pause(20);}
  assert.equal(await evaluate("document.querySelector('#search-results p').textContent"),'<script>synthetic search</script>');
  assert.equal(await evaluate("document.querySelector('#task-progress').value"),1);
  assert.equal(await evaluate("document.querySelector('#cancel-task').disabled"),true);
  output.workflows={geometry:[]};
  for(const width of [320,375,390,430,844,1280])for(const font of [16,32]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:false});await call('Page.setFontSizes',{fontSizes:{standard:font,fixed:font}});
    const geometry=await evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,controls:[...document.querySelectorAll('#attachments button,#search-results button,#cancel-task')].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))})");
    assert.ok(geometry.scrollWidth<=width+1);for(const control of geometry.controls)assert.ok(control.width>=44&&control.height>=44);output.workflows.geometry.push({font,...geometry});
  }
  const workflowsAx=await call('Accessibility.getFullAXTree');
  for(const name of ['Remove fixture.txt','Remove fixture.png','Remove fixture.pdf','Cancel task'])assert.ok(workflowsAx.nodes.some(n=>n.role?.value==='button'&&n.name?.value===name));
  assert.ok(workflowsAx.nodes.some(n=>n.role?.value==='progressbar'&&n.name?.value==='Completed task steps'));
  await evaluate("document.querySelector('#attachments button').focus()");await key('Enter',13);
  assert.equal(await evaluate("pwaTest.state.attachments.length"),2);
  await select('settings');assert.equal(await evaluate("pwaTest.state.attachments.length"),0);
  await evaluate("window.fetch=workflowFetch;pwaTest.clearSearch({erase:true});pwaTest.state.taskSelected=null;document.querySelector('#task-detail').hidden=true");
  await select('chat');
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
  // F15 populated workspace and complete explicit interactions in actual Chromium.
  await evaluate(`(()=>{
    window.workspaceFetch=window.fetch;window.workspaceRequests=[];window.workspaceCopies=[];
    window.workspaceMarkdown='# Synthetic heading\\nParagraph **bold** and *emphasis*. [source:fixture](<https://example.com/evidence>)\\n- One\\n- Two\\n> Quote\\n| A | B |\\n| --- | --- |\\n| cell | value |\\n'+'\x60\x60\x60js\\nconst safe = 1;\\n\x60\x60\x60'+'\\n<script>window.hostileExecuted=true</script> ![remote](https://example.com/image) [bad](javascript:alert) [attachment:abc#chunk:1]';
    window.workspaceRows=Array.from({length:20},(_,i)=>({id:'workspace-'+i,title:'Synthetic conversation '+i+' <img onerror=alert>',excerpt:'Bounded synthetic excerpt '+i,updated_at:'2026-10-19T12:00:00Z',revision:0,pinned:i===0,archived:false}));
    window.workspaceTimeline={task_id:'workspace-task',events:[{sequence:50,event_type:'node_verifying',task_status:'running',node_status:'verifying',node_id:'first',created_at:'2026-10-19T12:00:00Z',explanation:'Core recorded a state transition.'}],has_more:true,next_before:50};
    window.workspaceAttachments={conversation_id:'workspace-0',available:true,vision_available:false,attachments:[{id:'a'.repeat(32),filename:'synthetic.txt',status:'ready',byte_size:42,expires_at:'2099-10-19T12:00:00Z',request_ids:['workspace-history']},{id:'b'.repeat(32),filename:'synthetic.png',status:'failed',error_code:'processing_interrupted',byte_size:24,request_ids:[]}],has_more:false};
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>workspaceCopies.push(text)}});
    window.fetch=async(url,options={})=>{
      const path=String(url),body=options.body?JSON.parse(options.body):null;workspaceRequests.push({path,method:options.method||'GET',body});let result;
      if(path.includes('/conversations/library'))result={conversations:body.offset?[{...workspaceRows[0],id:'workspace-last',title:'Last page'}]:workspaceRows.filter(r=>r.archived===body.archived),revision:1,has_more:!body.offset&&!body.archived,next_offset:20};
      else if(path.endsWith('/metadata')){const row=workspaceRows.find(r=>path.includes('/'+r.id+'/'));Object.assign(row,body,{revision:row.revision+1});result={id:row.id,revision:row.revision};}
      else if(path.includes('/conversations/search'))result={results:[{conversation_id:'workspace-0',sequence:1,role:'user',excerpt:'Synthetic matching message'}],has_more:false};
      else if(path.includes('/messages')){const cid=path.split('/conversations/')[1].split('/')[0];result={conversation_id:cid,messages:[{id:'history-u',sequence:1,role:'user',request_id:'workspace-history',content:'Synthetic question'},{id:'history-a',sequence:2,role:'assistant',request_id:'workspace-history',content:workspaceMarkdown}],requests:[],has_more:false,attachment_page:{...workspaceAttachments,conversation_id:cid}};}
      else if(path.includes('/conversations/')&&path.includes('/attachments'))result=workspaceAttachments;
      else if(path.includes('/client/conversations'))result={conversations:workspaceRows.filter(r=>!r.archived),revision:1,has_more:false};
      else if(path.includes('/client/tasks/workspace-task/events'))result=path.includes('before=')?{...workspaceTimeline,events:[{sequence:1,event_type:'task_created',task_status:'proposed'}],has_more:false}:workspaceTimeline;
      else if(path.includes('/client/tasks/workspace-task'))result={id:'workspace-task',objective:'Synthetic task <button>Approve</button>',status:'running',nodes:[{id:'first',status:'verifying',attempts:2}],timeline:workspaceTimeline};
      else if(path.includes('/client/tasks?'))result=[{id:'workspace-task',status:'running',completed_nodes:0,total_nodes:1,verifying_nodes:1}];
      else if(path.endsWith('/client/chat'))result={request_id:body.request_id,conversation_id:body.conversation_id,status:'completed',reply:workspaceMarkdown};
      else throw new Error('Unexpected workspace request '+path);
      return new Response(JSON.stringify(result),{headers:{'Content-Type':'application/json','X-Jarvis-Task-Revision':'1'}});
    };
    pwaTest.state.csrf='synthetic';pwaTest.state.subscription='subscription:workspace';pwaTest.state.historyReady=true;pwaTest.state.historyBusy=false;pwaTest.state.pendingRequest=null;pwaTest.state.chatActive.clear();pwaTest.setConnected(true);
  })()`);
  await evaluate("pwaTest.loadLibrary()");
  assert.equal(await evaluate("document.querySelectorAll('#library > li').length"),20);
  assert.equal(await evaluate("document.querySelectorAll('#library img,#library script').length"),0);
  await evaluate("document.querySelector('#library-next').click()");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryRead)");turn++)await pause(10);
  assert.equal(await evaluate("document.querySelectorAll('#library > li').length"),1);
  await evaluate("pwaTest.loadLibrary()");await evaluate("pwaTest.chooseConversation('workspace-0')");
  assert.equal(await evaluate("document.querySelectorAll('#log table,#log blockquote,#log strong,#log em').length"),4);
  assert.equal(await evaluate("document.querySelectorAll('#log script,#log img,#log iframe').length"),0);
  assert.equal(await evaluate("Boolean(window.hostileExecuted)"),false);
  assert.equal(await evaluate("[...document.querySelectorAll('#log a')].some(a=>a.protocol==='javascript:')"),false);
  await evaluate("[...document.querySelectorAll('#log button')].find(b=>b.textContent==='Copy code').click()");await pause(20);
  assert.equal(await evaluate("workspaceCopies[0]"),'const safe = 1;');
  await evaluate("[...document.querySelectorAll('#log button')].find(b=>b.textContent==='Copy response').click()");await pause(20);
  assert.equal(await evaluate("workspaceCopies[1]"),await evaluate("workspaceMarkdown"));
  output.workspace={geometry:[]};
  for(const width of [320,375,390,430,844,1280])for(const font of [16,32]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:false});await call('Page.setFontSizes',{fontSizes:{standard:font,fixed:font}});
    const geometry=await evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,controls:[...document.querySelectorAll('#library button,#log button,#conversation-attachments button')].filter(e=>!e.hidden).map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))})");
    assert.ok(geometry.scrollWidth<=width+1,JSON.stringify({font,...geometry}));for(const control of geometry.controls)assert.ok(control.width>=44&&control.height>=44);output.workspace.geometry.push({font,...geometry});
  }
  await evaluate("pwaTest.refreshTasks();pwaTest.loadTask('workspace-task',{focus:true})");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.tasksBusy||pwaTest.state.taskRead)");turn++)await pause(10);
  assert.match(await evaluate("document.querySelector('#task-events').textContent"),/verifying/);
  await evaluate("pwaTest.loadTaskTimeline({before:50,focus:true})");assert.equal(await evaluate("document.activeElement.id"),'task-timeline-title');
  assert.match(await evaluate("document.querySelector('#task-events').textContent"),/task created/);
  await evaluate("pwaTest.loadTaskTimeline()");
  const workspaceAx=await call('Accessibility.getFullAXTree');
  for(const name of ['Copy response','Copy code','Reuse synthetic.txt','Refresh library','Older task events'])assert.ok(workspaceAx.nodes.some(n=>n.role?.value==='button'&&n.name?.value===name),name);
  assert.ok(workspaceAx.nodes.some(n=>n.role?.value==='textbox'&&n.name?.value==='Conversation title'));
  await evaluate("document.querySelector('#library input[type=text]').value='Renamed synthetic';document.querySelector('#library form').requestSubmit()");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryMutation)");turn++)await pause(10);
  assert.equal(await evaluate("workspaceRows[0].title"),'Renamed synthetic');
  await evaluate("[...document.querySelectorAll('#library > li:first-child > button')].find(b=>b.textContent==='Unpin').click()");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryMutation)");turn++)await pause(10);
  assert.equal(await evaluate("workspaceRows[0].pinned"),false);
  await evaluate("[...document.querySelectorAll('#library > li:first-child > button')].find(b=>b.textContent==='Archive').click()");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryMutation)");turn++)await pause(10);
  await evaluate("document.querySelector('#library-archived').checked=true;document.querySelector('#library-archived').dispatchEvent(new Event('change'))");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryRead)");turn++)await pause(10);
  assert.equal(await evaluate("document.querySelectorAll('#library > li').length"),1);
  await evaluate("[...document.querySelectorAll('#library > li:first-child > button')].find(b=>b.textContent==='Unarchive').click()");
  for(let turn=0;turn<50&&await evaluate("Boolean(pwaTest.state.libraryMutation)");turn++)await pause(10);
  assert.equal(await evaluate("workspaceRows[0].archived"),false);
  await evaluate("pwaTest.loadAttachmentMetadata()");
  await evaluate("document.querySelector('#conversation-attachments button').click();document.querySelector('#message').value='Deliberate synthetic reuse';document.querySelector('#message').dispatchEvent(new CompositionEvent('compositionstart'));document.querySelector('#chat').dispatchEvent(new Event('submit',{cancelable:true}))");
  assert.equal(await evaluate("workspaceRequests.filter(r=>r.path.endsWith('/client/chat')).length"),0);
  await evaluate("document.querySelector('#message').dispatchEvent(new CompositionEvent('compositionend'));document.querySelector('#send').click()");
  for(let turn=0;turn<100&&await evaluate("Boolean(pwaTest.state.pendingRequest||pwaTest.state.sending)");turn++)await pause(10);
  assert.equal(await evaluate("workspaceRequests.filter(r=>r.path.endsWith('/client/chat')).length"),1);
  assert.deepEqual(await evaluate("workspaceRequests.find(r=>r.path.endsWith('/client/chat')).body.attachment_ids"),['a'.repeat(32)]);
  output.workspace.terminalSelection=await evaluate("(()=>{const row=pwaTest.row('jarvis','JARVIS: Selected text','terminal-selection'),range=document.createRange();range.setStart(row.firstChild,8);range.setEnd(row.firstChild,16);getSelection().removeAllRanges();getSelection().addRange(range);const focus=document.activeElement;pwaTest.row('jarvis','JARVIS: # Canonical replacement','terminal-selection',true);const result={text:getSelection().toString(),deferred:row.pendingFormat,focusKept:focus===document.activeElement};getSelection().removeAllRanges();return result;})()");
  assert.equal(output.workspace.terminalSelection.text,'Selected');assert.ok(output.workspace.terminalSelection.deferred&&output.workspace.terminalSelection.focusKept);
  await pause(30);assert.equal(await evaluate("document.querySelector('[data-request=terminal-selection]').formatted"),true);
  await call('Performance.enable');await call('HeapProfiler.collectGarbage');
  const heapBefore=(await call('Performance.getMetrics')).metrics.find(m=>m.name==='JSHeapUsedSize').value;
  output.workspace.bounds=await evaluate("(()=>{const start=performance.now();for(let i=0;i<300;i++)pwaTest.row('jarvis','Synthetic bounded reply '+i,'bounded-'+i,true);return {rows:document.querySelector('#log').children.length,chars:[...document.querySelector('#log').children].reduce((n,r)=>n+(r.replyText||'').length,0),nodes:document.querySelectorAll('#log *').length,durationMs:performance.now()-start};})()");
  assert.ok(output.workspace.bounds.rows<=200&&output.workspace.bounds.chars<=512000&&output.workspace.bounds.nodes<=10000);
  output.workspace.largeBounds=await evaluate("(()=>{const start=performance.now();for(let i=0;i<20;i++)pwaTest.row('jarvis','JARVIS: '+'x'.repeat(100000),'large-'+i,true);return {rows:document.querySelector('#log').children.length,chars:[...document.querySelector('#log').children].reduce((n,r)=>n+(r.replyText||'').length,0),nodes:document.querySelectorAll('#log *').length,durationMs:performance.now()-start};})()");
  await call('HeapProfiler.collectGarbage');output.workspace.largeBounds.heapGrowthBytes=(await call('Performance.getMetrics')).metrics.find(m=>m.name==='JSHeapUsedSize').value-heapBefore;
  assert.ok(output.workspace.largeBounds.chars<=512000&&output.workspace.largeBounds.nodes<=10000&&output.workspace.largeBounds.heapGrowthBytes<16*1024*1024);
  output.workspace.privacy=await evaluate("({urlsSafe:workspaceRequests.every(r=>!r.path.includes('Deliberate')&&!r.path.includes('Renamed')),storageSafe:!JSON.stringify({...sessionStorage,...localStorage}).includes('synthetic reuse'),noControl:workspaceRequests.every(r=>!/(cancel|approve|execute|run)$/.test(r.path)),location:location.hash})");
  assert.ok(output.workspace.privacy.urlsSafe&&output.workspace.privacy.storageSafe&&output.workspace.privacy.noControl);
  await evaluate("window.fetch=workspaceFetch");
  await select("garmin");
  await evaluate("pwaTest.state.csrf=null;pwaTest.state.hasIdentity=true;pwaTest.setConnected(false);pwaTest.logout()");
  output.logoutFocus = await evaluate("document.activeElement.id"); assert.equal(output.logoutFocus, "ticket");
  await call("Page.setFontSizes", { fontSizes: { standard: 32, fixed: 32 } });
  await call("Emulation.setDeviceMetricsOverride", { width: 320, height: 844, deviceScaleFactor: 1, mobile: false });
  await evaluate("scrollTo(0,0)");
  const screenshot = await call("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  fs.writeFileSync(path.join(outputDir, "enlarged-320.png"), Buffer.from(screenshot.data, "base64"));
  output.navigation.apiRequests = apiRequests; assert.equal(apiRequests.filter(item=>!item.path.startsWith('/api/v1/client/attachments/')).length,0);
  assert.equal(apiRequests.filter(item=>item.method==='POST').length,3);assert.equal(apiRequests.filter(item=>item.method==='DELETE').length,3);
  fs.writeFileSync(path.join(outputDir, "desktop.json"), JSON.stringify(output, null, 2));
  console.log(JSON.stringify({ pass: true, cases: output.cases.length, contrast: output.contrast, keyboard: true, history: true, namedLog: true, output: "runtime/mvp4-fixes/desktop.json" }));
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (call) { try { await call("Browser.close"); } catch {} }
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close();
});
