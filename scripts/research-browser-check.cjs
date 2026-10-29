"use strict";

// Real PWA/auth/Core/SQLite/public HTTPS research; disposable identity and TLS pin only.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {spawn,spawnSync}=require("node:child_process");
const config=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
const dir=config.directory,origin=`https://127.0.0.1:${config.port}`;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={profile:"public-research",checks:[],samples:[]};
const save=()=>fs.writeFileSync(path.join(dir,"browser-results.json"),JSON.stringify(report,null,2));
const calls=()=>{try{return fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").filter(Boolean).length;}catch{return 0;}};
let core,browser,ws,call,evaluate;
const log=fs.openSync(path.join(dir,"core.log"),"a");
async function startCore(){
  core=spawn(config.python,["scripts/research-acceptance.py","--serve",dir,"--port",String(config.port)],{windowsHide:true,stdio:["ignore",log,log]});
  for(let i=0;i<200;i++){
    if(core.exitCode!==null)throw Error("Synthetic Core exited; inspect ignored core.log");
    const probe=spawnSync(config.python,["-c",`import socket;s=socket.create_connection(('127.0.0.1',${config.port}),.1);s.close()`],{windowsHide:true,stdio:"ignore"});
    if(probe.status===0&&fs.existsSync(path.join(dir,"tickets.json")))return;
    await pause(100);
  }
  throw Error("Synthetic Core startup timeout");
}
async function stopCore(){if(core&&core.exitCode===null){core.kill();await new Promise(resolve=>core.once("exit",resolve));}}
async function wait(expression,timeout=90000){
  const started=Date.now();while(Date.now()-started<timeout){const result=await evaluate(expression);if(result)return result;await pause(30);}
  throw Error(`Wait timeout: ${expression}; ${JSON.stringify(await evaluate("({ready:document.readyState,connection:document.querySelector('#connection')?.textContent,access:document.querySelector('#access-status')?.textContent,chat:document.querySelector('#chat-status')?.textContent})"))}`);
}
async function click(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);}
async function input(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function ready(){await wait("(()=>{if(!state.connecting&&ui.connection.textContent==='Connection failed')throw Error(ui.accessStatus.textContent);return state.online&&state.historyReady&&!state.historyBusy&&!state.connecting;})()");}
async function send(prompt,label){
  await ready();await input("#message",prompt);
  await evaluate("ui.chat.requestSubmit()");
  const request=await wait("state.pendingRequest?.request_id",5000);
  await wait(`state.chatAnnounced.has(${JSON.stringify(request)})&&!state.pendingRequest&&!state.sending`);
  const result=await evaluate(`(async()=>{return (await(await api('/client/chat/'+${JSON.stringify(request)})).json());})()`);
  assert.equal(result.status,"completed",JSON.stringify(result));
  report.samples.push({label,request_id:request,reply:result.reply});save();return result;
}
async function main(){
  await startCore();
  const profile=fs.mkdtempSync(path.join(dir,"edge-"));
  browser=spawn(process.env.PWA_TEST_BROWSER||"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",["--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check","--disable-background-networking",`--ignore-certificate-errors-spki-list=${config.spki}`,"--remote-debugging-port=0",`--user-data-dir=${profile}`,"about:blank"],{windowsHide:true,stdio:"ignore"});
  let port;for(let i=0;i<150;i++){try{port=Number(fs.readFileSync(path.join(profile,"DevToolsActivePort"),"utf8").split("\n")[0]);break;}catch{await pause(100);}}
  assert.ok(port,"Edge unavailable");
  const targets=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target=targets.find(t=>t.type==="page"&&t.url==="about:blank");
  assert.ok(target,"Disposable blank test tab required");
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise(resolve=>ws.addEventListener("open",resolve,{once:true}));
  let sequence=0;const pending=new Map();
  ws.addEventListener("message",async event=>{
    const message=JSON.parse(event.data),item=pending.get(message.id);
    if(item){pending.delete(message.id);clearTimeout(item.timer);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}
    if(message.method==="Fetch.requestPaused"){
      try{
        const result=await call("Fetch.getResponseBody",{requestId:message.params.requestId});
        const source=result.base64Encoded?Buffer.from(result.body,"base64").toString("utf8"):result.body;
        await call("Fetch.fulfillRequest",{requestId:message.params.requestId,responseCode:200,responseHeaders:message.params.responseHeaders.filter(h=>!["content-length","content-encoding"].includes(h.name.toLowerCase())),body:Buffer.from(source+"\nObject.assign(globalThis,{state,ui,api,openDb,STORE,chooseConversation,renderReply});\n").toString("base64")});
      }catch(error){console.error(error);}
    }
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},100000)});ws.send(JSON.stringify({id,method,params}));});
  evaluate=async expression=>{const result=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call("Page.enable");await call("Fetch.enable",{patterns:[{urlPattern:origin+"/app/app.js*",requestStage:"Response"}]});
  await call("Page.navigate",{url:origin+"/app/"});await wait("typeof state!=='undefined'&&document.readyState==='complete'");
  const tickets=JSON.parse(fs.readFileSync(path.join(dir,"tickets.json"),"utf8"));
  await click("#nav-settings");await input("#ticket",JSON.stringify(tickets[0]));await click("#enroll");await ready();await click("#nav-chat");
  assert.equal(await evaluate("state.attachmentsAllowed"),false);
  assert.equal(await evaluate("document.body.dataset.profile"),"public-research");
  const prompt="Research current Python macOS installer certificates and SQLite Windows support at https://www.python.org/downloads/ and https://www.sqlite.org/changes.html";
  const first=await send(prompt,"live-public-sources");
  assert.match(first.reply,/Source states:/);assert.match(first.reply,/published (unknown|[0-9]{4})/);
  assert.match(first.reply,/Evidence expires/);assert.match(first.reply,/not independently verified/);
  await wait("document.querySelectorAll('#log .reply-body a').length>=2");
  const links=await evaluate("[...document.querySelectorAll('#log .reply-body a')].map(a=>({url:a.href,rel:a.rel,referrer:a.referrerPolicy}))");
  for(const host of ["www.python.org","www.sqlite.org"])assert.ok(links.some(a=>new URL(a.url).hostname===host));
  assert.ok(links.every(a=>a.rel==="noopener noreferrer"&&a.referrer==="no-referrer"));
  report.checks.push("actual public-source fetch/parser/extractive citation pipeline; safe clickable source URLs; freshness and uncertainty");
  const before=fs.readFileSync(path.join(dir,"evidence.jsonl"),"utf8").trim().split("\n").length;
  const replay=await evaluate(`(async()=>{const r=await api('/client/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:${JSON.stringify(first.request_id)},subscription_id:state.subscription,conversation_id:null,message:${JSON.stringify(prompt)}})});return r.json();})()`);
  assert.equal(replay.status,"completed");assert.equal(fs.readFileSync(path.join(dir,"evidence.jsonl"),"utf8").trim().split("\n").length,before);
  const unavailable=await send("What is the latest Python version?","wikimedia-discovery");
  assert.match(unavailable.reply,/Current evidence is unavailable/);assert.doesNotMatch(unavailable.reply,/\[Source \d/);
  report.checks.push("immutable request replay performs no acquisition; actual blocked discovery gives deterministic unavailable");
  await stopCore();await startCore();await click("#nav-settings");await click("#connect");await ready();await click("#nav-chat");
  const second=await send(prompt,"fresh-after-restart");assert.match(second.reply,/Source states:/);
  const records=fs.readFileSync(path.join(dir,"evidence.jsonl"),"utf8").trim().split("\n").map(JSON.parse);
  assert.equal(records.length,2);
  for(const record of records){
    assert.equal(record.sources.length,2);
    for(const claim of record.claims)for(const cite of claim.citations){
      const source=record.sources.find(s=>s.id===cite.source_id),[start,end]=cite.locator.slice(5).split("-").map(Number);
      assert.equal(source.extracted_text.slice(start,end),cite.quote);assert.ok(cite.quote.split(/\s+/).length<=25);
    }
  }
  assert.ok(records[1].sources.every(s=>s.retrieved_at>records[0].sources.find(x=>x.url===s.url).retrieved_at));
  report.checks.push("restart obtains fresh public evidence; exact source spans and quote budgets verified against actual parser output");
  // Literal source syntax must not create a source-authored link/control.
  const hostile="Source states: \\[trap\\]\\(https://example.com\\) <script>bad</script>";
  assert.deepEqual(await evaluate(`(()=>{const r=renderReply(${JSON.stringify(hostile)});return [...r.querySelectorAll('a,script,img,iframe,button')].map(x=>x.tagName);})()`),[]);
  const persistent=await evaluate("(async()=>{const db=await openDb();const rows=await new Promise((resolve,reject)=>{const r=db.transaction(STORE).objectStore(STORE).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});db.close();return JSON.stringify({rows,local:{...localStorage},session:{...sessionStorage},caches:await Promise.all((await caches.keys()).map(async n=>(await(await caches.open(n)).keys()).map(r=>r.url)))});})()");
  for(const term of [prompt,first.reply,second.reply,"sqlite.org/changes"])assert.equal(persistent.includes(term),false);
  await click("#nav-settings");await click("#logout");await wait("!state.hasIdentity&&!state.csrf");
  assert.equal(await evaluate("ui.log.textContent+ui.message.value"),"");
  assert.equal(fs.existsSync(path.join(dir,"unexpected-model-call")),false);
  report.checks.push("hostile source syntax stays inert; no browser source persistence, model call or tool authority; logout erasure");
  report.passed=true;save();console.log(JSON.stringify({passed:true,checks:report.checks.length,real_public_runs:2,model_calls:0}));

}
main().catch(error=>{report.error=String(error.stack||error);save();console.error(report.error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();if(browser)browser.kill();await stopCore();fs.closeSync(log);});
