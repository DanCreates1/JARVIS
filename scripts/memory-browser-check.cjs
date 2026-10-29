"use strict";

// Real PWA/auth/Core/SQLite/Ollama; disposable synthetic identities, files and TLS pin only.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path");
const {spawn,spawnSync}=require("node:child_process");
const config=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
const dir=config.directory,origin=`https://127.0.0.1:${config.port}`;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={profile:"private-memory",checks:[],samples:[]};
const save=()=>fs.writeFileSync(path.join(dir,"browser-results.json"),JSON.stringify(report,null,2));
const calls=()=>{try{return fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").filter(Boolean).length;}catch{return 0;}};
let core,browser,ws,call,evaluate;
const log=fs.openSync(path.join(dir,"core.log"),"a");
async function startCore(){
  core=spawn(config.python,["scripts/memory-acceptance.py","--serve",dir,"--port",String(config.port)],{windowsHide:true,stdio:["ignore",log,log]});
  for(let i=0;i<200;i++){
    if(core.exitCode!==null)throw Error("Synthetic Core exited; inspect ignored core.log");
    const probe=spawnSync(config.python,["-c",`import socket;s=socket.create_connection(('127.0.0.1',${config.port}),.1);s.close()`],{windowsHide:true,stdio:"ignore"});
    if(probe.status===0&&fs.existsSync(path.join(dir,"seeded")))return;
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
  });
  call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject,timer:setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},100000)});ws.send(JSON.stringify({id,method,params}));});
  evaluate=async expression=>{const result=await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await call("Page.enable");
  await call("Page.handleJavaScriptDialog",{accept:true}).catch(()=>{});
  ws.addEventListener("message",event=>{const message=JSON.parse(event.data);if(message.method==="Page.javascriptDialogOpening")call("Page.handleJavaScriptDialog",{accept:true});});
  await call("Page.navigate",{url:origin+"/app/#/settings"});
  await wait("document.querySelector('#memory-link')?.hidden===false");
  await click("#memory-link");await wait("document.querySelector('#inspect')&&document.readyState==='complete'");
  assert.equal(await evaluate("document.querySelector('#items').textContent"),"");
  await click("#inspect");await wait("document.querySelector('#items button')&&document.querySelector('main').getAttribute('aria-busy')!=='true'");
  assert.match(await evaluate("document.querySelector('#items').textContent"),/candidate/);
  await click("#items button");await wait("JSON.parse(document.querySelector('#detail').textContent||'null')?.state==='candidate'&&document.querySelector('main').getAttribute('aria-busy')!=='true'");
  const originalId=await evaluate("JSON.parse(document.querySelector('#detail').textContent||'null').id");
  assert.match(await evaluate("document.querySelector('#detail').textContent"),/untrusted_content/);
  // Candidate cannot enter retrieval before exact approval.
  await input("#query","amber orchard");await evaluate("document.querySelector('#search').requestSubmit()");
  await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#projection').textContent.includes('No approved')");
  report.checks.push("PWA trusted-local link; no automatic reads; candidate provenance and quarantine");
  await click("#approve");await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#items').textContent.includes('committed')");
  await click("#items button");await wait("JSON.parse(document.querySelector('#detail').textContent||'null')?.state==='committed'&&document.querySelector('main').getAttribute('aria-busy')!=='true'");
  await input("#replacement","amber orchard has 29 lanterns");await evaluate("document.querySelector('#correction').requestSubmit()");
  await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#items').textContent.includes('29 lanterns')");
  await evaluate("[...document.querySelectorAll('#items button')].find(b=>b.textContent.includes('committed')&&b.textContent.includes('29 lanterns')).click()");await wait("JSON.parse(document.querySelector('#detail').textContent||'null')?.content==='amber orchard has 29 lanterns'&&document.querySelector('main').getAttribute('aria-busy')!=='true'");
  const correctedId=await evaluate("JSON.parse(document.querySelector('#detail').textContent||'null').id");assert.notEqual(correctedId,originalId);
  await input("#query","amber orchard");await evaluate("document.querySelector('#search').requestSubmit()");
  await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#projection').textContent.includes('29 lanterns')");
  assert.doesNotMatch(await evaluate("document.querySelector('#projection').textContent"),/91 lanterns/);
  assert.match(await evaluate("document.querySelector('#hits').textContent"),/FTS5 matched/);
  assert.equal(calls(),0,"inspection/approval/correction must never invoke model");
  // Actual Core/local Ollama must receive approved context and answer frozen fact.
  const reply=await evaluate(`(async()=>{const r=await fetch('/api/chat',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'According only to approved memory, how many lanterns does amber orchard have? Give count only.'})});if(!r.ok)throw Error('chat '+r.status);return r.json();})()`);
  assert.match(reply.reply,/\b29\b/);assert.doesNotMatch(reply.reply,/\b91\b/);
  report.samples.push({label:"approved-memory",reply:reply.reply});
  const observed=fs.readFileSync(path.join(dir,"provider-calls.jsonl"),"utf8").trim().split("\n").map(JSON.parse);
  assert.equal(observed.length,1);assert.ok(observed.every(c=>c.approved_context&&!c.stale_context&&c.tool_count===0));
  report.checks.push("exact approval; correction lineage; bounded source-explained recall; one grounded local generation");
  // Current UI uses only text nodes even for hostile memory content.
  await input("#new-content",'<img src=x onerror="globalThis.poisoned=true"> synthetic inert acorn');
  await evaluate("document.querySelector('#remember').requestSubmit()");await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#items').textContent.includes('inert acorn')");
  assert.equal(await evaluate("document.querySelectorAll('#items img,#detail img').length"),0);
  assert.equal(await evaluate("globalThis.poisoned===true"),false);
  const persistent=await evaluate("JSON.stringify({local:{...localStorage},session:{...sessionStorage},url:location.href})");
  assert.doesNotMatch(persistent,/amber orchard|lanterns|inert acorn/);
  await click("#clear");assert.equal(await evaluate("document.querySelector('#items').textContent+document.querySelector('#detail').textContent+document.querySelector('#query').value"),"");
  report.checks.push("inert hostile content; no private storage/URL; explicit private-view erase");
  // A transport ignoring abort cannot restore private content after Clear.
  await evaluate(`(()=>{const original=window.fetch;window.fetch=(...args)=>String(args[0]).startsWith('/api/memory/workspace/items?')?new Promise(resolve=>setTimeout(()=>resolve(new Response(JSON.stringify({items:[{id:'stale',category:'semantic',state:'committed',content:'stale private sentinel'}],has_more:false}),{status:200})),150)):original(...args);globalThis.restoreFixtureFetch=()=>{window.fetch=original;};})()`);
  await click("#inspect");await click("#clear");await pause(250);
  assert.equal(await evaluate("document.querySelector('#items').textContent"),"");
  await evaluate("restoreFixtureFetch()");
  report.checks.push("late response ignored after explicit abort and private-view erase");
  await stopCore();await startCore();
  await call("Page.reload");await wait("document.querySelector('#inspect')&&document.readyState==='complete'");
  await click("#inspect");await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#items').textContent.includes('29 lanterns')");
  // Forget every synthetic row, including the separately inspectable corrected version.
  while(await evaluate("document.querySelectorAll('#items button').length>0")){
    await click("#items button");await wait("JSON.parse(document.querySelector('#detail').textContent||'null')&&document.querySelector('main').getAttribute('aria-busy')!=='true'");await click("#forget");await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&JSON.parse(document.querySelector('#detail').textContent||'null')===null");
  }
  await stopCore();await startCore();await call("Page.reload");await wait("document.querySelector('#inspect')&&document.readyState==='complete'");
  await click("#inspect");await wait("document.querySelector('main').getAttribute('aria-busy')!=='true'&&document.querySelector('#items').textContent.includes('No items')");
  // Remote headers and cookies do not grant local memory authority.
  const denied=await evaluate("(async()=>{return (await fetch('/api/memory/workspace/items',{headers:{Authorization:'Bearer synthetic'}})).status;})()");assert.equal(denied,403);
  const cacheKeys=await evaluate("(async()=>{return (await Promise.all((await caches.keys()).map(async n=>(await(await caches.open(n)).keys()).map(r=>r.url)))).flat();})()");
  assert.ok(cacheKeys.every(url=>!url.includes('/memory')&&!url.includes('/api/')));
  report.checks.push("actual Core crash/restart; complete explicit forget; restart absence; remote denial; cache exclusion");
  await call("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert.ok(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"));
  report.checks.push("390px desktop-emulated layout without horizontal overflow; physical phone unverified");
  await evaluate("document.querySelector('#clear').focus()");
  await call("Input.dispatchKeyEvent",{type:"keyDown",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
  await call("Input.dispatchKeyEvent",{type:"keyUp",key:"Tab",code:"Tab",windowsVirtualKeyCode:9});
  assert.equal(await evaluate("document.activeElement.id"),"state");
  const ax=await call("Accessibility.getFullAXTree");
  for(const name of ["State","Category"])assert.ok(ax.nodes.some(n=>n.role?.value==='combobox'&&n.name?.value===name));
  assert.equal(await evaluate("getComputedStyle(document.querySelector('header a')).color"),'rgb(186, 230, 253)');
  for(const width of [320,1280]){
    await call("Emulation.setDeviceMetricsOverride",{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate("document.documentElement.style.fontSize='200%'");
    assert.ok(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"));
  }
  report.checks.push("named form controls and keyboard order; high-contrast links; 200-percent font reflow at 320/1280px");
  report.local_provider_calls=calls();report.passed=true;save();console.log(JSON.stringify({passed:true,checks:report.checks.length,grounded_answers:1,local_provider_calls:calls()}));
}
main().catch(error=>{report.error=String(error.stack||error);save();console.error(report.error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();if(browser)browser.kill();await stopCore();fs.closeSync(log);});
