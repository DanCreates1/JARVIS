"use strict";

// Real PWA/auth/Core/SQLite/local speech and Ollama; disposable identity and TLS pin only.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {spawn,spawnSync}=require("node:child_process");
const config=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
const dir=config.directory,origin=`https://127.0.0.1:${config.port}`;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={profile:"foreground-voice",checks:[],samples:[]};
const save=()=>fs.writeFileSync(path.join(dir,"browser-results.json"),JSON.stringify(report,null,2));
const calls=()=>{try{return fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").filter(Boolean).length;}catch{return 0;}};
let core,browser,ws,call,evaluate;
const log=fs.openSync(path.join(dir,"core.log"),"a");
async function startCore(){
  core=spawn(config.python,["scripts/foreground-voice-acceptance.py","--serve",dir,"--port",String(config.port)],{windowsHide:true,stdio:["ignore",log,log]});
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
async function record(){
  await evaluate("ui.record.focus()");
  for(const type of ["keyDown","keyUp"])await call("Input.dispatchKeyEvent",{type,key:"Enter",code:"Enter",windowsVirtualKeyCode:13,...(type==="keyDown"?{text:"\r"}:{})});
  await wait("state.voice?.phase==='recording'");
}
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
        await call("Fetch.fulfillRequest",{requestId:message.params.requestId,responseCode:200,responseHeaders:message.params.responseHeaders.filter(h=>!["content-length","content-encoding"].includes(h.name.toLowerCase())),body:Buffer.from(source+"\nObject.assign(globalThis,{state,ui,api,openDb,STORE,chooseConversation,refreshStatus,recordMessage,stopRecording,discardVoice,updateControls});\n").toString("base64")});
      }catch(error){console.error(error);}
    }
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},100000)});ws.send(JSON.stringify({id,method,params}));});
  evaluate=async expression=>{const result=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call("Page.enable");await call("Fetch.enable",{patterns:[{urlPattern:origin+"/app/app.js*",requestStage:"Response"}]});
  await call("Page.navigate",{url:origin+"/app/"});await wait("typeof state!=='undefined'&&document.readyState==='complete'");
  const tickets=JSON.parse(fs.readFileSync(path.join(dir,"tickets.json"),"utf8"));
  await click("#nav-settings");await input("#ticket",JSON.stringify(tickets[0]));await click("#enroll");await ready();await click("#nav-chat");
  assert.equal(await evaluate("document.body.dataset.profile"),"foreground-voice");
  for(let attempt=0;attempt<90;attempt++){
    await evaluate("refreshStatus()");
    if(await evaluate("state.voiceReady"))break;
    await pause(1000);
  }
  assert.equal(await evaluate("state.voiceReady"),true,JSON.stringify(await evaluate("(async()=> (await(await api('/client/voice')).json()))()")));
  assert.equal(await evaluate("state.attachmentsAllowed"),false);
  assert.equal(await evaluate("(async()=> (await(await api('/client/conversations')).json()).conversations.length)()"),0);
  const fixture=fs.readFileSync(path.join(dir,"fixture.pcm")).toString("base64");
  await evaluate(`(()=>{
    window.voiceEvidence={permissionCalls:0};
    navigator.mediaDevices.getUserMedia=async()=>{
      voiceEvidence.permissionCalls++;
      const context=new AudioContext({sampleRate:48000}),destination=context.createMediaStreamDestination();
      const raw=Uint8Array.from(atob(${JSON.stringify(fixture)}),c=>c.charCodeAt(0));
      // Half-second silence at each end models deliberate speech after Record is ready.
      const view=new DataView(raw.buffer),buffer=context.createBuffer(1,raw.length/2+16000,16000),samples=buffer.getChannelData(0);
      for(let i=0;i<raw.length/2;i++)samples[i+8000]=view.getInt16(i*2,true)/32768;
      const source=context.createBufferSource();source.buffer=buffer;source.connect(destination);
      voiceEvidence.generator=context;voiceEvidence.stream=destination.stream;
      voiceEvidence.source=source;voiceEvidence.duration=buffer.duration;
      await context.resume();return destination.stream;
    };
  })()`);
  assert.equal(await evaluate("voiceEvidence.permissionCalls"),0);
  await record();
  await evaluate("voiceEvidence.source.start()");
  await pause(await evaluate("voiceEvidence.duration*1000+500"));
  const started=Date.now();await click("#stop-recording");
  await wait("!state.voice&&ui.message.value.trim()",90000);
  const draft=await evaluate("ui.message.value");
  assert.equal(draft.toLowerCase().replace(/[.!?]/g,"").trim(),"the quick brown fox jumps over the lazy dog");
  assert.equal(await evaluate("voiceEvidence.stream.getTracks().every(t=>t.readyState==='ended')"),true);
  assert.equal(await evaluate("(async()=> (await(await api('/client/conversations')).json()).conversations.length)()"),0);
  assert.equal(calls(),0);
  const persistent=await evaluate("(async()=>{const db=await openDb();const rows=await new Promise((resolve,reject)=>{const r=db.transaction(STORE).objectStore(STORE).getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});db.close();return JSON.stringify({rows,local:{...localStorage},session:{...sessionStorage},caches:await Promise.all((await caches.keys()).map(async n=>(await(await caches.open(n)).keys()).map(r=>r.url)))});})()");
  assert.equal(persistent.includes(draft),false);
  report.transcription_ms=Date.now()-started;
  report.checks.push("real browser worklet -> authenticated PCM upload -> local Silero/faster-whisper -> editable draft; tracks stopped; no pre-Send conversation/model/browser persistence");
  // Edit deliberately before Send. Deterministic clock provides a trustworthy text receipt.
  const reviewed="What is the time?";
  const first=await send(reviewed,"reviewed-voice-clock");
  assert.match(first.reply,/\d{4}-\d\d-\d\dT/);assert.equal(calls(),0);
  const replay=await evaluate(`(async()=>{const r=await api('/client/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:${JSON.stringify(first.request_id)},subscription_id:state.subscription,conversation_id:null,message:${JSON.stringify(reviewed)}})});return r.json();})()`);
  assert.equal(replay.status,"completed");assert.equal(replay.reply,first.reply);assert.equal(calls(),0);
  const text=await send("Reply briefly with a greeting.","typed-local-model");
  assert.ok(text.reply.trim());assert.equal(calls(),1);
  report.checks.push("explicit Send and immutable replay; deterministic text reply plus actual installed local model; no automatic audio output");
  await evaluate("voiceEvidence.generator.close();ui.message.value='';updateControls()");
  await record();
  await click("#discard-recording");assert.equal(await evaluate("state.voice"),null);
  assert.equal(await evaluate("voiceEvidence.stream.getTracks().every(t=>t.readyState==='ended')"),true);
  await evaluate("voiceEvidence.generator.close()");
  const conversation=await evaluate("state.conversation");
  await stopCore();await startCore();await click("#nav-settings");await click("#connect");await ready();await click("#nav-chat");
  await evaluate(`chooseConversation(${JSON.stringify(conversation)})`);await ready();
  assert.equal(calls(),1);assert.equal(await evaluate("state.voice"),null);
  // Kill only disposable fixture control; text remains available with no capture restart.
  fs.writeFileSync(path.join(dir,"core","voice-settings.json"),JSON.stringify({version:1,devices:{},control:{enabled:false}}));
  await evaluate("refreshStatus()");assert.equal(await evaluate("state.voiceReady"),false);
  const fallback=await send("What is the time?","typed-after-kill");assert.match(fallback.reply,/\d{4}-\d\d-\d\dT/);
  assert.equal(calls(),1);assert.equal(await evaluate("voiceEvidence.permissionCalls"),2);
  report.checks.push("Discard closes tracks; restart restores history without capture/replay; software kill disables speech while typed Send works");
  await click("#nav-settings");await click("#logout");await wait("!state.hasIdentity&&!state.csrf");
  assert.equal(await evaluate("ui.log.textContent+ui.message.value"),"");
  report.checks.push("logout erases private display and speech state; synthetic Windows evidence only");
  report.passed=true;save();console.log(JSON.stringify({passed:true,checks:report.checks.length,local_model_calls:calls(),transcription_ms:report.transcription_ms}));

}
main().catch(error=>{report.error=String(error.stack||error);save();console.error(report.error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();if(browser)browser.kill();await stopCore();fs.closeSync(log);});
