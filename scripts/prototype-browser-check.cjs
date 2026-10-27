"use strict";

// Real assets/auth/Core/SQLite/Ollama. Only synthetic stores and process-local TLS pin.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {spawn, spawnSync} = require("node:child_process");
const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const dir = config.directory, origin = `https://127.0.0.1:${config.port}`;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let core, browser, ws, call, evaluate;
// `passed` covers this integration matrix only. Corpus rubric scoring is separate.
const report = {scope: 'integration matrix; corpus quality requires separate review', model: config.model, ollama: config.ollama, resident_before: config.resident_before, samples: [], checks: []};
const save = () => fs.writeFileSync(path.join(dir, "browser-results.json"), JSON.stringify(report, null, 2));
const providerCalls = () => {try{return fs.readFileSync(path.join(dir,'provider-calls.jsonl'),'utf8').trim().split('\n').filter(Boolean).length;}catch{return 0;}};
const log = fs.openSync(path.join(dir, "core.log"), "a");
async function startCore() {
  core = spawn(config.python, ["scripts/prototype-acceptance.py", "--serve", dir, "--port", String(config.port), "--model", config.model.name, "--profile", config.profile||"prototype-text"], {windowsHide:true, stdio:["ignore", log, log]});
  for (let i=0;i<200;i++) {
    if(core.exitCode!==null)throw Error("Synthetic Core exited; inspect ignored core.log");
    const ready=spawnSync(config.python,["-c",`import socket; s=socket.create_connection(('127.0.0.1',${config.port}),.1); s.close()`],{windowsHide:true,stdio:"ignore"});
    if(ready.status===0&&fs.existsSync(path.join(dir,"tickets.json")))return;
    await pause(100);
  }
  throw Error("Synthetic Core startup timeout");
}
async function wait(expression, timeout=60000) {
  const start=Date.now(); let value;
  while(Date.now()-start<timeout){value=await evaluate(expression);if(value)return value;await pause(20);}
  throw Error(`Wait timeout: ${expression}; state=${JSON.stringify(await evaluate("({status:ui.chatStatus.textContent,connection:ui.connection.textContent,access:ui.accessStatus.textContent})"))}`);
}
async function click(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);}
async function input(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function ready(){await wait("state.online&&state.historyReady&&!state.historyBusy&&!state.connecting");}
async function fresh(){await click("#new-conversation");await ready();}
async function send(prompt, id){
  await ready();
  await input("#message",prompt);
  await evaluate(`(()=>{globalThis.measure={start:performance.now(),first:null,feedback:null,deltas:0};globalThis.observer?.disconnect();globalThis.observer=new MutationObserver(()=>{const m=globalThis.measure;if(m.feedback===null&&ui.chat.getAttribute('aria-busy')==='true')m.feedback=performance.now()-m.start;const row=m.requestId&&ui.log.querySelector('[data-request="'+CSS.escape(m.requestId)+'"]');if(row?.className==='entry jarvis'&&row.textContent.trim()!=='JARVIS:'&&!row.textContent.includes('Reply in progress')){m.deltas++;if(m.first===null)m.first=performance.now()-m.start;}});observer.observe(document.querySelector('#view-chat'),{subtree:true,childList:true,characterData:true,attributes:true});ui.chat.requestSubmit();measure.requestId=state.pendingRequest?.request_id;})()`);
  const requestId=await wait("state.pendingRequest?.request_id||[...state.chatAnnounced.keys()].at(-1)",5000);
  await wait(`state.chatAnnounced.has(${JSON.stringify(requestId)})&&!state.pendingRequest&&!state.sending`,90000);
  const result=await evaluate(`(()=>{observer.disconnect();const e=ui.log.querySelector('[data-request="'+CSS.escape(${JSON.stringify(requestId)})+'"]');return {id:${JSON.stringify(id)},request_id:${JSON.stringify(requestId)},conversation:state.conversation,reply:(e?.replyText??e?.textContent)?.replace(/^JARVIS: /,''),completed:state.chatAnnounced.get(${JSON.stringify(requestId)}),first_ms:measure.first,completion_ms:performance.now()-measure.start,feedback_ms:measure.feedback,visible_changes:measure.deltas};})()`);
  report.samples.push(result);save();return result;
}
async function main(){
  await startCore();
  const profile=fs.mkdtempSync(path.join(dir,"edge-"));
  browser=spawn(process.env.PWA_TEST_BROWSER||"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",["--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check","--disable-background-networking",`--ignore-certificate-errors-spki-list=${config.spki}`,"--remote-debugging-port=0",`--user-data-dir=${profile}`,"about:blank"],{windowsHide:true,stdio:"ignore"});
  let port;
  for(let i=0;i<150;i++){try{port=Number(fs.readFileSync(path.join(profile,"DevToolsActivePort"),"utf8").split("\n")[0]);break;}catch{await pause(100);}}
  assert.ok(port,"Edge unavailable");
  const targets=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(targets.find(t=>t.type==="page").webSocketDebuggerUrl);
  await new Promise(resolve=>ws.addEventListener("open",resolve,{once:true}));
  let sequence=0;const pending=new Map();
  ws.addEventListener("message",async event=>{const m=JSON.parse(event.data),p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}
    if(m.method==='Network.responseReceived'&&m.params.response.status===429)report.http_429=(report.http_429||0)+1;
    if(m.method==='Fetch.requestPaused'){
      try{
        const r=await call('Fetch.getResponseBody',{requestId:m.params.requestId});
        const source=r.base64Encoded?Buffer.from(r.body,'base64').toString('utf8'):r.body;
        const body=Buffer.from(source+'\nObject.assign(globalThis,{state,ui,chooseConversation,openDb,API,STORE,api});\n').toString('base64');
        await call('Fetch.fulfillRequest',{requestId:m.params.requestId,responseCode:200,responseHeaders:m.params.responseHeaders.filter(h=>!['content-length','content-encoding'].includes(h.name.toLowerCase())),body});
      }catch(error){console.error(error);}
    }
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},100000)});ws.send(JSON.stringify({id,method,params}));});
  evaluate=async expression=>{const r=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await call("Page.enable");await call("Network.enable");
  // Append observation handles to the fetched module in this disposable browser only.
  // Production source, auth, requests and all application behavior remain real.
  await call('Fetch.enable',{patterns:[{urlPattern:origin+'/app/app.js*',requestStage:'Response'}]});
  await call("Page.navigate",{url:origin+"/app/"});
  await wait("typeof state!=='undefined'&&document.readyState==='complete'");
  assert.equal(await evaluate("ui.send.disabled"),true);
  await click("#nav-settings");
  const tickets=JSON.parse(fs.readFileSync(path.join(dir,"tickets.json"),"utf8"));
  await input("#ticket",JSON.stringify(tickets[0]));await click("#enroll");await ready();await click("#nav-chat");
  report.checks.push("real browser enrollment, signed bootstrap, stream/history readiness");save();
  const clockBefore=Date.now();const clock=await send("What is the time?","clock");
  const timestamp=clock.reply.match(/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d/);
  assert.ok(timestamp&&Date.parse(timestamp[0])>=clockBefore-1000&&Date.parse(timestamp[0])<=Date.now());
  assert.equal(providerCalls(),0,'deterministic clock makes no model request');
  await fresh();await send(config.cases[0].prompt,"cold-E1");
  const conversations={};
  for(const item of config.cases){
    if(item.parent||item.id==='F1'||item.id==='F2'){
      const cid=conversations[item.parent||(item.id==='F1'?'C1':'R2')];
      await evaluate(`chooseConversation(${JSON.stringify(cid)})`);await ready();
    }else await fresh();
    const result=await send(item.prompt,item.id);conversations[item.id]=result.conversation;
  }
  report.checks.push(`${config.cases.length} frozen corpus prompts through real PWA`);save();
  await fresh();
  const streamed=await send('Give exactly 20 numbered synthetic desk labels, each containing three words. Do not perform any actions. Use under 150 words.','stream-demo');
  report.streaming_passed=Boolean(streamed.completed&&streamed.visible_changes>=2&&!streamed.reply.includes('The current time'));
  report.real_provider_deltas=fs.readFileSync(path.join(dir,'provider-deltas.jsonl'),'utf8').trim().split('\n').length;
  assert.ok(report.real_provider_deltas>0);
  // UI rename/pin/search and conversation isolation.
  await click("#library-refresh");await wait("ui.library.querySelector('form input')");
  await input("#library form input","Synthetic prototype saved");
  await evaluate("ui.library.querySelector('form').requestSubmit()");
  await wait("ui.library.textContent.includes('Synthetic prototype saved')");
  await evaluate("[...ui.library.querySelectorAll('button')].find(b=>b.textContent==='Pin').click()");
  await wait("ui.library.textContent.includes('Synthetic prototype saved')&&[...ui.library.querySelectorAll('button')].some(b=>b.textContent==='Unpin')");
  await input("#history-query","blue box");await evaluate("document.querySelector('#search-history').requestSubmit()");
  await wait("document.querySelector('#search-results').children.length>0");
  report.checks.push("rename, pin, search real stored history");save();
  // Capture immutable request after server acceptance; discard only its HTTP acknowledgement.
  await fresh();
  const callsBefore=providerCalls();
  await evaluate("globalThis.originalFetch=fetch;globalThis.lost=null;globalThis.fetch=async(...args)=>{const response=await originalFetch(...args);if(String(args[0]).endsWith('/client/chat')&&args[1]?.method==='POST'){globalThis.lost=JSON.parse(args[1].body);globalThis.fetch=originalFetch;throw new TypeError('Synthetic lost acknowledgement');}return response;}");
  await send("Explain a rainbow in two sentences under 60 words.","lost-ack");
  const immutable=await evaluate("lost");
  assert.ok(immutable);
  const retry=await evaluate(`(async()=>{const r=await api('/client/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(immutable)})});return r.json();})()`);
  assert.equal(retry.status,"completed");
  assert.equal(providerCalls()-callsBefore,1,'lost acknowledgement plus retry generates once');
  report.retry_provider_calls=providerCalls()-callsBefore;
  const substitution=await evaluate(`(async()=>{const r=await fetch(API+'/client/chat',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-Jarvis-CSRF':state.csrf},body:JSON.stringify({...${JSON.stringify(immutable)},message:'Substituted payload'})});return r.status;})()`);
  assert.equal(substitution,409);report.duplicate_request_id=immutable.request_id;
  report.checks.push("lost HTTP acknowledgement, immutable retry, substitution rejected");save();
  // Real local long turn cancellation; no assertion about native Ollama computation.
  await fresh();await input("#message","List 1000 synthetic numbered workshop tasks, explaining each in detail.");
  await evaluate("ui.chat.requestSubmit()");const cancelId=await wait("state.pendingRequest?.request_id");
  const cancelStart=Date.now();await wait("!ui.cancelChat.disabled",5000);await click("#cancel-chat");
  await wait(`!state.pendingRequest&&!state.chatActive.has(${JSON.stringify(cancelId)})`,5000);
  report.cancel_ms=Date.now()-cancelStart;
  const cancelled=await evaluate(`(async()=>{const r=await api('/client/chat/'+encodeURIComponent(${JSON.stringify(cancelId)}));return r.json();})()`);
  assert.equal(cancelled.status,"cancelled");
  const afterCancel=await evaluate("ui.log.textContent");await pause(1000);assert.equal(await evaluate("ui.log.textContent"),afterCancel);
  report.checks.push("real cancellation terminal on Core; no post-cancel visible additions");save();
  // Crash while genuine generation is pending, same database, retained browser key.
  await fresh();await input("#message","Write 1000 numbered synthetic explanations of rainbows.");await evaluate("ui.chat.requestSubmit()");
  const interrupted=await wait("state.pendingRequest?.request_id");
  await wait(`(async()=>{try{return (await(await api('/client/chat/'+encodeURIComponent(${JSON.stringify(interrupted)}))).json()).status==='running';}catch{return false;}})()`,5000);
  core.kill();await new Promise(resolve=>core.once("exit",resolve));await startCore();
  await click("#nav-settings");await click("#connect");await ready();await click("#nav-chat");
  const recovered=await evaluate(`(async()=>{return (await(await api('/client/chat/'+encodeURIComponent(${JSON.stringify(interrupted)}))).json());})()`);
  assert.equal(recovered.status,"interrupted");report.interrupted_request_id=interrupted;
  await click("#library-refresh");await wait("ui.library.textContent.includes('Synthetic prototype saved')");
  report.checks.push("crash/restart interrupts pending work; history and metadata survive");save();
  await call("Network.emulateNetworkConditions",{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
  await wait("ui.send.disabled",5000);
  await call("Network.emulateNetworkConditions",{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await click("#nav-settings");await click("#connect");await ready();
  await input("#message","Synthetic private draft must vanish");await click("#logout");await wait("!state.hasIdentity&&!state.csrf");
  assert.equal(await evaluate("ui.log.textContent+ui.message.value"),"");
  const persistence=await evaluate("(async()=>{const db=await openDb();const keys=await new Promise((resolve,reject)=>{const r=db.transaction(STORE).objectStore(STORE).getAllKeys();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});db.close();return {keys,local:Object.keys(localStorage),session:Object.keys(sessionStorage),cache:await Promise.all((await caches.keys()).map(async name=>({name,urls:(await(await caches.open(name)).keys()).map(r=>new URL(r.url).pathname)})))};})()");
  assert.equal(persistence.keys.length,0);assert.equal(persistence.local.length,0);assert.equal(persistence.session.length,0);
  assert.ok(persistence.cache.every(c=>c.urls.every(u=>u.startsWith('/app/'))));report.persistence=persistence;
  const denied=await evaluate("(async()=>{return (await fetch(API+'/client/conversations',{credentials:'include'})).status;})()");assert.equal(denied,401);
  // Second actual device cannot see first device's conversation.
  await input("#ticket",JSON.stringify(tickets[1]));await click("#enroll");await ready();
  const foreign=await evaluate(`(async()=>{return (await fetch(API+'/client/conversations/'+encodeURIComponent(${JSON.stringify(conversations.C1)})+'/messages',{credentials:'include'})).status;})()`);
  assert.ok([403,404].includes(foreign));await click("#logout");
  report.checks.push("offline/reconnect/logout erasure, shell-only cache, unauthenticated and foreign-device denial");
  report.matrix_passed=true;
  report.passed=report.streaming_passed;save();console.log(JSON.stringify({passed:report.passed,checks:report.checks.length,samples:report.samples.length}));
  if(!report.passed)process.exitCode=1;
}
main().catch(error=>{report.error=String(error.stack||error);save();console.error(report.error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();if(browser)browser.kill();if(core)core.kill();fs.closeSync(log);});
