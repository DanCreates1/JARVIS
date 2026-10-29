"use strict";

// Real PWA/auth/Core/SQLite/Ollama; disposable synthetic identities, files and TLS pin only.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {spawn,spawnSync}=require("node:child_process");
const config=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
const dir=config.directory,origin=`https://127.0.0.1:${config.port}`;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={profile:"private-files",checks:[],samples:[]};
const save=()=>fs.writeFileSync(path.join(dir,"browser-results.json"),JSON.stringify(report,null,2));
const calls=()=>{try{return fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").filter(Boolean).length;}catch{return 0;}};
let core,browser,ws,call,evaluate;
const log=fs.openSync(path.join(dir,"core.log"),"a");
async function startCore(){
  core=spawn(config.python,["scripts/files-acceptance.py","--serve",dir,"--port",String(config.port)],{windowsHide:true,stdio:["ignore",log,log]});
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
async function upload(filename){
  await ready();
  const doc=await call("DOM.getDocument"),node=await call("DOM.querySelector",{nodeId:doc.root.nodeId,selector:"#attachment-file"});
  await call("DOM.setFileInputFiles",{nodeId:node.nodeId,files:[path.join(dir,filename)]});
  await evaluate("document.querySelector('#attachment-file').dispatchEvent(new Event('change',{bubbles:true}))");
  await wait("state.attachments.length===1&&state.attachments[0].phase==='ready'",10000);
}
async function send(prompt,label){
  await ready();await input("#message",prompt);
  await evaluate("ui.chat.requestSubmit()");
  const request=await wait("state.pendingRequest?.request_id",5000);
  await wait(`state.chatAnnounced.has(${JSON.stringify(request)})&&!state.pendingRequest&&!state.sending`);
  const result=await evaluate(`(async()=>{return (await(await api('/client/chat/'+${JSON.stringify(request)})).json());})()`);
  assert.equal(result.status,"completed",JSON.stringify(result));
  report.samples.push({label,request_id:request,reply:result.reply});save();return result;
}
async function metadata(){
  await click("#refresh-attachments");
  await wait("!state.attachmentRead&&state.attachmentPage&&state.attachmentPage.conversation_id===state.conversation");
  return evaluate("state.attachmentPage");
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
        await call("Fetch.fulfillRequest",{requestId:message.params.requestId,responseCode:200,responseHeaders:message.params.responseHeaders.filter(h=>!["content-length","content-encoding"].includes(h.name.toLowerCase())),body:Buffer.from(source+"\nObject.assign(globalThis,{state,ui,api,openDb,STORE,chooseConversation});\n").toString("base64")});
      }catch(error){console.error(error);}
    }
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},100000)});ws.send(JSON.stringify({id,method,params}));});
  evaluate=async expression=>{const result=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call("Page.enable");await call("Fetch.enable",{patterns:[{urlPattern:origin+"/app/app.js*",requestStage:"Response"}]});
  await call("Page.navigate",{url:origin+"/app/"});await wait("typeof state!=='undefined'&&document.readyState==='complete'");
  const tickets=JSON.parse(fs.readFileSync(path.join(dir,"tickets.json"),"utf8"));
  await click("#nav-settings");await input("#ticket",JSON.stringify(tickets[0]));await click("#enroll");await ready();await click("#nav-chat");
  assert.equal(await evaluate("state.attachmentsAllowed"),true);
  assert.match(await evaluate("document.querySelector('#file-capabilities').textContent"),/Image understanding unavailable/);
  report.checks.push("real cookie/CSRF/signed bootstrap and explicit file capability; absent vision explained");
  await upload("cedar.txt");assert.equal(calls(),0,"staging alone invokes no model");
  const preview=await evaluate("document.querySelector('#attachments pre').textContent");assert.equal(preview,"cedar inventory has 17 lanterns");
  const text=await send("According only to selected text, how many lanterns are in cedar inventory? State count and cite exact [attachment:ID#chunk:N] reference.","text");
  assert.match(text.reply,/\b17\b/);
  const cid=text.conversation_id;
  let page=await metadata(),textId=page.attachments.find(a=>a.filename==="cedar.txt").id;
  assert.ok(text.reply.includes(`[attachment:${textId}#chunk:0]`),"text answer needs exact supplied source reference");
  assert.equal(page.attachments.length,1);assert.equal(page.attachments[0].status,"ready");
  report.checks.push("real file input, safe text preview, explicit Send, isolated extraction, grounded text citation");
  await upload("harbor.pdf");assert.equal(await evaluate("document.querySelectorAll('#attachments iframe,#attachments object,#attachments embed').length"),0);
  const pdf=await send("According only to selected PDF, how many crates are in harbor shipment? State count and cite exact [attachment:ID#chunk:N] reference.","pdf");
  assert.match(pdf.reply,/\b23\b/);page=await metadata();const pdfId=page.attachments.find(a=>a.filename==="harbor.pdf").id;
  assert.ok(pdf.reply.includes(`[attachment:${pdfId}#chunk:0]`));
  const before=calls();
  await evaluate(`(()=>{const button=[...ui.conversationAttachments.querySelectorAll('button')].find(b=>b.textContent==='Reuse cedar.txt');button.click();})()`);
  assert.equal(calls(),before,"reuse selection invokes no model");
  const reuse=await send("According only to selected file, give original lantern count with exact attachment/chunk citation.","reuse");
  assert.match(reuse.reply,/\b17\b/);assert.ok(reuse.reply.includes(`[attachment:${textId}#chunk:0]`));
  report.checks.push("text PDF stays inert; grounded PDF citation; deliberate same-conversation source reuse");
  // Replay an accepted immutable request, without parsing or generating again.
  const replay=await evaluate(`(async()=>{const id=${JSON.stringify(reuse.request_id)},r=await api('/client/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:id,subscription_id:state.subscription,conversation_id:state.conversation,message:'According only to selected file, give original lantern count with exact attachment/chunk citation.',attachment_ids:[${JSON.stringify(textId)}]})});return r.json();})()`);
  assert.equal(replay.status,"completed");assert.equal(calls(),before+1);
  await upload("red.png");await wait("document.querySelector('#attachments img')?.naturalWidth===16");
  const image=await send("Is image understanding available for selected image? If unavailable, state vision_unavailable and do not guess visible contents.","image-unavailable");
  assert.match(image.reply,/unavailable/i);assert.doesNotMatch(image.reply,/red (square|image|pixels)/i);
  report.checks.push("receipt replay generates once; local photo preview/normalization; explicit unavailable image understanding");
  await input("#history-query","lantern");await evaluate("document.querySelector('#search-history').requestSubmit()");
  await wait("!state.search&&document.querySelector('#search-results').children.length>0");
  assert.ok((await evaluate("document.querySelector('#search-results').textContent")).includes("lantern"));
  await click("#search-clear");
  // Crash/restart preserves sources and sticky privacy; staging is memory-only and never resumes.
  await upload("cedar.txt");const stagedId=await evaluate("state.attachments[0].id");
  await stopCore();await startCore();
  await click("#nav-settings");await click("#connect");await ready();await click("#nav-chat");
  await evaluate(`chooseConversation(${JSON.stringify(cid)})`);await ready();page=await metadata();
  assert.equal(page.attachments.length,3);assert.ok(page.attachments.every(a=>a.status==="ready"));
  const beforeStale=calls();
  const staleUpload=await evaluate(`(async()=>{const r=await api('/client/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:'request:stale-upload',subscription_id:state.subscription,message:'No automatic upload resume',conversation_id:state.conversation,upload_ids:[${JSON.stringify(stagedId)}]})});return r.json();})()`);
  assert.equal(staleUpload.status,'failed');assert.equal(staleUpload.error.code,'upload_unavailable');assert.equal(calls(),beforeStale);
  report.checks.push("literal private history search; restart retains ready metadata; old staging denied without automatic retry");
  // Real local cancellation remains a terminal receipt and never gains file/action authority.
  await input("#message","Write 1000 numbered synthetic explanations of lanterns.");await evaluate("ui.chat.requestSubmit()");
  const cancelled=await wait("state.pendingRequest?.request_id",5000);await wait("!ui.cancelChat.disabled",5000);await click("#cancel-chat");
  await wait("!state.pendingRequest&&state.chatActive.size===0",5000);
  assert.equal(await evaluate(`(async()=>{return (await(await api('/client/chat/'+${JSON.stringify(cancelled)})).json()).status;})()`),"cancelled");
  // Private browser state never persists; logout clears all source/history/draft state.
  const persistent=await evaluate("(async()=>{const db=await openDb();const rows=await new Promise((resolve,reject)=>{const request=db.transaction(STORE).objectStore(STORE).getAll();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});db.close();return JSON.stringify({rows,local:{...localStorage},session:{...sessionStorage},caches:await Promise.all((await caches.keys()).map(async n=>(await(await caches.open(n)).keys()).map(r=>r.url)))});})()");
  for(const term of ["cedar inventory","harbor shipment","17 lanterns","23 crates","red.png"])assert.equal(persistent.includes(term),false);
  assert.ok(fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").every(line=>JSON.parse(line).tool_count===0));
  await click("#nav-settings");await click("#logout");await wait("!state.hasIdentity&&!state.csrf");
  assert.equal(await evaluate("ui.log.textContent+ui.message.value+ui.conversationAttachments.textContent"),"");
  await input("#ticket",JSON.stringify(tickets[1]));await click("#enroll");await ready();
  const foreign=await evaluate(`(async()=>{return (await fetch('/api/v1/client/conversations/'+${JSON.stringify(cid)}+'/attachments',{credentials:'include'})).status;})()`);assert.ok([403,404].includes(foreign));
  await click("#logout");
  report.checks.push("real cancellation; no source browser persistence/tools; logout erasure; foreign-device file denial");
  report.local_provider_calls=calls();report.passed=true;save();console.log(JSON.stringify({passed:true,checks:report.checks.length,grounded_answers:3,image_understanding:"unavailable",local_provider_calls:calls()}));
}
main().catch(error=>{report.error=String(error.stack||error);save();console.error(report.error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();if(browser)browser.kill();await stopCore();fs.closeSync(log);});
