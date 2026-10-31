"use strict";

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const script = readFileSync(path.join(__dirname, "../../src/jarvis/pwa/app.js"), "utf8");
const EMPTY = "Connect JARVIS to see Garmin data.";

for(const profile of ["prototype-text","daily-text","private-garmin","private-files","private-memory","public-research","foreground-voice"]){
  test(`Phase 8 ${profile} keeps Garmin behind explicit capability and refresh`,async()=>{
    const h=harness(new Map(),"",profile);await h.ready;h.activate();h.run("selectView('garmin')");
    assert.equal(h.requests.length,0);
    assert.equal(h.run("navigation.view"),profile==="private-garmin"?"garmin":"chat");
    const read=h.run("refreshGarmin(true)");
    if(profile==="private-garmin"){
      await h.waitForRequests(1);h.respond(h.requests[0],h.summary(123456));
    }
    await read;
    assert.equal(h.requests.length,profile==="private-garmin"?1:0);
    assert.equal(h.storage.size,0);assert.equal(h.records.size,0);
  });
}

for(const profile of ["prototype-text","daily-text","private-garmin","private-files","private-memory","public-research","foreground-voice"]){
  test(`Phase 9 ${profile} keeps file and vision capability explicit`,async()=>{
    const h=harness(new Map(),"",profile);await h.ready;h.activate();
    for(const configured of [false,true]){
      const count=h.requests.length+1,read=h.run("refreshStatus()");await h.waitForRequests(count);
      h.respond(h.requests.at(-1),{attachments:{available:true,vision_configured:configured},voice:{available:true},device:{},session:{}});await read;
      assert.equal(h.run("state.attachmentsAllowed"),profile==="private-files");
      assert.equal(h.run("state.voiceReady"),profile==="foreground-voice");
      assert.match(h.get("#file-capabilities").textContent,profile!=="private-files"?/File processing unavailable/:configured?/each request checks availability/:/Image understanding unavailable/);
    }
    assert.equal(h.storage.size,0);assert.equal(h.records.size,0);
  });
}

test("Phase 8 health-scope denial clears previous values immediately",async()=>{
  const h=harness();await h.ready;h.activate();h.context.data=h.summary(123456);h.run("renderGarmin(data)");
  const read=h.run("refreshGarmin(true)");await h.waitForRequests(1);h.respond(h.requests[0],{detail:"denied"},403);await read;
  assert.equal(h.get("#garmin-metrics").children.length,0);assert.equal(h.get("#garmin-activities").children.length,0);
  assert.equal(h.run("state.healthAllowed"),false);assert.equal(h.get("#refresh-garmin").disabled,true);
  assert.match(h.get("#garmin-state").textContent,/access denied/);
});

test("Phase 8 partial availability distinguishes empty activities from unavailable",async()=>{
  const h=harness();await h.ready;h.activate();
  for(const available of [false,true]){
    h.context.data={...h.summary(null),activities:[],activities_available:available};h.run("renderGarmin(data)");
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent,"Unavailable");
    assert.equal(h.get("#garmin-activities").children[0].textContent,available?"No recent activities.":"Recent activities unavailable.");
  }
});

test("Phase 8 recent fetch becomes stale across local-day rollover without a read",async()=>{
  const h=harness();await h.ready;h.activate();
  h.clock.now=new Date(2026,9,7,23,59,50).getTime();h.context.data={...h.summary(123456),refreshed_at:new Date(h.clock.now).toISOString()};h.run("renderGarmin(data)");
  assert.doesNotMatch(h.get("#garmin-state").textContent,/Stale/);
  h.clock.now+=20000;h.run("renderGarminStatus()");
  assert.match(h.get("#garmin-state").textContent,/Stale/);assert.equal(h.requests.length,0);
});

test("Phase 8 Garmin rendering never enters public chat request or browser storage",async()=>{
  const h=harness(new Map(),"","private-garmin");await h.ready;h.activate();h.context.data=h.summary(123456);h.run("renderGarmin(data);state.subscription='owned'");
  h.get("#message").value="Public synthetic rewrite";const send=h.run("sendMessage({preventDefault(){}})");await h.waitForRequests(1);
  const body=h.requests[0].options.body,payload=JSON.parse(body);
  assert.equal(body.includes("123456"),false);assert.deepEqual(Object.keys(payload).sort(),["conversation_id","message","request_id","subscription_id"]);
  assert.equal(JSON.stringify([...h.records]).includes("123456"),false);assert.equal(JSON.stringify([...h.storage]).includes("123456"),false);
  h.respond(h.requests[0],{request_id:payload.request_id,status:"completed",reply:"Public synthetic reply"});await send;
});

function descendants(node){return [node,...node.children.flatMap(descendants)];}
test("F15 old task-list body cannot reappear after offline then successful reconnect",async()=>{
  const h=harness();await h.ready;h.activate();const stale=h.run("refreshTasks()");await h.waitForRequests(1);
  h.requests[0].pending.resolve({ok:true,status:200,json:()=>new Promise(resolve=>{h.context.finishTaskBody=resolve;})});
  for(let i=0;i<20&&!h.context.finishTaskBody;i++)await Promise.resolve();
  h.windowEvents.offline();h.activate();h.context.finishTaskBody([{id:"obsolete",status:"running"}]);await stale;
  assert.equal(h.get("#tasks").children.length,0);assert.equal(h.run("state.tasksBusy"),false);
});
test("F15 asynchronous parser failure restores accepted draft without overwriting new typing",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.subscription='subscription:owned'");h.get("#message").value="original attachment question";
  const send=h.run("sendMessage({preventDefault(){}})");await h.waitForRequests(1);const payload=JSON.parse(h.requests[0].options.body);h.respond(h.requests[0],{request_id:payload.request_id,conversation_id:"owned",status:"running"});await send;
  assert.equal(h.get("#message").value,"");h.context.result={request_id:payload.request_id,conversation_id:"owned",status:"failed",error:{code:"attachment_processing_failed"}};h.run("applyChatResult(result)");
  assert.equal(h.get("#message").value,"original attachment question");
  h.get("#message").value="new unsent text";h.run("state.chatAnnounced.clear();state.chatDrafts.set(result.request_id,'old');applyChatResult(result)");assert.equal(h.get("#message").value,"new unsent text");
});
test("F15 IME and multiline editing cannot submit accidentally; explicit shortcut sends once",async()=>{
  const h=harness();await h.ready;h.activate();h.get("#message").value="multiline\n日本語";h.run("state.subscription='owned'");
  h.get("#message").listeners.compositionstart[0]();await h.run("sendMessage({preventDefault(){}})");assert.equal(h.requests.length,0);
  let submitted=0;h.get("#chat").requestSubmit=()=>submitted++;
  const key=extra=>({key:"Enter",preventDefault(){},...extra});
  h.get("#message").listeners.keydown[0](key({ctrlKey:true,isComposing:true}));h.get("#message").listeners.compositionend[0]();
  h.get("#message").listeners.keydown[0](key({}));h.get("#message").listeners.keydown[0](key({ctrlKey:true,repeat:true}));assert.equal(submitted,0);
  h.get("#message").listeners.keydown[0](key({ctrlKey:true}));assert.equal(submitted,1);
});
test("F15 library metadata conflict preserves edit and sends no implicit retry",async()=>{
  const h=harness();await h.ready;h.activate();h.context.saved={id:"owned",title:"old",revision:2,pinned:false,archived:false};
  h.run("renderLibrary({conversations:[saved],revision:9,has_more:true,next_offset:20})");
  const form=h.get("#library").children[0].children[3];form.children[1].value="unsaved edit";
  const change=h.run("changeConversationMetadata(saved,{title:'unsaved edit'})");await h.waitForRequests(1);
  assert.equal(JSON.parse(h.requests[0].options.body).revision,2);h.respond(h.requests[0],{detail:"changed"},409);await change;
  assert.equal(form.children[1].value,"unsaved edit");assert.match(h.get("#library-state").textContent,/Concurrent/);assert.equal(h.requests.length,1);
});
test("F15 ready reuse remains conversation-bound and explicit Send fingerprints immutable IDs",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.conversation='owned';state.subscription='subscription:owned';renderAttachmentMetadata({conversation_id:'owned',available:true,attachments:[{id:'file',filename:'note.txt',status:'ready',request_ids:[]}],has_more:false})");
  h.get("#conversation-attachments").children[0].reuse.listeners.click[0]();assert.equal(h.run("state.reuseSelected.has('file')"),true);assert.equal(h.requests.length,0);
  h.get("#message").value="Reuse deliberately";const send=h.run("sendMessage({preventDefault(){}})");await h.waitForRequests(1);
  const payload=JSON.parse(h.requests[0].options.body);assert.deepEqual(payload.attachment_ids,["file"]);assert.equal(payload.conversation_id,"owned");
  h.respond(h.requests[0],{request_id:payload.request_id,conversation_id:"owned",status:"failed",error:{code:"attachment_unavailable"}});await send;
  assert.equal(h.get("#message").value,"Reuse deliberately");assert.match(h.get("#chat-status").textContent,/expired or unavailable/);
});
for(const ending of ["selection","navigation","offline","session","logout"]){
  test(`F15 attachment metadata and timeline reject stale body after ${ending}`,async()=>{
    const h=harness();await h.ready;h.activate();h.run("state.conversation='owned';state.taskSelected='task:a'");
    const attachment=h.run("loadAttachmentMetadata()"),timeline=h.run("loadTaskTimeline()");await h.waitForRequests(2);
    if(ending==="selection")h.run("state.conversation='other';state.taskSelected='task:b'");
    if(ending==="navigation")h.run("selectView('settings')");
    if(ending==="offline")h.windowEvents.offline();
    if(ending==="session")h.run("invalidateSession()");
    if(ending==="logout")await h.run("logout()");
    h.respond(h.requests[0],{conversation_id:"owned",attachments:[{id:"file",filename:"stale.txt",status:"ready"}]});h.respond(h.requests[1],{task_id:"task:a",events:[{event_type:"stale-private"}]});
    await Promise.all([attachment,timeline]);assert.equal(h.get("#conversation-attachments").children.length,0);assert.equal(h.get("#task-events").children.length,0);
  });
}
test("F15 timeline pagination replaces bounded page and selected task survives filter refresh",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.taskSelected='task:a';renderTaskTimeline({task_id:'task:a',events:[{event_type:'node_waiting_approval',task_status:'waiting_approval',explanation:'Core approval required'}],has_more:true,next_before:80})");
  const more=h.run("loadTaskTimeline({before:80})");await h.waitForRequests(1);assert.match(h.requests[0].url,/before=80/);
  h.respond(h.requests[0],{task_id:"task:a",events:[{event_type:"task_created",task_status:"proposed"}],has_more:false});await more;assert.equal(h.get("#task-events").children.length,1);assert.equal(h.get("#task-events-latest").hidden,false);
  h.get("#task-filter").value="failed";h.get("#task-sort").value="oldest";const refresh=h.run("resetTaskList()");await h.waitForRequests(2);assert.match(h.requests[1].url,/status=failed&sort=oldest/);h.respond(h.requests[1],[]);await h.waitForRequests(3);h.respond(h.requests[2],{detail:"gone"},404);await refresh;
  assert.equal(h.run("state.taskSelected"),"task:a");assert.equal(h.get("#cancel-task").disabled,true);
});
test("F15 Markdown subset renders structure, citations, code and safe explicit links",()=>{
  const h=harness();h.context.URL=URL;
  h.context.reply="# Heading\n\nParagraph **bold** and *emphasis* [source:source-1](<https://example.com/evidence>).\n- First\n- Second\n> Quote\n\n| A | B |\n| --- | --- |\n| one | two |\n```js\nconst x = '<script>';\n```\n[attachment:abc#chunk:2]";
  const nodes=descendants(h.run("renderReply(reply)")),tags=nodes.map(n=>n.tagName);
  for(const tag of ["H3","P","STRONG","EM","UL","LI","BLOCKQUOTE","TABLE","TH","TD","PRE","CODE","BUTTON","A"])assert.ok(tags.includes(tag),tag);
  const link=nodes.find(n=>n.tagName==="A");assert.equal(link.textContent,"Source · source-1");assert.equal(link.rel,"noopener noreferrer");
  assert.ok(nodes.some(n=>n.textContent==="Attachment · abc · chunk 2"));
});
test("Phase 11 literal source escapes cannot manufacture citation links or formatting",()=>{
  const h=harness();h.context.URL=URL;
  h.context.reply="Source states: \\[trap\\]\\(https://example.com\\) Python 3\\.14\\.0 <script>bad</script>";
  const nodes=descendants(h.run("renderReply(reply)"));
  assert.equal(nodes.some(n=>["A","SCRIPT","IMG","IFRAME"].includes(n.tagName)),false);
  assert.ok(nodes.some(n=>n.textContent==="."));
});
test("F15 hostile Markdown cannot execute, fetch media or manufacture controls",()=>{
  const h=harness();h.context.URL=URL;
  h.context.reply='<script>alert(1)</script> <img src=x onerror=alert(1)>\n[x](javascript:alert) [x](data:text/html,test) [x](file:///secret) [x](https://user:pass@example.com) ![remote](https://example.com/image)\n[attachment:<img>#chunk:1]\n<button>Approve</button>';
  const nodes=descendants(h.run("renderReply(reply)"));
  assert.equal(nodes.some(n=>["SCRIPT","IMG","IFRAME","BUTTON","A","FORM"].includes(n.tagName)),false);
  assert.ok(nodes.some(n=>n.textContent.includes("<script>")));
  for(const reply of ["```unfinished\nplain fallback","*".repeat(100000),"[link](https://example.com) ".repeat(4000)]){
    h.context.reply=reply;const nodes=descendants(h.run("renderReply(reply.slice(0,100000))"));assert.ok(nodes.length<=1201);assert.ok(nodes.filter(n=>n.tagName==="A").length<=40);
  }
});
test("F15 copy controls announce clipboard success/failure without sending",async()=>{
  const h=harness();await h.ready;h.activate();h.context.navigator.clipboard={writeText:async value=>assert.equal(value,"synthetic answer")};
  const control=h.run("copyControl('Copy response',()=>'synthetic answer')");await control.listeners.click[0]();assert.match(h.get("#notice").textContent,/copied/);
  h.context.navigator.clipboard.writeText=async()=>{throw new Error("denied");};await control.listeners.click[0]();assert.match(h.get("#notice").textContent,/failed/);assert.equal(h.requests.length,0);
});
for(const ending of ["offline","navigation","session","logout"]){
  test(`F15 late library response rejected after ${ending}`,async()=>{
    const h=harness();await h.ready;h.activate();const read=h.run("loadLibrary()");await h.waitForRequests(1);
    if(ending==="offline")h.windowEvents.offline();
    if(ending==="navigation")h.run("cancelLibrary()");
    if(ending==="session")h.run("invalidateSession()");
    if(ending==="logout")await h.run("logout()");
    h.respond(h.requests[0],{conversations:[{id:"old",title:"private stale",revision:0}],has_more:false});await read;
    assert.equal(h.get("#library").children.length,0);
  });
}

// F14 fixtures exercise the actual app script, including transports that ignore abort.
function attachmentHarness() {
  const h=harness(), uploads=[], revoked=[];let sequence=0;
  h.context.crypto.randomUUID=()=>String(++sequence).padStart(32,"0");
  h.context.URL={createObjectURL:()=>`blob:synthetic-${sequence}`,revokeObjectURL:url=>revoked.push(url)};
  h.context.XMLHttpRequest=class {
    constructor(){this.upload={};this.headers={};uploads.push(this);}
    open(method,url){this.method=method;this.url=url;}
    setRequestHeader(key,value){this.headers[key]=value;}
    send(file){this.file=file;}
    abort(){this.aborted=true;this.onabort?.();}
    respond(status=201){this.status=status;this.response={id:this.url.split("/").pop(),status:"staged"};this.onload();}
  };
  const file=(name="notes.txt",size=30)=>({name,size,slice:()=>({text:async()=>"<script>untrusted text</script>"})});
  h.activate();h.run("state.attachmentsAllowed=true;updateControls()");
  return {...h,uploads,revoked,file};
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element() {
  return {
    children: [], textContent: "", disabled: false, value: "", dataset: {}, classList: { add() {}, remove() {} },
    attributes: {}, scrollTop: 0, scrollHeight: 0, clientHeight: 0, hidden: false,
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    focus() { this.focused = true; },
    contains(node) { return this.children.includes(node); },
    listeners: {},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    querySelector(selector) { const id = selector.match(/data-request="([^"]+)"/)?.[1]; return this.children.find(item => item.dataset.request === id) || null; },
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); },
  };
}

function harness(records = new Map(), hash = "", profile = "standard") {
  const nodes = new Map(), requests = [], windowEvents = {}, timers = [], storage = new Map();
  const location = { origin: "https://synthetic.test", hash }, historyEntries = [{ state: null, hash }];
  let historyIndex = 0;
  const history = {
    pushState(state, _, hash) { historyEntries.splice(++historyIndex); historyEntries.push({ state, hash }); location.hash = hash; },
    replaceState(state, _, hash) { historyEntries[historyIndex] = { state, hash }; location.hash = hash; },
    go(delta) {
      historyIndex += delta; location.hash = historyEntries[historyIndex].hash;
      windowEvents.popstate(); windowEvents.hashchange();
    },
  };
  const clock = { now: Date.parse("2026-10-07T12:00:00Z") };
  class FakeDate extends Date {
    constructor(...args) { super(...(args.length ? args : [clock.now])); }
    static now() { return clock.now; }
  }
  const get = (selector) => {
    if (!nodes.has(selector)) {
      const node = element(); node.id = selector.slice(1);
      node.focus = () => { node.focused = true; context.document.activeElement = node; };
      if (selector.startsWith("#nav-")) node.textContent = selector.slice(5).replace(/^./, letter => letter.toUpperCase());
      nodes.set(selector, node);
    }
    return nodes.get(selector);
  };
  let nextMarkerCommit;
  const storageRequest = (result) => {
    const request = { result };
    queueMicrotask(() => request.onsuccess?.());
    return request;
  };
  const database = {
    close() {},
    transaction() {
      const tx = {};
      const operation = (result, mutation = () => {}, marker = false) => {
        const request = storageRequest(result), control = marker ? nextMarkerCommit : null;
        if (marker) nextMarkerCommit = null;
        const finish = error => {
          if (error) { tx.error = error; tx.onabort?.(); return; }
          mutation(); tx.oncomplete?.();
        };
        if (control) { control.commit = () => finish(); control.fail = () => finish(new Error("Synthetic IndexedDB transaction abort")); }
        else queueMicrotask(() => queueMicrotask(() => finish()));
        return request;
      };
      tx.objectStore = () => ({
        get: key => operation(records.get(key)),
        clear: () => operation(undefined, () => records.clear()),
        put: (value, key) => operation(value, () => records.set(key, value), key === "chat-request"),
        delete: key => operation(undefined, () => records.delete(key)),
      });
      return tx;
    },
  };
  const listen = (name, callback) => { const previous = windowEvents[name]; windowEvents[name] = (...args) => { previous?.(...args); callback(...args); }; };
  const context = vm.createContext({
    AbortController, DOMException, TextEncoder, URLSearchParams, Date: FakeDate, Promise, CSS: { escape: value => value },
    crypto: { randomUUID: () => "synthetic-request" },
    document: { body: {dataset: {profile}}, querySelector: get, createElement: tag => Object.assign(element(),{tagName:tag.toUpperCase()}), addEventListener: listen },
    window: { location, history, scrollTo() {}, addEventListener: listen },
    navigator: { onLine: true },
    indexedDB: { open: () => storageRequest(database) },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    caches: { keys: async () => [] },
    setTimeout: (callback, delay) => { const timer = { callback, delay, active: true }; timers.push(timer); return timer; },
    clearTimeout: timer => { if (timer) timer.active = false; },
    fetch: (url, options) => {
      const pending = deferred();
      requests.push({ url, options, pending });
      // Deliberately ignore abort: transport/body work can complete after cancellation.
      return pending.promise;
    },
  });
  const run = (code) => vm.runInContext(code, context);
  const ready = (async () => { for (let turn = 0; turn < 20; turn++) await Promise.resolve(); })();
  const activate = (session = "synthetic-session") => run(`state.csrf=${JSON.stringify(session)};state.deviceId='synthetic-device';state.hasIdentity=true;state.healthAllowed=true;state.historyReady=true;setConnected(true);`);
  const summary = (steps) => ({
    date: "2026-10-07", refreshed_at: "2026-10-07T12:00:00Z", steps,
    resting_heart_rate: null, sleep_minutes: null, stress: null, body_battery: null,
    activities: [{ name: "Activity", type: "walking", started: "2026-10-07T12:00:00" }],
  });
  const respond = (request, body, status = 200) => request.pending.resolve({ ok: status < 400, status, json: async () => body });
  vm.runInContext(script, context);
  const setIdentity = (value) => { records.set("device", value); };
  const holdMarkerCommit = () => { const control = {}; nextMarkerCommit = control; return control; };
  const waitForRequests = async (count) => {
    for (let turn = 0; turn < 50 && requests.length < count; turn++) {
      await Promise.resolve();
      // Existing transport scenarios advance the successful-poll pacing clock.
      const pacing = timers.find(item => item.active && item.delay === 500);
      if (pacing) { pacing.active = false; pacing.callback(); }
    }
    assert.equal(requests.length, count);
  };
  const runTimer = (predicate) => {
    const timer = timers.find(item => item.active && predicate(item.delay));
    assert.ok(timer, "Expected active timer");
    timer.active = false;
    timer.callback();
  };
  const fakeEnrollmentCrypto = () => {
    context.window.indexedDB = context.indexedDB;
    context.btoa = text => Buffer.from(text, "binary").toString("base64");
    context.crypto.subtle = {
      generateKey: async () => ({ privateKey: "synthetic-private-key", publicKey: "synthetic-public-key" }),
      exportKey: async () => new Uint8Array(32),
      sign: async () => new Uint8Array(64),
    };
  };
  return { run, ready, activate, get, requests, summary, respond, windowEvents, context, clock, setIdentity, waitForRequests, runTimer, storage, records, holdMarkerCommit, fakeEnrollmentCrypto, history, historyEntries, location };
}

test("F14 bounded uploads show progress and safe text/photo/PDF previews without Send",async()=>{
  const h=attachmentHarness();await h.ready;
  h.context.files=[h.file(),h.file("photo.png"),h.file("paper.pdf")];
  await h.run("selectAttachments(files)");await Promise.resolve();
  assert.equal(h.uploads.length,3);assert.equal(h.requests.length,0);
  const upload=h.uploads[0];assert.equal(upload.headers["X-Jarvis-CSRF"],"synthetic-session");assert.equal(upload.withCredentials,true);
  h.context.document.activeElement=h.get("#attachments").children[0].children[2];
  upload.upload.onprogress({lengthComputable:true,loaded:10,total:30});assert.equal(h.run("state.attachments[0].progress"),33);
  assert.equal(h.get("#attachments").children[0].children[2].focused,true,"Progress must retain keyboard cancellation focus");
  assert.equal(h.get("#send").disabled,true);
  h.uploads.forEach(item=>item.respond());assert.equal(h.run("state.attachments.every(item=>item.phase==='ready')"),true);
  assert.equal(h.get("#send").disabled,false);assert.equal(h.get("#record-message").disabled,true);
  assert.ok(h.run("state.attachments[0].preview").includes("<script>"));
  assert.equal(h.get("#attachments").children.length,3);
  assert.equal(h.storage.size,0);assert.equal(h.records.size,0);
});

test("F14 invalid sizes/types and four-file bound reject before upload",async()=>{
  const h=attachmentHarness();h.context.files=[h.file("a.exe"),h.file("empty.txt",0),h.file("large.pdf",1048577)];
  await h.run("selectAttachments(files)");assert.equal(h.uploads.length,0);
  h.context.files=Array.from({length:5},(_,i)=>h.file(`file${i}.txt`));await h.run("selectAttachments(files)");assert.equal(h.uploads.length,4);
  assert.match(h.get("#attachment-state").textContent,/Four-file/);
});

for(const exit of ["remove","navigation","offline","hide","pagehide","session","logout"]){
  test(`F14 ${exit} aborts upload, revokes previews and rejects late completion`,async()=>{
    const h=attachmentHarness();h.context.files=[h.file("photo.png")];await h.run("selectAttachments(files)");
    const xhr=h.uploads[0];
    if(exit==="remove")h.run("removeAttachment(state.attachments[0]);updateControls()");
    if(exit==="navigation")h.run("selectView('settings')");
    if(exit==="offline"){h.context.navigator.onLine=false;h.windowEvents.offline();}
    if(exit==="hide"){h.context.document.hidden=true;h.windowEvents.visibilitychange();}
    if(exit==="pagehide")h.windowEvents.pagehide();
    if(exit==="session")h.run("invalidateSession()");
    if(exit==="logout")await h.run("logout()");
    xhr.respond();assert.equal(h.run("state.attachments.length"),0);assert.ok(xhr.aborted);assert.equal(h.revoked.length,1);
    assert.equal(h.get("#attachments").children.length,0);assert.ok(!h.requests.some(item=>item.url.endsWith("/client/chat")));
  });
}

for(const failure of ["timeout","network",403,409,413,422,429,503]){
  test(`F14 upload failure ${failure} keeps draft and requires reselection`,async()=>{
    const h=attachmentHarness();h.context.files=[h.file()];await h.run("selectAttachments(files)");
    h.get("#message").value="keep draft";
    if(failure==="timeout")h.uploads[0].ontimeout();else if(failure==="network")h.uploads[0].onerror();else h.uploads[0].respond(failure);
    assert.equal(h.run("state.attachments[0].phase"),"failed");assert.ok(h.run("state.attachments[0].error"));
    assert.equal(h.get("#message").value,"keep draft");assert.equal(h.get("#send").disabled,true);
  });
}

test("F14 upload expiry disables Send; explicit Send alone hands immutable IDs to Core",async()=>{
  const h=attachmentHarness();h.context.files=[h.file()];await h.run("selectAttachments(files)");h.uploads[0].respond();
  h.runTimer(delay=>delay===600000);assert.equal(h.get("#send").disabled,true);
  h.run("removeAttachment(state.attachments[0])");await h.waitForRequests(1);h.respond(h.requests[0],{});
  await h.run("selectAttachments(files)");h.uploads[1].respond();h.get("#message").value="read notes";h.run("state.subscription='subscription:synthetic'");
  const send=h.run("sendMessage({preventDefault(){}})");await h.waitForRequests(2);
  const body=JSON.parse(h.requests[1].options.body);assert.equal(body.upload_ids.length,1);assert.equal(h.run("state.attachments.length"),0);
  h.respond(h.requests[1],{request_id:body.request_id,conversation_id:"conversation:one",status:"running"},202);await send;
  assert.equal(h.requests.filter(item=>item.options.method==="DELETE").length,1,"Send must not race discard against accepted upload");
});

test("F14 search is body-only, paginates, renders text and leaves pending ownership intact",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.pendingRequest={request_id:'request:owned'};state.subscription='subscription:owned'");
  h.get("#history-query").value="private <query>";const first=h.run("searchHistory()");await h.waitForRequests(1);
  assert.equal(h.requests[0].url,"/api/v1/client/conversations/search");assert.equal(JSON.parse(h.requests[0].options.body).query,"private <query>");
  h.respond(h.requests[0],{results:[{conversation_id:"c",sequence:3,role:"user",excerpt:"<img onerror=attack>"}],has_more:true,next_before:12});await first;
  assert.equal(h.get("#search-results").children[0].children[1].textContent,"<img onerror=attack>");
  assert.equal(h.get("#search-results").children[0].children[0].disabled,true);
  const more=h.run("searchHistory({more:true})");await h.waitForRequests(2);assert.equal(JSON.parse(h.requests[1].options.body).before,12);
  h.respond(h.requests[1],{results:[],has_more:false,next_before:null});await more;
  assert.equal(h.run("state.pendingRequest.request_id"),"request:owned");assert.equal(h.records.size,0);assert.equal(h.storage.size,0);
});

for(const exit of ["query","navigation","offline","session","logout"]){
  test(`F14 stale search result rejected after ${exit}`,async()=>{
    const h=harness();await h.ready;h.activate();h.get("#history-query").value="term";const search=h.run("searchHistory()");await h.waitForRequests(1);
    if(exit==="query")h.run("clearSearch()");if(exit==="navigation")h.run("selectView('garmin')");
    if(exit==="offline"){h.context.navigator.onLine=false;h.windowEvents.offline();}
    if(exit==="session")h.run("invalidateSession()");if(exit==="logout")await h.run("logout()");
    h.respond(h.requests[0],{results:[{conversation_id:"c",sequence:1,excerpt:"stale private text"}],has_more:false});await search;
    assert.equal(h.get("#search-results").children.length,0);assert.equal(h.get("#search-state").textContent,"");
  });
}

test("F14 search empty/error and newer query preserve recovery",async()=>{
  const h=harness();await h.ready;h.activate();await h.run("searchHistory()");assert.match(h.get("#search-state").textContent,/Enter text/);
  h.get("#history-query").value="old";const old=h.run("searchHistory()");await h.waitForRequests(1);
  h.get("#history-query").value="new";const latest=h.run("searchHistory()");await h.waitForRequests(2);
  h.respond(h.requests[1],{results:[],has_more:false});await latest;assert.match(h.get("#search-state").textContent,/No matching/);
  h.respond(h.requests[0],{results:[{excerpt:"old"}],has_more:false});await old;assert.equal(h.get("#search-results").children.length,0);
  const failed=h.run("searchHistory()");await h.waitForRequests(3);h.respond(h.requests[2],{},503);await failed;assert.match(h.get("#search-state").textContent,/Search failed/);
});

test("F14 matching history navigation preserves separate drafts and targets matching page",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.conversation='first'");h.get("#message").value="draft first";
  const choose=h.run("chooseConversation('second',8)");await h.waitForRequests(1);h.respond(h.requests[0],{conversations:[]});await h.waitForRequests(2);
  assert.ok(h.requests[1].url.endsWith("?limit=50&before=9"));h.respond(h.requests[1],{conversation_id:"second",messages:[],requests:[],has_more:false});await choose;
  assert.equal(h.get("#message").value,"");h.get("#message").value="draft second";
  const back=h.run("chooseConversation('first')");await h.waitForRequests(3);h.respond(h.requests[2],{conversations:[]});await h.waitForRequests(4);h.respond(h.requests[3],{conversation_id:"first",messages:[],requests:[],has_more:false});await back;
  assert.equal(h.get("#message").value,"draft first");h.run("invalidateSession()");assert.equal(h.run("state.threadDrafts.size"),0);assert.equal(h.get("#message").value,"");
});

test("F14 task progress/failure is Core-owned; cancellation remains disabled",async()=>{
  const h=harness();await h.ready;h.activate();const detail=h.run("loadTask('task:one',{focus:true})");await h.waitForRequests(1);
  h.respond(h.requests[0],{id:"task:one",objective:"<untrusted objective>",status:"failed",nodes:[{id:"first",status:"completed",attempts:1},{id:"second",status:"failed",attempts:2,failure_class:"denied"}]});await detail;
  assert.equal(h.get("#task-progress").value,1);assert.equal(h.get("#task-progress").max,2);assert.equal(h.get("#cancel-task").disabled,true);
  assert.match(h.get("#task-detail-state").textContent,/failed/);assert.match(h.get("#task-nodes").children[1].textContent,/denied/);assert.equal(h.get("#task-detail-title").textContent,"<untrusted objective>");
  h.windowEvents.offline();assert.match(h.get("#task-detail-state").textContent,/stale/);
});

test("F14 task reads reject older selection and logout; reconnect schedules refresh",async()=>{
  const h=harness();await h.ready;h.activate();const old=h.run("loadTask('old')");await h.waitForRequests(1);const latest=h.run("loadTask('new')");await h.waitForRequests(2);
  h.respond(h.requests[0],{id:"old",objective:"obsolete",nodes:[]});await old;
  h.respond(h.requests[1],{id:"new",objective:"current",status:"completed",nodes:[]});await latest;assert.equal(h.get("#task-detail-title").textContent,"current");
  const late=h.run("loadTask('late')");await h.waitForRequests(3);await h.run("logout()");h.respond(h.requests[2],{id:"late",objective:"private",nodes:[]});await late;assert.equal(h.get("#task-detail").hidden,true);
});

test("F14 task list paginates, marks offline stale and schedules foreground recovery",async()=>{
  const h=harness();await h.ready;h.activate();const first=h.run("refreshTasks()");await h.waitForRequests(1);
  h.respond(h.requests[0],Array.from({length:50},(_,i)=>({id:`task:${i}`,status:"running",completed_nodes:1,total_nodes:3})));await first;assert.equal(h.get("#more-tasks").hidden,false);
  const more=h.run("refreshTasks({more:true})");await h.waitForRequests(2);assert.ok(h.requests[1].url.includes("&offset=50"));h.respond(h.requests[1],[]);await more;
  assert.equal(h.get("#tasks").children.length,0);assert.equal(h.get("#more-tasks").hidden,true);assert.equal(h.get("#previous-tasks").hidden,false);
  h.run("scheduleTaskRefresh(0)");h.runTimer(delay=>delay===0);await h.waitForRequests(3);h.respond(h.requests[2],[]);
});

test("F14 processing failure retains text draft with actionable attachment guidance",async()=>{
  const h=attachmentHarness();h.context.files=[h.file()];await h.run("selectAttachments(files)");h.uploads[0].respond();
  h.get("#message").value="read notes";h.run("state.subscription='subscription:synthetic'");
  const send=h.run("sendMessage({preventDefault(){}})");await h.waitForRequests(1);
  const payload=JSON.parse(h.requests[0].options.body);
  h.respond(h.requests[0],{request_id:payload.request_id,conversation_id:"owned",status:"failed",error:{code:"attachment_processing_failed"}});await send;
  assert.equal(h.get("#message").value,"read notes");assert.match(h.get("#chat-status").textContent,/Attachment processing failed/);
});

test("F14 successful reconnect poll schedules current task recovery without another stream owner",async()=>{
  const h=harness();await h.ready;h.activate();h.run("state.healthAllowed=false;state.subscription='subscription:owned';startStreamOwnership()");await h.waitForRequests(1);
  h.requests[0].pending.resolve({ok:true,status:200,text:async()=>": keepalive\n\n"});await h.waitForRequests(2);
  h.runTimer(delay=>delay===0);await h.waitForRequests(3);assert.equal(h.requests[2].url,"/api/v1/client/tasks?limit=50&sort=newest");
  h.respond(h.requests[2],[]);h.run("stopStream()");h.requests[1].pending.resolve({ok:true,status:200,text:async()=>": keepalive\n\n"});
});

function voiceHarness() {
  const h = harness(), permission = deferred(), tracks = [{ stopped: 0, stop() { this.stopped++; } }];
  const stream = { getTracks: () => tracks }, resources = { requests: 0, closed: 0, disconnected: 0, ports: 0, nodes: [] };
  h.context.navigator.mediaDevices = { getUserMedia(options) { resources.requests++; assert.equal(options.video, false); return permission.promise; } };
  h.context.window.AudioContext = class {
    constructor() { this.sampleRate = 48000; this.state = "running"; resources.context = this; }
    audioWorklet = { addModule: async url => { assert.equal(url, "/app/pcm-worklet.js?v=12"); } };
    createMediaStreamSource() { return { connect: node => { assert.equal(node.options.numberOfOutputs, 1); }, disconnect: () => resources.disconnected++ }; }
    async resume() {}
    async close() { resources.closed++; this.state = "closed"; }
  };
  h.context.window.AudioWorkletNode = class {
    constructor(context, name, options) {
      this.options = options; resources.nodes.push(this);
      this.port = { onmessage: null, close: () => resources.ports++, postMessage: data => { if (data === "stop") queueMicrotask(() => this.port.onmessage?.({ data: { done: true } })); } };
    }
    disconnect() { resources.disconnected++; }
    connect() {}
  };
  h.voiceActivate = () => { h.activate(); h.run("state.voiceReady=true;updateControls()"); };
  h.grant = () => permission.resolve(stream);
  h.deny = () => permission.reject(new Error("denied"));
  h.voiceResources = resources; h.voiceTracks = tracks;
  h.voiceChunk = (size = 2048) => resources.nodes.at(-1).port.onmessage({ data: { pcm: new ArrayBuffer(size) } });
  h.voiceStart = async () => { const promise = h.run("recordMessage()"); h.grant(); await promise; };
  return h;
}

test("voice has no permission/network side effects before explicit Record; empty current Chat required", async () => {
  const h = voiceHarness(); await h.ready; h.voiceActivate();
  h.run("selectView('settings');selectView('chat')");
  assert.equal(h.voiceResources.requests, 0); assert.equal(h.requests.length, 0);
  for (const block of ["ui.message.value='draft'", "state.pendingRequest={request_id:'uncertain'}", "state.historyBusy=true", "state.voiceReady=false"]) {
    h.run(block); await h.run("recordMessage()"); assert.equal(h.voiceResources.requests, 0);
    h.run("ui.message.value='';state.pendingRequest=null;state.historyBusy=false;state.voiceReady=true");
  }
});

test("voice Stop releases microphone before upload; transcript remains editable until explicit Send", async () => {
  const h = voiceHarness(); await h.ready; h.voiceActivate(); await h.voiceStart();
  assert.equal(h.run("state.voice.phase"), "recording"); assert.equal(h.get("#message").readOnly, true);
  h.voiceChunk(); h.voiceChunk(); const stop = h.run("stopRecording()"); await h.waitForRequests(1);
  assert.ok(h.voiceTracks.every(t => t.stopped)); assert.equal(h.voiceResources.closed, 1); assert.equal(h.voiceResources.ports, 1);
  assert.equal(h.requests[0].url, "/api/v1/client/voice/transcriptions");
  assert.equal(h.requests[0].options.body.length, 4096); assert.equal(h.requests[0].options.cache, "no-store");
  assert.equal(h.requests[0].options.headers["Content-Type"], "application/octet-stream");
  h.respond(h.requests[0], { text: "<script>Synthetic draft</script>", duration_ms: 128 }); await stop;
  assert.equal(h.get("#message").value, "<script>Synthetic draft</script>"); assert.equal(h.get("#message").readOnly, false);
  assert.equal(h.get("#voice-status").textContent, "Review transcript, then Send."); assert.equal(h.requests.length, 1);
  assert.equal(h.storage.size, 0); assert.equal(h.records.size, 0);
});

test("voice denial, never resolved permission and late grant leave text usable and stop all tracks", async () => {
  for (const action of ["deny", "timeout", "discard"]) {
    const h = voiceHarness(); await h.ready; h.voiceActivate(); const start = h.run("recordMessage()");
    if (action === "deny") h.deny();
    else { if (action === "timeout") h.runTimer(delay => delay === 30000); else h.run("discardVoice()"); h.grant(); }
    await start; assert.equal(h.run("state.voice"), null); assert.equal(h.get("#message").readOnly, false);
    assert.equal(h.requests.length, 0); if (action !== "deny") assert.ok(h.voiceTracks.every(t => t.stopped));
  }
});

for (const action of ["discard", "escape", "hide", "pagehide", "offline", "navigation", "conversation", "session", "track", "mute", "context", "processor", "input"]) {
  test(`voice ${action} cancels capture and releases every resource without upload`, async () => {
    const h = voiceHarness(); await h.ready; h.voiceActivate(); await h.voiceStart(); h.voiceChunk();
    if (action === "discard") h.run("discardVoice()");
    if (action === "escape") h.windowEvents.keydown({ key: "Escape", preventDefault() {} });
    if (action === "hide") { h.context.document.hidden = true; h.windowEvents.visibilitychange(); }
    if (action === "pagehide") h.windowEvents.pagehide();
    if (action === "offline") { h.context.navigator.onLine = false; h.windowEvents.offline(); }
    if (action === "navigation") h.run("selectView('settings')");
    if (action === "conversation") h.run("chooseConversation(null)");
    if (action === "session") h.run("invalidateSession()");
    if (action === "track") h.voiceTracks[0].onended();
    if (action === "mute") h.voiceTracks[0].onmute();
    if (action === "context") { h.voiceResources.context.state = "suspended"; h.voiceResources.context.onstatechange(); }
    if (action === "processor") h.voiceResources.nodes[0].onprocessorerror();
    if (action === "input") { h.get("#message").value = "replacement"; h.get("#message").listeners.input[0](); }
    assert.equal(h.run("state.voice"), null); assert.ok(h.voiceTracks.every(t => t.stopped)); assert.equal(h.voiceResources.closed, 1);
    assert.equal(h.voiceResources.ports, 1); assert.equal(h.voiceResources.disconnected, 2);
    assert.equal(h.requests.filter(r => r.url.includes("voice")).length, 0);
  });
}

test("voice hard wall duration stops then uploads; short, malformed and excess capture rejected", async () => {
  const h = voiceHarness(); await h.ready; h.voiceActivate(); await h.voiceStart(); h.voiceChunk(); h.voiceChunk();
  h.runTimer(delay => delay === 30000); await h.waitForRequests(1); h.respond(h.requests[0], { text: "bounded", duration_ms: 128 });
  for (let i = 0; i < 20; i++) await Promise.resolve();
  assert.equal(h.get("#message").value, "bounded");
  for (const size of [2, 2050, 2047]) {
    const n = voiceHarness(); await n.ready; n.voiceActivate(); await n.voiceStart(); n.voiceChunk(size); await n.run("stopRecording()");
    assert.equal(n.requests.length, 0); assert.equal(n.run("state.voice"), null);
  }
});

for (const action of ["discard", "conversation", "session", "composer", "logout", "back"]) {
  test(`voice late upload result cannot overwrite ${action} owner or Send automatically`, async () => {
    const h = voiceHarness(); await h.ready; h.voiceActivate(); await h.voiceStart(); h.voiceChunk(); h.voiceChunk();
    const stop = h.run("stopRecording()"); await h.waitForRequests(1);
    if (action === "discard") h.run("discardVoice()");
    if (action === "conversation") h.run("state.conversation='other'");
    if (action === "session") h.run("state.sessionGeneration++");
    if (action === "composer") h.run("state.composerRevision++;ui.message.value='edited'");
    if (action === "logout") await h.run("logout()");
    if (action === "back") { h.run("selectView('settings')"); h.history.go(-1); }
    h.respond(h.requests[0], { text: "obsolete", duration_ms: 128 }); await stop;
    assert.notEqual(h.get("#message").value, "obsolete"); assert.equal(h.run("state.voice"), null);
    assert.equal(h.requests.filter(r => r.url === "/api/v1/client/chat").length, 0);
  });
}

test("offline logout erases local identity and displayed data while remote DELETE remains pending", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.activate();
  h.run("state.subscription='synthetic-subscription';state.conversation='synthetic-conversation';state.cursor=4;renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  for (const selector of ["#device-status", "#tasks", "#log"]) h.get(selector).append(element());
  h.get("#message").value = "Synthetic draft";
  h.get("#ticket").value = "Synthetic ticket";
  const logout = h.run("logout()");
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(h.run("state.subscription"), null);
  assert.equal(h.run("state.conversation"), null);
  assert.equal(h.run("state.cursor"), 0);
  for (const selector of ["#device-status", "#tasks", "#log", "#garmin-metrics", "#garmin-activities"]) assert.equal(h.get(selector).children.length, 0);
  assert.equal(h.get("#message").value, "");
  assert.equal(h.get("#ticket").value, "");
  assert.equal(h.get("#logout").disabled, true);
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, "/api/v1/sessions/current");
  assert.equal(h.requests[0].options.method, "DELETE");
  assert.equal(h.requests[0].options.credentials, "include");
  assert.equal(h.requests[0].options.headers["X-Jarvis-CSRF"], "synthetic-session");
  await logout;
  assert.equal(await h.run("loadIdentity()"), undefined);
  assert.match(h.get("#connection").textContent, /Logged out/);
  // An old revocation response cannot expire a later valid connection.
  h.activate("synthetic-new-session");
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:84,activities:[]})");
  h.respond(h.requests[0], {}, 401);
  await Promise.resolve();
  assert.equal(h.run("state.online"), true);
  assert.equal(h.run("state.healthAllowed"), true);
  assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "84");
});

test("late status and task JSON cannot restore private views after logout", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.activate();
  const status = h.run("refreshStatus()"), tasks = h.run("refreshTasks()");
  const bodies = [deferred(), deferred()], started = [deferred(), deferred()];
  for (let index = 0; index < 2; index++) h.requests[index].pending.resolve({ ok: true, status: 200, json: () => { started[index].resolve(); return bodies[index].promise; } });
  await Promise.all(started.map(item => item.promise));
  await h.run("logout()");
  bodies[0].resolve({ device: { display_name: "Synthetic name", state: "active", key_version: 1 }, session: { id: "synthetic-old-session" } });
  bodies[1].resolve([{ id: "synthetic-old-task", status: "complete" }]);
  await Promise.all([status, tasks]);
  assert.equal(h.get("#device-status").children.length, 0);
  assert.equal(h.get("#tasks").children.length, 0);
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(await h.run("loadIdentity()"), undefined);
  h.respond(h.requests[2], {});
});

test("logout rejects a late session bootstrap response or JSON body", async () => {
  for (const phase of ["response", "body"]) {
    const h = harness();
    await h.ready;
    h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
    h.run("signedHeaders=async()=>({})");
    const connect = h.run("connect()");
    await h.waitForRequests(1);
    assert.equal(h.requests[0].url, "/api/v1/browser/sessions");
    const body = deferred(), started = deferred();
    if (phase === "body") {
      h.requests[0].pending.resolve({ ok: true, status: 201, json: () => { started.resolve(); return body.promise; } });
      await started.promise;
    }
    await h.run("logout()");
    const credential = { csrf_token: "synthetic-late-session" };
    if (phase === "response") h.respond(h.requests[0], credential, 201);
    else body.resolve(credential);
    await connect;
    await h.waitForRequests(2);
    assert.equal(h.requests[0].options.signal.aborted, phase === "response");
    assert.equal(h.requests[1].url, "/api/v1/sessions/current");
    assert.equal(h.requests[1].options.headers["X-Jarvis-CSRF"], "synthetic-late-session");
    assert.equal(h.run("state.csrf"), null);
    assert.equal(h.run("state.hasIdentity"), false);
    assert.equal(h.run("state.healthAllowed"), false);
    assert.equal(h.run("state.online"), false);
    assert.equal(h.get("#device-status").children.length, 0);
    assert.equal(await h.run("loadIdentity()"), undefined);
    h.respond(h.requests[1], {});
    await h.run("state.logoutPending");
  }
});

test("late subscription bootstrap cannot restore a logged-out session", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  await h.waitForRequests(1);
  h.respond(h.requests[0], { csrf_token: "synthetic-session" }, 201);
  await h.waitForRequests(2);
  await h.run("logout()");
  h.respond(h.requests[1], { id: "synthetic-late-subscription", next_cursor: 8 });
  await connect;
  assert.equal(h.run("state.subscription"), null);
  assert.equal(h.run("state.cursor"), 0);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.requests.length, 3);
  h.respond(h.requests[2], {});
});

test("startup identity lookup cannot restore identity after logout", async () => {
  const h = harness();
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  await h.run("logout()");
  await h.ready;
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(h.get("#logout").disabled, true);
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("replacement enrollment waits for old remote logout response before creating a key", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  await h.run("logout()");
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-enrollment", challenge: "synthetic-challenge", approved_scopes: ["client.health.read"] });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  assert.equal(await h.run("loadIdentity()"), undefined);
  // Browser applies old Set-Cookie/Clear-Site-Data before replacement may begin.
  h.respond(h.requests[0], { revoked: true });
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/enrollments/complete");
  assert.equal(h.requests[0].options.signal.aborted, false);
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { id: "synthetic-new-device", key_version: 1 }, 201);
  await enroll;
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("remote logout aborts after five seconds and releases replacement bootstrap", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  await h.run("logout()");
  h.setIdentity({ deviceId: "synthetic-recovery", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  h.runTimer(delay => delay === 5000);
  assert.equal(h.requests[0].options.signal.aborted, true);
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/browser/sessions");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { csrf_token: "synthetic-recovery-session" }, 201);
  await connect;
  h.respond(h.requests[0], { revoked: true });
  assert.equal(h.run("state.csrf"), null);
});

test("replacement waits for stale bootstrap cookie cleanup as well as local logout", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  await h.waitForRequests(1);
  const body = deferred(), started = deferred();
  h.requests[0].pending.resolve({ ok: true, status: 201, json: () => { started.resolve(); return body.promise; } });
  await started.promise;
  await h.run("logout()");
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-recovery-enrollment", challenge: "synthetic-recovery-challenge" });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  body.resolve({ csrf_token: "synthetic-stale-bootstrap-session" });
  await connect;
  await h.waitForRequests(2);
  assert.equal(h.requests[1].options.headers["X-Jarvis-CSRF"], "synthetic-stale-bootstrap-session");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 2);
  h.respond(h.requests[1], { revoked: true });
  await h.waitForRequests(3);
  assert.equal(h.requests[2].url, "/api/v1/enrollments/complete");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[2], { id: "synthetic-recovery-device", key_version: 1 }, 201);
  await enroll;
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("replacement waits for local worker cleanup even when remote logout already succeeded", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const cleanup = deferred(), started = deferred();
  h.context.navigator.serviceWorker = { getRegistrations: async () => [{ active: { postMessage() {} }, unregister: () => { started.resolve(); return cleanup.promise; } }] };
  const logout = h.run("logout()");
  await started.promise;
  h.respond(h.requests[0], { revoked: true });
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-enrollment", challenge: "synthetic-challenge" });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  cleanup.resolve(true);
  await logout;
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/enrollments/complete");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { id: "synthetic-new-device", key_version: 1 }, 201);
  await enroll;
});

test("logout clears identity after an already-started local identity write settles", async () => {
  const h = harness();
  await h.ready;
  const write = deferred();
  h.context.syntheticWrite = write.promise;
  h.run("state.identityWrite=syntheticWrite");
  const logout = h.run("logout()");
  h.setIdentity({ deviceId: "synthetic-late-write", healthAllowed: true });
  write.resolve();
  await logout;
  assert.equal(await h.run("loadIdentity()"), undefined);
  assert.equal(h.run("state.hasIdentity"), false);
});

test("late chat response body or error cannot restore conversation after logout", async () => {
  for (const failure of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.run("state.subscription='synthetic-subscription'");
    h.get("#message").value = "Synthetic public prompt";
    const send = h.run("sendMessage({preventDefault(){}})");
    await h.waitForRequests(1);
    const body = deferred(), started = deferred();
    if (!failure) {
      h.requests[0].pending.resolve({ ok: true, status: 200, json: () => { started.resolve(); return body.promise; } });
      await started.promise;
    }
    await h.run("logout()");
    if (failure) h.requests[0].pending.reject(new Error("Synthetic delayed chat error"));
    else body.resolve({ conversation_id: "synthetic-late-conversation", reply: "Synthetic delayed reply" });
    await send;
    assert.equal(h.get("#log").children.length, 0);
    assert.equal(h.run("state.conversation"), null);
    h.respond(h.requests[1], { revoked: true });
  }
});

test("successful stream polls are paced and logout wakes pacing without a stale request", async () => {
  const h = harness(); await h.ready; streamSession(h);
  const stream = h.run("streamLoop()");
  respondStream(h, h.requests[0]);
  await flush();
  assert.equal(h.requests.length, 1, "Fast token batches cannot start a tight polling loop");
  h.runTimer(delay => delay === 500);
  await h.waitForRequests(2);
  respondStream(h, h.requests[1]); await flush();
  await h.run("logout()"); await stream;
  assert.equal(h.requests.length, 3, "Logout wakes pacing and only sends revocation");
  h.respond(h.requests[2], { revoked: true });
});

test("late stream body cannot restore cursor, conversation or log after logout", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("state.subscription='synthetic-subscription'");
  const stream = h.run("streamLoop()"), body = deferred(), started = deferred();
  h.requests[0].pending.resolve({ ok: true, status: 200, text: () => { started.resolve(); return body.promise; } });
  await started.promise;
  await h.run("logout()");
  body.resolve('data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"synthetic-request","payload":{"content_delta":"Synthetic private reply"}}\n\ndata: {"cursor":2,"topic":"chat","event_type":"chat.completed","payload":{"conversation_id":"synthetic-old-conversation"}}\n\n');
  await stream;
  assert.equal(h.run("state.cursor"), 0);
  assert.equal(h.run("state.conversation"), null);
  assert.equal(h.get("#log").children.length, 0);
  assert.equal(h.run("state.online"), false);
  h.respond(h.requests[1], { revoked: true });
});

test("stream reconnect backoff cannot reconnect a logged-out or replaced session", async () => {
  for (const replacement of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.run("state.subscription='synthetic-subscription'");
    const stream = h.run("streamLoop()");
    h.requests[0].pending.reject(new Error("Synthetic network loss"));
    for (let turn = 0; turn < 10; turn++) await Promise.resolve();
    assert.equal(h.run("state.online"), false);
    await h.run("logout()");
    if (replacement) h.activate("synthetic-replacement-session");
    const label = h.get("#connection").textContent;
    // Logout cancels and wakes the backoff instead of waiting for its old timer.
    await stream;
    assert.equal(h.get("#connection").textContent, label);
    assert.equal(h.run("state.online"), replacement);
    assert.equal(h.get("#message").disabled, !replacement);
    assert.equal(h.requests.length, 2);
    h.respond(h.requests[1], { revoked: true });
  }
});

test("late notification permission cannot restore notification flag after logout", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const permission = deferred();
  h.context.Notification = h.context.window.Notification = { requestPermission: () => permission.promise };
  const notifications = h.run("enableNotifications()");
  await h.run("logout()");
  permission.resolve("granted");
  await notifications;
  assert.equal(h.storage.has("jarvis-notifications"), false);
  h.respond(h.requests[0], { revoked: true });
});

test("rejected enrollment preserves existing stream generation and connection", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-existing-device", healthAllowed: true });
  h.activate();
  const generation = h.run("state.sessionGeneration");
  await assert.rejects(h.run("enroll()"), /Log out and erase/);
  assert.equal(h.run("state.sessionGeneration"), generation);
  assert.equal(h.run("state.online"), true);
  assert.equal(h.run("state.healthAllowed"), true);
  assert.equal(h.requests.length, 0);
});

test("failed reconnect aborts old stream and remains offline with health cleared", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-existing-device", healthAllowed: true });
  h.activate("synthetic-existing-session");
  h.context.syntheticStreamController = new AbortController();
  h.run("state.streamAbort=syntheticStreamController;renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]});signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  assert.equal(h.context.syntheticStreamController.signal.aborted, true);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.get("#connection").textContent, "Connecting");
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  await h.waitForRequests(1);
  h.respond(h.requests[0], {}, 403);
  await assert.rejects(connect, /Session bootstrap rejected \(403\)/);
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#connection").textContent, "Connection failed");
  assert.equal(h.get("#refresh-garmin").disabled, true);
  assert.equal(h.get("#message").disabled, true);
});

test("logout clears health immediately and ignores delayed Garmin fetch even if revocation fails", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  const refresh = h.run("refreshGarmin(true)");
  const garmin = h.requests[0];
  const logout = h.run("logout()");
  assert.equal(garmin.options.signal.aborted, true);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-activities").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  assert.equal(h.get("#refresh-garmin").disabled, true);
  h.respond(garmin, h.summary(123));
  await refresh;
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  h.requests[1].pending.reject(new Error("Synthetic revocation failure"));
  await logout;
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
});

test("logout blocks delayed JSON body and late errors from changing cleared health view", async () => {
  for (const failure of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    const refresh = h.run("refreshGarmin(false)");
    const body = deferred();
    const bodyStarted = deferred();
    h.requests[0].pending.resolve({ ok: true, status: 200, json: () => { bodyStarted.resolve(); return body.promise; } });
    await bodyStarted.promise;
    const logout = h.run("logout()");
    if (failure) body.reject(new Error("Late synthetic parse failure"));
    else body.resolve(h.summary(234));
    await refresh;
    assert.equal(h.get("#garmin-metrics").children.length, 0);
    assert.equal(h.get("#garmin-state").textContent, EMPTY);
    h.respond(h.requests[1], {});
    await logout;
  }
});

test("new connect clears old health and ignores old response before identity lookup finishes", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const refresh = h.run("refreshGarmin(false)");
  const connect = h.run("connect()");
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  assert.equal(h.run("state.healthAllowed"), false);
  h.respond(h.requests[0], h.summary(345));
  await refresh;
  await assert.rejects(connect, /No enrolled device key/);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
});

test("older refresh cannot replace latest result or its status", async () => {
  for (const failure of ["none", "transport", "expired-session"]) {
    const h = harness();
    await h.ready;
    h.activate();
    const older = h.run("refreshGarmin(false)");
    const latest = h.run("refreshGarmin(true)");
    assert.equal(h.requests[0].options.signal.aborted, true);
    h.respond(h.requests[1], h.summary(456));
    await latest;
    const label = h.get("#garmin-state").textContent;
    if (failure === "transport") h.requests[0].pending.reject(new Error("Late older failure"));
    else if (failure === "expired-session") h.respond(h.requests[0], {}, 401);
    else h.respond(h.requests[0], h.summary(999));
    await older;
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "456");
    assert.equal(h.get("#garmin-state").textContent, label);
    assert.equal(h.run("state.online"), true);
  }
});

test("active session rejection clears health rather than retaining stale private values", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  const refresh = h.run("refreshGarmin(true)");
  h.respond(h.requests[0], {}, 401);
  await refresh;
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
});

test("offline cancels pending refresh and keeps stale presentation; new session rejects old response", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const offlineRefresh = h.run("refreshGarmin(true)");
  h.context.navigator.onLine = false;
  h.windowEvents.offline();
  const stale = h.get("#garmin-state").textContent;
  h.respond(h.requests[0], h.summary(567));
  await offlineRefresh;
  assert.equal(h.get("#garmin-state").textContent, stale);
  assert.match(stale, /stale/);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  h.context.navigator.onLine = true;
  h.activate("session:old");
  const old = h.run("refreshGarmin(false)");
  h.activate("session:new");
  h.respond(h.requests[1], h.summary(678));
  await old;
  assert.equal(h.get("#garmin-metrics").children.length, 0);
});

test("Garmin response is explicitly stale at five minutes and for invalid or future timestamps", async () => {
  for (const [age, timestamp, expectedStale] of [
    [299999, "2026-10-07T12:00:00Z", false],
    [300000, "2026-10-07T12:00:00Z", true],
    [600000, "2026-10-07T12:00:00Z", true],
    [0, "2026-10-07T12:00:01Z", true],
    [0, "invalid timestamp", true],
  ]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.clock.now += age;
    const refresh = h.run("refreshGarmin(true)");
    const summary = { ...h.summary(789), refreshed_at: timestamp };
    h.respond(h.requests[0], summary);
    await refresh;
    const label = h.get("#garmin-state").textContent;
    assert.equal(label.includes("Stale. Refresh Garmin"), expectedStale);
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "789");
    if (timestamp === "invalid timestamp") assert.match(label, /last checked Unknown/);
  }
});

test("failed Garmin refresh retains prior metrics with explicit stale warning", async () => {
  for (const failure of ["transport", "unavailable"]) {
    const h = harness();
    await h.ready;
    h.activate();
    const initial = h.run("refreshGarmin(false)");
    h.respond(h.requests[0], h.summary(890));
    await initial;
    assert.doesNotMatch(h.get("#garmin-state").textContent, /stale/i);
    const refresh = h.run("refreshGarmin(true)");
    if (failure === "transport") h.requests[1].pending.reject(new Error("Synthetic network failure"));
    else h.respond(h.requests[1], {}, 503);
    await refresh;
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "890");
    assert.match(h.get("#garmin-state").textContent, /Shown Garmin data may be stale\./);
    assert.equal(h.get("#garmin-activities").children.length, 1);
  }
});

async function flush() { for (let turn = 0; turn < 40; turn++) await Promise.resolve(); }
function streamSession(h) {
  h.activate();
  h.run("state.healthAllowed=false;state.subscription='synthetic-subscription';setConnected(false,'Checking live connection')");
}
function respondStream(h, request, text = ": keepalive\n\n") {
  request.pending.resolve({ ok: true, status: 200, text: async () => text });
}

test("offline and repeated online events retain one owner and require a successful current poll", async () => {
  for (const outcome of ["success", "rejection", "stalled-body"]) {
    const h = harness(); await h.ready; streamSession(h);
    h.run("startStreamOwnership()"); await h.waitForRequests(1);
    const owner = h.run("state.streamOwner"), body = deferred();
    if (outcome === "stalled-body") h.requests[0].pending.resolve({ ok: true, status: 200, text: () => body.promise });
    await flush(); h.context.navigator.onLine = false; h.windowEvents.offline(); await flush();
    assert.equal(h.requests[0].options.signal.aborted, true);
    assert.equal(h.get("#send").disabled, true);
    if (outcome === "success") respondStream(h, h.requests[0]);
    if (outcome === "rejection") h.requests[0].pending.reject(new Error("Synthetic offline rejection"));
    if (outcome === "stalled-body") body.resolve('data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"old","payload":{"content_delta":"Old reply"}}\n\n');
    await flush(); assert.equal(h.run("state.cursor"), 0);
    h.context.navigator.onLine = true; h.windowEvents.online(); h.windowEvents.online();
    assert.equal(h.get("#send").disabled, true); assert.equal(h.run("state.streamOwner"), owner);
    await h.waitForRequests(2); assert.equal(h.get("#send").disabled, true);
    h.run("state.chatDrafts.set('current','Synthetic recovered prompt')");
    respondStream(h, h.requests[1], 'data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"current","payload":{"content_delta":"Recovered reply"}}\n\n');
    await h.waitForRequests(3); assert.equal(h.run("state.online"), true);
    assert.equal(h.get("#send").disabled, false); assert.equal(h.run("state.cursor"), 1);
    assert.match(h.get("#log").children[0].textContent, /Recovered reply/);
    assert.equal(h.requests.filter(r => !r.options.signal.aborted && r === h.requests[2]).length, 1);
    h.run("stopStream()"); await flush();
  }
});

test("401 and stream 403 preserve key but online cannot reactivate rejected credentials", async () => {
  for (const status of [401, 403]) {
    const h = harness(); await h.ready; streamSession(h);
    h.setIdentity({ deviceId: "synthetic-device" }); h.run("startStreamOwnership()"); await h.waitForRequests(1);
    h.respond(h.requests[0], {}, status); await flush();
    assert.equal(h.run("state.csrf"), null); assert.equal(h.run("state.subscription"), null);
    assert.equal(h.run("state.hasIdentity"), true); assert.ok(await h.run("loadIdentity()"));
    h.context.navigator.onLine = false; h.windowEvents.offline(); h.context.navigator.onLine = true; h.windowEvents.online();
    await flush(); assert.equal(h.requests.length, 1); assert.equal(h.get("#send").disabled, true);
    assert.match(h.get("#access-status").textContent, /Connect existing device/);
  }
});

test("stream deadline and reconnect backoff keep Send disabled until Core responds", async () => {
  for (const phase of ["headers", "body"]) {
    const h = harness(); await h.ready; streamSession(h); h.run("startStreamOwnership()"); await h.waitForRequests(1);
    const body = deferred();
    if (phase === "body") { h.requests[0].pending.resolve({ ok: true, status: 200, text: () => body.promise }); await flush(); }
    h.runTimer(delay => delay === 30000); await flush();
    assert.equal(h.requests[0].options.signal.aborted, true); assert.equal(h.get("#send").disabled, true);
    h.runTimer(delay => delay >= 500 && delay < 3500); await h.waitForRequests(2);
    assert.equal(h.get("#send").disabled, true); respondStream(h, h.requests[1]); await h.waitForRequests(3);
    assert.equal(h.get("#send").disabled, false);
    if (phase === "body") body.resolve(": keepalive\n\n"); else respondStream(h, h.requests[0]);
    h.run("stopStream()"); await flush();
  }
});

test("Core subscription reset requires a new authenticated event poll", async () => {
  const h = harness(); await h.ready; streamSession(h); h.run("startStreamOwnership()"); await h.waitForRequests(1);
  h.respond(h.requests[0], {}, 404); await h.waitForRequests(2);
  assert.equal(h.requests[1].options.method, "DELETE"); h.respond(h.requests[1], {}); await h.waitForRequests(3);
  h.respond(h.requests[2], { id: "synthetic-restarted-subscription", next_cursor: 8 }); await h.waitForRequests(4);
  assert.equal(h.get("#send").disabled, true); assert.match(h.requests[3].url, /after=8/);
  respondStream(h, h.requests[3]); await h.waitForRequests(5);
  assert.equal(h.requests[4].url, "/api/v1/client/conversations?limit=20");
  assert.equal(h.get("#send").disabled, true);
  h.respond(h.requests[4], { conversations: [], active_request: null });
  await h.waitForRequests(6); assert.equal(h.get("#send").disabled, false);
  h.run("stopStream()"); await flush();
});

test("queued Web Lock and repeated startup never create another active owner", async () => {
  const h = harness(); await h.ready; streamSession(h);
  const lock = deferred(); let callbacks = 0;
  h.context.navigator.locks = { request: async (name, options, callback) => { callbacks++; await lock.promise; return callback({ name }); } };
  h.run("startStreamOwnership();startStreamOwnership()"); assert.equal(callbacks, 1); assert.equal(h.requests.length, 0);
  assert.equal(h.get("#send").disabled, true); lock.resolve(); await h.waitForRequests(1);
  respondStream(h, h.requests[0]); await h.waitForRequests(2); assert.equal(h.get("#send").disabled, false);
  h.run("stopStream()"); await flush();
});

test("partial connect failure and body deadline release controls without false readiness", async () => {
  for (const phase of ["subscription", "status", "tasks", "stalled-body"]) {
    const h = harness(); await h.ready;
    h.setIdentity({ deviceId: "synthetic-device", healthAllowed: false }); h.run("signedHeaders=async()=>({})");
    const connection = h.run("connect()"), result = assert.rejects(connection);
    h.run("connect()"); await h.waitForRequests(1); assert.equal(h.get("#connect").disabled, true);
    h.respond(h.requests[0], { csrf_token: "synthetic-session" }, 201); await h.waitForRequests(2);
    if (phase === "subscription") h.respond(h.requests[1], {}, 503);
    else {
      h.respond(h.requests[1], { id: "synthetic-subscription", next_cursor: 0 }); await h.waitForRequests(3);
      if (phase === "status") h.respond(h.requests[2], {}, 503);
      else if (phase === "stalled-body") {
        h.requests[2].pending.resolve({ ok: true, status: 200, json: () => deferred().promise }); await flush(); h.runTimer(delay => delay === 10000);
      } else {
        h.respond(h.requests[2], { device: { display_name: "Synthetic", state: "active", key_version: 1 }, session: { id: "synthetic-session" } });
        await h.waitForRequests(4); h.respond(h.requests[3], {}, 503);
      }
    }
    await result; assert.equal(h.run("state.csrf"), null); assert.equal(h.get("#send").disabled, true);
    assert.equal(h.get("#connect").disabled, false); assert.equal(h.get("#enroll").disabled, true);
    assert.match(h.get("#access-status").textContent, /Retry Connect existing device/);
  }
});

test("history updates retain scroll position and selection until Jump to latest", async () => {
  const h = harness(); await h.ready; const log = h.get("#log");
  log.scrollHeight = 1000; log.clientHeight = 200; log.scrollTop = 120;
  h.run("row('jarvis','Synthetic delta','reply')"); assert.equal(log.scrollTop, 120); assert.equal(h.get("#jump-latest").hidden, false);
  log.scrollTop = 800;
  h.context.document.getSelection = () => ({ isCollapsed: false, anchorNode: log.children[0] });
  h.run("row('jarvis','Selected synthetic reply','reply')"); assert.equal(log.scrollTop, 800); assert.equal(h.get("#jump-latest").hidden, false);
  h.get("#jump-latest").listeners.click[0](); assert.equal(log.scrollTop, 1000); assert.equal(log.focused, true);
  assert.equal(h.get("#jump-latest").hidden, true);
});

test("completed answer announced once; delta, failed and cancelled behavior explicit", async () => {
  const h = harness(); await h.ready; let cursor = 0;
  const event = (type, payload = {}, id = "synthetic-reply") => {
    if (["chat.started", "chat.failed", "chat.cancelled"].includes(type)) h.run(`state.chatActive.add(${JSON.stringify(id)})`);
    return h.run(`processEvent(${JSON.stringify({ cursor: ++cursor, topic: "chat", event_type: type, request_id: id, payload })})`);
  };
  event("chat.started"); assert.equal(h.get("#chat").attributes["aria-busy"], "true");
  const start = h.get("#chat-status").textContent;
  event("chat.delta", { content_delta: "Synthetic " }); event("chat.frame", { type: "assistant_delta", content_delta: "answer" });
  assert.equal(h.get("#chat-status").textContent, start);
  event("chat.completed", { conversation_id: "synthetic-conversation" });
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Synthetic answer");
  assert.equal(h.get("#chat").attributes["aria-busy"], "false");
  h.get("#chat-status").textContent = "Sentinel"; event("chat.completed"); assert.equal(h.get("#chat-status").textContent, "Sentinel");
  event("chat.failed", {}, "failed-reply"); assert.equal(h.get("#chat-status").textContent, "Request failed safely.");
  event("chat.cancelled", {}, "cancelled-reply"); assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
});

test("model failures expose bounded recovery without leaking provider text or retrying", async () => {
  const h = harness(); await h.ready;
  for(const [code, expected] of [["provider_error",/Model unavailable/],["invalid_provider_response",/invalid reply/],["request_timeout",/timed out/],["__proto__",/Request failed safely/]]){
    h.context.failure={request_id:`failure:${code}`,status:"failed",error:{code,message:"PRIVATE PROVIDER BODY"}};
    h.run("state.chatActive.add(failure.request_id);applyChatResult(failure)");
    assert.match(h.get("#chat-status").textContent,expected);
    assert.equal(h.get("#chat-status").textContent.includes("PRIVATE PROVIDER BODY"),false);
  }
  assert.equal(h.requests.length,0);
});

test("failed send keeps draft and repeated submit cannot duplicate in-flight request", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft";
  const send = h.run("sendMessage({preventDefault(){}})"); h.run("sendMessage({preventDefault(){}})");
  await h.waitForRequests(1);
  assert.equal(h.requests.length, 1); assert.equal(h.get("#send").disabled, true);
  h.requests[0].pending.reject(new Error("Synthetic failed send")); await send;
  assert.equal(h.get("#message").value, "Synthetic draft"); assert.equal(h.get("#send").disabled, true);
  assert.equal(h.get("#retry-chat").disabled, false);
  assert.match(h.get("#chat-status").textContent, /outcome unconfirmed.*Draft kept/);
});

test("Garmin ages on screen and retains fetched-at context while loading without new reads", async () => {
  const h = harness(); await h.ready; h.activate();
  const initial = h.run("refreshGarmin(false)"); h.respond(h.requests[0], h.summary(42)); await initial;
  const refreshed = h.get("#garmin-state").textContent; h.clock.now += 299999; h.run("renderGarminStatus()");
  assert.equal(h.get("#garmin-state").textContent, refreshed); h.clock.now += 1; h.runTimer(delay => delay === 1);
  assert.match(h.get("#garmin-state").textContent, /Stale/); assert.equal(h.requests.length, 1);
  const loading = h.run("refreshGarmin(true)");
  assert.match(h.get("#garmin-state").textContent, /Checking Garmin.*last checked.*Stale/);
  assert.equal(h.get("#refresh-garmin").disabled, true); h.requests[1].pending.reject(new Error("Synthetic failure")); await loading;
  h.clock.now += 300000; h.windowEvents.visibilitychange(); assert.match(h.get("#garmin-state").textContent, /Stale/);
  await h.run("logout()"); h.windowEvents.pageshow(); h.windowEvents.visibilitychange();
  assert.equal(h.get("#garmin-state").textContent, EMPTY); assert.equal(h.run("state.healthSnapshot"), null);
  h.respond(h.requests[2], {});
});

test("logout focus and durable result distinguish remote success, failure and timeout", async () => {
  for (const result of [200, 503, "timeout"]) {
    const h = harness(); await h.ready; h.activate(); await h.run("logout()");
    assert.equal(h.get("#ticket").focused, true); assert.match(h.get("#access-status").textContent, /Server sign-out pending/);
    if (result === "timeout") h.runTimer(delay => delay === 5000); else h.respond(h.requests[0], {}, result);
    await flush(); assert.match(h.get("#access-status").textContent, result === 200 ? /Server sign-out confirmed/ : /Server sign-out unconfirmed/);
    assert.match(h.get("#access-status").textContent, /Device enrollment remains on Core/);
    assert.equal(h.get("#notice").textContent, h.get("#access-status").textContent);
  }
});

test("malformed ticket produces persistent associated recovery and no network call", async () => {
  const h = harness(); await h.ready; h.fakeEnrollmentCrypto(); h.get("#ticket").value = "{";
  await assert.rejects(h.run("enroll()"), /complete JSON/);
  assert.equal(h.requests.length, 0); assert.equal(h.get("#ticket").attributes["aria-invalid"], "true");
  assert.match(h.get("#ticket-error").textContent, /approved, unexpired, unused ticket/); assert.equal(h.get("#enroll").disabled, false);
});

test("completed HTTP reply survives later stream frames without duplicate speech", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic prompt"; const send = h.run("sendMessage({preventDefault(){}})");
  await h.waitForRequests(1);
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.started',request_id:'request:synthetic-request',payload:{}})");
  h.respond(h.requests[0], { reply: "Full synthetic answer", conversation_id: "synthetic-conversation" }); await send;
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Full synthetic answer");
  const announcement = h.get("#chat-status").textContent;
  h.run("processEvent({cursor:2,topic:'chat',event_type:'chat.started',request_id:'request:synthetic-request',payload:{}});processEvent({cursor:3,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Repeated answer'}});processEvent({cursor:4,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Full synthetic answer");
  assert.equal(h.get("#chat-status").textContent, announcement); assert.equal(h.run("state.cursor"), 4);
  assert.equal(h.get("#chat").attributes["aria-busy"], "false");
});

test("logout cancels a queued owner; later lock grant cannot start a stale poll", async () => {
  const h = harness(); await h.ready; streamSession(h); const lock = deferred(); let signal;
  h.context.navigator.locks = { request: async (name, options, callback) => { signal = options.signal; await lock.promise; return callback({ name }); } };
  h.run("startStreamOwnership()"); await h.run("logout()"); assert.equal(signal.aborted, true);
  lock.resolve(); await flush(); assert.equal(h.requests.length, 1); assert.equal(h.run("state.online"), false);
  h.respond(h.requests[0], {});
});

test("browser resume marks old health stale without another Garmin request", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  h.clock.now += 300001; h.windowEvents.pageshow(); h.windowEvents.visibilitychange();
  assert.match(h.get("#garmin-state").textContent, /Stale/); assert.equal(h.requests.length, 0);
});

test("unconfirmed POST outcome cannot suppress later authoritative streamed reply", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft"; const send = h.run("sendMessage({preventDefault(){}})");
  await h.waitForRequests(1);
  h.requests[0].pending.reject(new Error("Synthetic response loss")); await send;
  assert.equal(h.run("state.chatAnnounced.has('request:synthetic-request')"), false);
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Recovered authoritative answer'}});processEvent({cursor:2,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Recovered authoritative answer");
  assert.equal(h.get("#log").children[1].className, "entry jarvis");
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Recovered authoritative answer");
  assert.equal(h.get("#message").value, "");
});

test("lost POST response after streamed completion preserves known answer and clears submitted draft", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft"; const send = h.run("sendMessage({preventDefault(){}})");
  await h.waitForRequests(1);
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Known answer'}});processEvent({cursor:2,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  h.requests[0].pending.reject(new Error("Synthetic lost acknowledgement")); await send;
  assert.equal(h.get("#message").value, ""); assert.equal(h.get("#log").children[1].textContent, "JARVIS: Known answer");
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Known answer");
});

test("Garmin deadline bounds stalled headers/body and releases accessible loading state", async () => {
  for (const phase of ["headers", "body"]) {
    const h = harness(); await h.ready; h.activate(); const refresh = h.run("refreshGarmin(true)");
    if (phase === "body") { h.requests[0].pending.resolve({ ok: true, status: 200, json: () => deferred().promise }); await flush(); }
    assert.equal(h.get("#garmin").attributes["aria-busy"], "true"); assert.equal(h.get("#refresh-garmin").disabled, true);
    h.runTimer(delay => delay === 95000); await refresh;
    assert.equal(h.requests[0].options.signal.aborted, true); assert.equal(h.get("#refresh-garmin").disabled, false);
    assert.equal(h.get("#garmin").attributes["aria-busy"], "false"); assert.match(h.get("#garmin-state").textContent, /Garmin check failed/);
  }
});

test("steady keepalive polls do not repeatedly mutate polite connection statuses", async () => {
  const h = harness(); await h.ready; streamSession(h); const writes = new Map();
  for (const selector of ["#connection", "#access-status"]) {
    const node = h.get(selector); let value = node.textContent; writes.set(selector, 0);
    Object.defineProperty(node, "textContent", { get: () => value, set: next => { value = next; writes.set(selector, writes.get(selector) + 1); } });
  }
  h.run("startStreamOwnership()"); await h.waitForRequests(1); respondStream(h, h.requests[0]); await h.waitForRequests(2);
  respondStream(h, h.requests[1]); await h.waitForRequests(3); respondStream(h, h.requests[2]); await h.waitForRequests(4);
  assert.equal(writes.get("#connection"), 1); assert.equal(writes.get("#access-status"), 1);
  h.run("stopStream()"); await flush();
});

async function connectionToHistory(h, deviceId = "synthetic-device", pending = null) {
  const start = h.requests.length;
  h.run("signedHeaders=async()=>({})");
  const connection = h.run("connect()");
  await h.waitForRequests(start + 1);
  assert.equal(h.requests[start].url, "/api/v1/browser/sessions");
  h.respond(h.requests[start], { csrf_token: `session:${deviceId}` }, 201);
  await h.waitForRequests(start + 2);
  h.respond(h.requests[start + 1], { id: `subscription:${deviceId}`, next_cursor: 0 });
  await h.waitForRequests(start + 3);
  h.respond(h.requests[start + 2], { device: { display_name: "Synthetic", state: "active", key_version: 1 }, session: { id: `session:${deviceId}` } });
  await h.waitForRequests(start + 4);
  h.respond(h.requests[start + 3], []);
  await h.waitForRequests(start + 5);
  let listing = start + 4;
  if (pending) {
    assert.equal(h.requests[listing].url, `/api/v1/client/chat/${encodeURIComponent(pending.request_id)}?subscription_id=${encodeURIComponent(`subscription:${deviceId}`)}`);
    h.respond(h.requests[listing], pending); listing++;
    await h.waitForRequests(listing + 1);
  }
  assert.equal(h.requests[listing].url, "/api/v1/client/conversations?limit=20");
  return { connection, start, listing };
}

function savedConversation(id = "synthetic-conversation") {
  return { id, updated_at: "2026-10-07T12:00:00Z" };
}

function historyPage(conversationId, messages, requests = [], options = {}) {
  return { conversation_id: conversationId, messages, requests, next_before: null, has_more: false, ...options };
}

test("safe Retry checks Core then resubmits original immutable request without a duplicate user turn", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("state.subscription='synthetic-subscription';state.conversation='synthetic-conversation'");
  h.get("#message").value = "Original synthetic prompt";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const original = JSON.parse(h.requests[0].options.body);
  assert.deepEqual(JSON.parse(JSON.stringify(h.records.get("chat-request"))), { deviceId: "synthetic-device", request_id: original.request_id });
  assert.equal(h.records.has("device"), false, "Request marker must not overwrite enrolled identity");
  h.requests[0].pending.reject(new Error("Synthetic response loss")); await send;
  h.get("#message").value = "Different unsent draft";
  const retry = h.run("retryChat()"); h.run("retryChat();sendMessage({preventDefault(){}})");
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, `/api/v1/client/chat/${encodeURIComponent(original.request_id)}?subscription_id=synthetic-subscription`);
  assert.equal(h.requests[1].options.method, undefined);
  assert.equal(h.requests.filter(request => request.options.method === "POST").length, 1);
  h.respond(h.requests[1], {}, 404); await h.waitForRequests(3);
  assert.deepEqual(JSON.parse(h.requests[2].options.body), original);
  assert.equal(h.get("#log").children.filter(node => node.className === "entry user").length, 1);
  h.respond(h.requests[2], { request_id: original.request_id, status: "completed", conversation_id: original.conversation_id, reply: "One synthetic answer" });
  await retry; await flush();
  assert.equal(h.get("#message").value, "Different unsent draft");
  assert.equal(h.get("#log").children.length, 2);
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: One synthetic answer");
  assert.equal(h.records.has("chat-request"), false);
});

test("Retry finds accepted running or completed Core request without another POST", async () => {
  for (const status of ["running", "completed"]) {
    const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
    h.get("#message").value = "Synthetic accepted prompt";
    const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
    const id = JSON.parse(h.requests[0].options.body).request_id;
    h.requests[0].pending.reject(new Error("Synthetic lost acknowledgment")); await send;
    const retry = h.run("retryChat()"); await h.waitForRequests(2);
    h.respond(h.requests[1], { request_id: id, status, conversation_id: "synthetic-conversation", reply: status === "completed" ? "Accepted answer" : null });
    await retry;
    assert.equal(h.requests.length, 2);
    assert.equal(h.requests.filter(request => request.options.method === "POST").length, 1);
    assert.equal(h.get("#log").children.filter(node => node.className === "entry user").length, 1);
    assert.equal(h.run("state.pendingRequest?.request_id || null"), status === "running" ? id : null);
    assert.equal(h.get("#retry-chat").hidden, true);
    if (status === "running") {
      assert.equal(h.get("#cancel-chat").disabled, false);
      h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.completed", request_id: id, payload: { conversation_id: "synthetic-conversation", reply: "Accepted answer" } })})`);
    }
    assert.equal(h.get("#log").children[1].textContent, "JARVIS: Accepted answer");
    assert.equal(h.get("#message").value, "");
  }
});

test("Cancel requires Core acknowledgment and suppresses late completion and deltas", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic long request";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const id = JSON.parse(h.requests[0].options.body).request_id;
  h.respond(h.requests[0], { request_id: id, status: "running", conversation_id: "synthetic-conversation" }, 202); await send;
  const cancel = h.run("cancelChat()"); h.run("cancelChat()"); await h.waitForRequests(2);
  assert.equal(h.requests[1].url, `/api/v1/client/chat/${encodeURIComponent(id)}/cancel`);
  assert.equal(h.requests[1].options.method, "POST");
  assert.equal(h.requests[1].options.headers["X-Jarvis-CSRF"], "synthetic-session");
  assert.match(h.get("#chat-status").textContent, /Stopping reply on Core/);
  assert.equal(h.run("state.pendingRequest.request_id"), id);
  h.respond(h.requests[1], { request_id: id, status: "cancelled", conversation_id: "synthetic-conversation" }); await cancel;
  assert.equal(h.run("state.pendingRequest"), null);
  assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
  assert.equal(h.get("#chat").attributes["aria-busy"], "false");
  h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.delta", request_id: id, payload: { conversation_id: "synthetic-conversation", content_delta: "Obsolete answer" } })});processEvent(${JSON.stringify({ cursor: 2, topic: "chat", event_type: "chat.completed", request_id: id, payload: { conversation_id: "synthetic-conversation", reply: "Obsolete completed answer" } })})`);
  assert.equal(h.get("#log").children[1].textContent, "Request cancelled.");
  assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
  assert.equal(h.run("state.cursor"), 2);
});

test("reload restores Core history and resumes accepted request using only an opaque local marker", async () => {
  const original = harness(); await original.ready;
  original.setIdentity({ deviceId: "synthetic-device", healthAllowed: false }); original.activate();
  original.run("state.subscription='synthetic-subscription'"); original.get("#message").value = "Core-owned synthetic prompt";
  const send = original.run("sendMessage({preventDefault(){}})"); await original.waitForRequests(1);
  const id = JSON.parse(original.requests[0].options.body).request_id;
  original.respond(original.requests[0], { request_id: id, status: "running", conversation_id: "synthetic-conversation" }, 202); await send;
  assert.deepEqual([...original.records.keys()].sort(), ["chat-request", "device"]);
  assert.equal(JSON.stringify(original.records.get("chat-request")).includes("Core-owned synthetic prompt"), false);
  const h = harness(original.records); await h.ready;
  const running = { request_id: id, conversation_id: "synthetic-conversation", status: "running" };
  const { connection, listing } = await connectionToHistory(h, "synthetic-device", running);
  h.respond(h.requests[listing], { conversations: [savedConversation()], active_request: { request_id: id, conversation_id: "synthetic-conversation" } });
  await h.waitForRequests(listing + 2);
  h.respond(h.requests[listing + 1], historyPage("synthetic-conversation", [{ id: 1, role: "user", content: "Core-owned synthetic prompt", request_id: id }], [running]));
  await h.waitForRequests(listing + 3); assert.equal(h.requests[listing + 2].url, `/api/v1/client/chat/${encodeURIComponent(id)}?subscription_id=subscription%3Asynthetic-device`);
  h.respond(h.requests[listing + 2], running); await connection; await h.waitForRequests(listing + 4);
  assert.equal(h.requests.filter(request => request.url === "/api/v1/client/chat" && request.options.method === "POST").length, 0);
  assert.equal(h.get("#log").children[0].textContent, "You: Core-owned synthetic prompt");
  assert.equal(h.run("state.pendingRequest.request_id"), id);
  assert.equal(h.get("#send").disabled, true);
  respondStream(h, h.requests[listing + 3], `data: ${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.completed", request_id: id, payload: { conversation_id: "synthetic-conversation", reply: "Restored answer" } })}\n\n`);
  await h.waitForRequests(listing + 5); await flush();
  assert.equal(h.get("#log").children.length, 2);
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Restored answer");
  assert.equal(h.records.has("chat-request"), false);
  h.run("stopStream()"); await flush();
});

test("Core-backed completed history restores after reload without replaying generation or speech", async () => {
  const h = harness(); await h.ready; h.setIdentity({ deviceId: "synthetic-device", healthAllowed: false });
  const { connection } = await connectionToHistory(h);
  h.respond(h.requests[4], { conversations: [savedConversation()], active_request: null }); await h.waitForRequests(6);
  h.respond(h.requests[5], historyPage("synthetic-conversation", [
    { id: 1, role: "user", content: "Persisted prompt", request_id: "prior-request" },
    { id: 2, role: "assistant", content: "Persisted answer", request_id: "prior-request" },
  ], [{ request_id: "prior-request", conversation_id: "synthetic-conversation", status: "completed", reply: "Persisted answer" }]));
  await connection; await h.waitForRequests(7);
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["You: Persisted prompt", "JARVIS: Persisted answer"]);
  assert.equal(h.get("#chat-status").textContent, "Conversation restored from Core.");
  assert.equal(h.get("#send").disabled, true, "Authenticated stream must also recover before Send");
  respondStream(h, h.requests[6], `data: ${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.completed", request_id: "prior-request", payload: { conversation_id: "synthetic-conversation", reply: "Persisted answer" } })}\n\n`);
  await h.waitForRequests(8);
  assert.equal(h.get("#log").children.length, 2);
  assert.equal(h.get("#chat-status").textContent, "Conversation restored from Core.");
  assert.equal(h.get("#send").disabled, false);
  h.run("stopStream()"); await flush();
});

test("foreign conversation frames advance stream cursor without changing selected conversation", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.conversation='selected-conversation';row('jarvis','Selected answer','selected-request')");
  let cursor = 0;
  for (const [event_type, payload] of [
    ["chat.started", {}], ["chat.delta", { content_delta: "Foreign delta" }], ["chat.completed", { reply: "Foreign answer" }],
  ]) h.run(`processEvent(${JSON.stringify({ cursor: ++cursor, topic: "chat", event_type, request_id: "foreign-request", payload: { ...payload, conversation_id: "foreign-conversation" } })})`);
  assert.equal(h.run("state.cursor"), 3);
  assert.equal(h.run("state.conversation"), "selected-conversation");
  assert.equal(h.run("state.pendingRequest"), null);
  assert.equal(h.get("#log").children.length, 1);
  assert.equal(h.get("#log").children[0].textContent, "Selected answer");
});

test("history pagination prepends older Core messages once and retains current rows", async () => {
  const h = harness(); await h.ready; h.activate();
  const history = h.run("refreshHistory()"); await h.waitForRequests(1);
  h.respond(h.requests[0], { conversations: [savedConversation()], active_request: null }); await h.waitForRequests(2);
  h.respond(h.requests[1], historyPage("synthetic-conversation", [
    { id: 3, role: "user", content: "Recent prompt", request_id: "recent" },
    { id: 4, role: "assistant", content: "Recent answer", request_id: "recent" },
  ], [], { next_before: 3, has_more: true })); await history;
  const recentRows = [...h.get("#log").children];
  assert.equal(h.get("#older-history").hidden, false);
  const older = h.run("refreshHistory({older:true})"); await h.waitForRequests(3);
  assert.equal(h.requests[2].url, "/api/v1/client/conversations/synthetic-conversation/messages?limit=50&before=3");
  h.respond(h.requests[2], historyPage("synthetic-conversation", [
    { id: 1, role: "user", content: "Older prompt", request_id: "older" },
    { id: 2, role: "assistant", content: "Older answer", request_id: "older" },
  ])); await older;
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["You: Older prompt", "JARVIS: Older answer", "You: Recent prompt", "JARVIS: Recent answer"]);
  assert.equal(h.get("#log").children[2], recentRows[0]); assert.equal(h.get("#log").children[3], recentRows[1]);
  assert.equal(h.get("#older-history").hidden, true);
});

test("conversation selection rejects obsolete history page after later selection", async () => {
  const h = harness(); await h.ready; h.activate();
  const first = h.run("chooseConversation('conversation:first')"); await h.waitForRequests(1);
  h.respond(h.requests[0], { conversations: [savedConversation("conversation:first"), savedConversation("conversation:second")], active_request: null }); await h.waitForRequests(2);
  const second = h.run("chooseConversation('conversation:second')"); await h.waitForRequests(3);
  h.respond(h.requests[2], { conversations: [savedConversation("conversation:first"), savedConversation("conversation:second")], active_request: null }); await h.waitForRequests(4);
  h.respond(h.requests[3], historyPage("conversation:second", [{ id: 2, role: "assistant", content: "Current selected answer" }])); await second;
  h.respond(h.requests[1], historyPage("conversation:first", [{ id: 1, role: "assistant", content: "Obsolete selected answer" }])); await first;
  assert.equal(h.run("state.conversation"), "conversation:second");
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["JARVIS: Current selected answer"]);
  assert.equal(h.get("#send").disabled, false);
});

test("session replacement clears display immediately and ignores old history body", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("state.conversation='old-conversation';row('jarvis','Old session synthetic answer','old-request')");
  const history = h.run("refreshHistory()"); await h.waitForRequests(1);
  h.respond(h.requests[0], { conversations: [savedConversation("old-conversation")], active_request: null }); await h.waitForRequests(2);
  h.setIdentity({ deviceId: "replacement-device", healthAllowed: false });
  const replacement = connectionToHistory(h, "replacement-device");
  assert.equal(h.get("#log").children.length, 0);
  assert.equal(h.run("state.conversation"), null);
  h.respond(h.requests[1], historyPage("old-conversation", [{ id: 1, role: "assistant", content: "Delayed old session answer" }])); await history;
  const { connection, start } = await replacement;
  assert.equal(h.get("#log").children.length, 0);
  h.respond(h.requests[start + 4], { conversations: [savedConversation("replacement-conversation")], active_request: null }); await h.waitForRequests(start + 6);
  h.respond(h.requests[start + 5], historyPage("replacement-conversation", [{ id: 2, role: "assistant", content: "Replacement session answer" }]));
  await connection; await h.waitForRequests(start + 7);
  assert.equal(h.run("state.deviceId"), "replacement-device");
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["JARVIS: Replacement session answer"]);
  h.run("stopStream()"); await flush();
});

test("New conversation ignores delayed frames belonging to previously viewed conversation", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.conversation='old-conversation';row('jarvis','Old answer','old-request')");
  const change = h.run("chooseConversation(null)"); await h.waitForRequests(1);
  h.respond(h.requests[0], { conversations: [savedConversation("old-conversation")], active_request: null }); await change;
  assert.equal(h.run("state.conversation"), null); assert.equal(h.get("#log").children.length, 0);
  h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.started", request_id: "old-request", payload: { conversation_id: "old-conversation" } })});processEvent(${JSON.stringify({ cursor: 2, topic: "chat", event_type: "chat.completed", request_id: "old-request", payload: { conversation_id: "old-conversation", reply: "Delayed old answer" } })})`);
  assert.equal(h.run("state.conversation"), null);
  assert.equal(h.get("#log").children.length, 0);
  assert.equal(h.run("state.cursor"), 2);
});

test("status completing after running history snapshot renders full answer once without replay speech", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("state.pendingRequest={request_id:'race-request'}");
  const refresh = h.run("refreshHistory()"); await h.waitForRequests(1);
  const running = { request_id: "race-request", conversation_id: "synthetic-conversation", status: "running" };
  h.respond(h.requests[0], { conversations: [savedConversation()], active_request: running }); await h.waitForRequests(2);
  h.respond(h.requests[1], historyPage("synthetic-conversation", [{ id: 1, role: "user", content: "Synthetic race prompt", request_id: "race-request" }], [running]));
  await h.waitForRequests(3);
  h.respond(h.requests[2], { ...running, status: "completed", reply: "Completed between snapshot and status" }); await refresh;
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["You: Synthetic race prompt", "JARVIS: Completed between snapshot and status"]);
  assert.equal(h.run("state.pendingRequest"), null);
  assert.equal(h.get("#chat-status").textContent, "Conversation restored from Core.");
  h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.completed", request_id: "race-request", payload: { conversation_id: "synthetic-conversation", reply: "Completed between snapshot and status" } })})`);
  assert.equal(h.get("#log").children.length, 2);
  assert.equal(h.get("#chat-status").textContent, "Conversation restored from Core.");
});

test("chat POST waits for IndexedDB marker transaction commit and never runs after abort", async () => {
  for (const outcome of ["commit", "abort"]) {
    const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
    const identity = { deviceId: "synthetic-device", healthAllowed: false }; h.setIdentity(identity);
    const transaction = h.holdMarkerCommit(); h.get("#message").value = "Synthetic durable prompt";
    const send = h.run("sendMessage({preventDefault(){}})"); await flush();
    assert.equal(typeof transaction.commit, "function");
    assert.equal(h.requests.length, 0, "Request success alone must not start Core generation");
    assert.equal(h.records.has("chat-request"), false);
    assert.equal(h.records.get("device"), identity);
    if (outcome === "abort") {
      transaction.fail(); await send;
      assert.equal(h.requests.length, 0); assert.equal(h.records.has("chat-request"), false);
      assert.equal(h.get("#message").value, "Synthetic durable prompt");
      const reload = harness(h.records); await reload.ready;
      const { connection } = await connectionToHistory(reload);
      reload.respond(reload.requests[4], { conversations: [], active_request: null }); await connection; await reload.waitForRequests(6);
      assert.equal(reload.run("state.pendingRequest"), null);
      assert.equal(reload.requests.some(request => request.url === "/api/v1/client/chat"), false);
      reload.run("stopStream()"); await flush();
    } else {
      transaction.commit(); await h.waitForRequests(1);
      const id = JSON.parse(h.requests[0].options.body).request_id;
      assert.equal(h.records.get("chat-request").request_id, id);
      h.respond(h.requests[0], { request_id: id, status: "completed", conversation_id: "synthetic-conversation", reply: "Committed answer" }); await send;
    }
  }
});

test("Cancel during marker commit prevents chat POST and erases marker after commit settles", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.setIdentity({ deviceId: "synthetic-device" }); const transaction = h.holdMarkerCommit();
  h.get("#message").value = "Never send synthetic prompt";
  const send = h.run("sendMessage({preventDefault(){}})"); await flush();
  await h.run("cancelChat()");
  assert.equal(h.requests.length, 0); assert.equal(h.run("state.pendingRequest"), null);
  assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
  transaction.commit(); await send; await flush();
  assert.equal(h.requests.length, 0); assert.equal(h.records.has("chat-request"), false);
  assert.equal(h.records.get("device").deviceId, "synthetic-device");
});

test("lost Cancel acknowledgment followed by initial running result automatically retries same-ID cancellation", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic pending reservation";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const id = JSON.parse(h.requests[0].options.body).request_id;
  const cancelled = assert.rejects(h.run("cancelChat()"), /Synthetic lost cancellation/); await h.waitForRequests(2);
  assert.equal(h.requests[1].url, `/api/v1/client/chat/${encodeURIComponent(id)}/cancel`);
  h.requests[1].pending.reject(new Error("Synthetic lost cancellation")); await cancelled;
  assert.match(h.get("#chat-status").textContent, /Cancellation unconfirmed/);
  h.respond(h.requests[0], { request_id: id, status: "running", conversation_id: "synthetic-conversation" }, 202);
  await h.waitForRequests(3);
  assert.equal(h.requests[2].url, h.requests[1].url);
  assert.equal(h.requests[2].options.method, "POST");
  h.respond(h.requests[2], { request_id: id, status: "cancelled", conversation_id: "synthetic-conversation" }); await send;
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
  assert.equal(h.requests.filter(request => request.url === "/api/v1/client/chat").length, 1);
});

test("restored request marker resolves its original conversation before latest unrelated history", async () => {
  const records = new Map([
    ["device", { deviceId: "synthetic-device", healthAllowed: false }],
    ["chat-request", { deviceId: "synthetic-device", request_id: "original-request" }],
  ]);
  const h = harness(records); await h.ready;
  const original = { request_id: "original-request", conversation_id: "original-conversation", status: "completed", reply: "Original answer" };
  const { connection, listing } = await connectionToHistory(h, "synthetic-device", original);
  h.respond(h.requests[listing], { conversations: [savedConversation("latest-unrelated-conversation"), savedConversation("original-conversation")], active_request: null });
  await h.waitForRequests(listing + 2);
  assert.equal(h.requests[listing + 1].url, "/api/v1/client/conversations/original-conversation/messages?limit=50");
  h.respond(h.requests[listing + 1], historyPage("original-conversation", [
    { id: 1, role: "user", content: "Original prompt", request_id: "original-request" },
    { id: 2, role: "assistant", content: "Original answer", request_id: "original-request" },
  ], [original])); await connection; await h.waitForRequests(listing + 3);
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.run("state.conversation"), "original-conversation");
  assert.equal(h.records.has("chat-request"), false);
  respondStream(h, h.requests[listing + 2]); await h.waitForRequests(listing + 4);
  assert.equal(h.get("#send").disabled, false);
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["You: Original prompt", "JARVIS: Original answer"]);
  h.run("stopStream()"); await flush();
});

test("unknown reload marker closes request on Core before clearing marker and enabling Send", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription';state.pendingRequest={request_id:'unknown-reloaded-request'};updateControls()");
  h.records.set("chat-request", { deviceId: "synthetic-device", request_id: "unknown-reloaded-request" });
  const check = h.run("checkPendingRequest({silent:true})"); await h.waitForRequests(1);
  assert.equal(h.requests[0].url, "/api/v1/client/chat/unknown-reloaded-request?subscription_id=synthetic-subscription");
  h.respond(h.requests[0], {}, 404); await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/client/chat/unknown-reloaded-request/cancel");
  assert.equal(h.requests[1].options.method, "POST");
  assert.equal(h.run("state.pendingRequest.request_id"), "unknown-reloaded-request");
  assert.equal(h.get("#send").disabled, true);
  assert.equal(h.records.has("chat-request"), true);
  h.respond(h.requests[1], { request_id: "unknown-reloaded-request", status: "cancelled", conversation_id: null }); await check; await flush();
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.records.has("chat-request"), false);
  assert.equal(h.get("#send").disabled, false);
  assert.match(h.get("#chat-status").textContent, /Unaccepted request closed on Core.*Draft was not stored/);
  assert.equal(h.requests.some(request => request.url === "/api/v1/client/chat"), false);
});

test("failed Core tombstone keeps unknown reload marker pending and offers safe Retry", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription';state.pendingRequest={request_id:'unknown-reloaded-request'};updateControls()");
  h.records.set("chat-request", { deviceId: "synthetic-device", request_id: "unknown-reloaded-request" });
  const checked = assert.rejects(h.run("checkPendingRequest({silent:true})")); await h.waitForRequests(1);
  h.respond(h.requests[0], {}, 404); await h.waitForRequests(2); h.respond(h.requests[1], {}, 503); await checked;
  assert.equal(h.run("state.pendingRequest.request_id"), "unknown-reloaded-request");
  assert.equal(h.run("state.pendingRequest.cancelIntent"), true); assert.equal(h.records.has("chat-request"), true);
  assert.equal(h.get("#send").disabled, true); assert.equal(h.get("#retry-chat").hidden, false);
  assert.match(h.get("#chat-status").textContent, /closure unconfirmed.*retries cancellation/);
  const retry = h.run("retryChat()"); await h.waitForRequests(3);
  h.respond(h.requests[2], {}, 404); await h.waitForRequests(4);
  assert.equal(h.requests[3].url, "/api/v1/client/chat/unknown-reloaded-request/cancel");
  h.respond(h.requests[3], { request_id: "unknown-reloaded-request", status: "cancelled", conversation_id: null }); await retry; await flush();
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.records.has("chat-request"), false);
  assert.equal(h.get("#send").disabled, false);
  assert.equal(h.requests.some(request => request.url === "/api/v1/client/chat"), false);
});

test("successful event poll recovers missed terminal status using current subscription without new generation", async () => {
  const h = harness(); await h.ready; streamSession(h);
  h.run("state.conversation='synthetic-conversation';state.pendingRequest={request_id:'missed-terminal-request',lastChecked:Date.now()-2000};state.chatActive.add('missed-terminal-request');row('user','You: Missed synthetic prompt','missed-terminal-request:user')");
  h.run("startStreamOwnership()"); await h.waitForRequests(1); respondStream(h, h.requests[0]); await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/client/chat/missed-terminal-request?subscription_id=synthetic-subscription");
  assert.equal(h.get("#send").disabled, true);
  h.respond(h.requests[1], { request_id: "missed-terminal-request", status: "completed", conversation_id: "synthetic-conversation", reply: "Recovered terminal answer" });
  await h.waitForRequests(3);
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.get("#send").disabled, false);
  assert.deepEqual(h.get("#log").children.map(node => node.textContent), ["You: Missed synthetic prompt", "JARVIS: Recovered terminal answer"]);
  const announcement = h.get("#chat-status").textContent;
  respondStream(h, h.requests[2], `data: ${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.completed", request_id: "missed-terminal-request", payload: { conversation_id: "synthetic-conversation", reply: "Recovered terminal answer" } })}\n\n`);
  await h.waitForRequests(4);
  assert.equal(h.get("#log").children.length, 2); assert.equal(h.get("#chat-status").textContent, announcement);
  assert.equal(h.requests.filter(request => request.options.method === "POST").length, 0);
  h.run("stopStream()"); await flush();
});

test("uncertain send metadata cannot become assistant partial text during history restoration", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic uncertain prompt";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const id = JSON.parse(h.requests[0].options.body).request_id;
  h.requests[0].pending.reject(new Error("Synthetic lost send response")); await send;
  assert.equal(h.get("#log").children[1].className, "entry meta");
  const refresh = h.run("refreshHistory()"); await h.waitForRequests(2);
  const running = { request_id: id, conversation_id: "synthetic-conversation", status: "running" };
  h.respond(h.requests[1], { conversations: [savedConversation()], active_request: running }); await h.waitForRequests(3);
  h.respond(h.requests[2], historyPage("synthetic-conversation", [{ id: 1, role: "user", content: "Synthetic uncertain prompt", request_id: id }], [running])); await h.waitForRequests(4);
  h.respond(h.requests[3], running); await refresh;
  assert.equal(h.get("#log").children[1].className, "entry jarvis");
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Reply in progress…");
  assert.equal(h.get("#log").children.some(node => /Send outcome unconfirmed/.test(node.textContent)), false);
});

test("interrupted Core receipt clears busy request and suppresses obsolete frames without bypassing readiness", async () => {
  for (const readiness of ["ready", "history-pending", "offline"]) {
    const h = harness(); await h.ready; h.activate();
    h.run("state.subscription='synthetic-subscription';state.conversation='synthetic-conversation';state.pendingRequest={request_id:'interrupted-request'};state.chatActive.add('interrupted-request');state.chatDrafts.set('interrupted-request','Synthetic interrupted prompt');ui.chat.setAttribute('aria-busy','true');row('jarvis','JARVIS: Interrupted partial','interrupted-request')");
    h.records.set("chat-request", { deviceId: "synthetic-device", request_id: "interrupted-request" });
    if (readiness === "history-pending") h.run("state.historyReady=false");
    if (readiness === "offline") h.run("setConnected(false)");
    h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.interrupted", request_id: "interrupted-request", payload: { conversation_id: "synthetic-conversation" } })})`);
    await flush();
    assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.run("state.chatActive.size"), 0);
    assert.equal(h.run("state.chatDrafts.size"), 0); assert.equal(h.records.has("chat-request"), false);
    assert.equal(h.get("#chat").attributes["aria-busy"], "false");
    assert.equal(h.get("#log").children[0].className, "entry meta");
    assert.match(h.get("#chat-status").textContent, /Reply interrupted.*Original request will not run again/);
    const message = h.get("#chat-status").textContent;
    h.run(`processEvent(${JSON.stringify({ cursor: 2, topic: "chat", event_type: "chat.delta", request_id: "interrupted-request", payload: { conversation_id: "synthetic-conversation", content_delta: "Obsolete partial" } })});processEvent(${JSON.stringify({ cursor: 3, topic: "chat", event_type: "chat.completed", request_id: "interrupted-request", payload: { conversation_id: "synthetic-conversation", reply: "Obsolete completion" } })})`);
    assert.equal(h.get("#log").children.length, 1); assert.equal(h.get("#log").children[0].textContent, message);
    assert.equal(h.get("#chat-status").textContent, message); assert.equal(h.run("state.cursor"), 3);
    assert.equal(h.get("#send").disabled, readiness !== "ready");
    assert.equal(h.requests.length, 0, "Interrupted request cannot trigger retry generation");
  }
});

test("initial navigation accepts only three public fragments without side effects or private history", async () => {
  for (const hash of ["", "#/chat", "#/garmin", "#/settings", "#/__proto__", "#/constructor", "#/unknown?message=synthetic", "#settings"]) {
    const h = harness(new Map(), hash); await h.ready;
    const selected = ["#/chat", "#/garmin", "#/settings"].includes(hash) ? hash.slice(2) : "chat";
    assert.equal(h.run("navigation.view"), selected); assert.equal(h.location.hash, `#/${selected}`);
    for (const name of ["chat", "garmin", "settings"]) {
      assert.equal(h.get(`#view-${name}`).hidden, name !== selected);
      assert.equal(h.get(`#nav-${name}`).attributes["aria-current"], name === selected ? "page" : undefined);
    }
    assert.equal(h.context.document.activeElement, undefined, "Startup must not steal focus");
    assert.equal(h.requests.length, 0); assert.equal(h.storage.size, 0); assert.equal(h.records.size, 0);
    assert.equal(h.run("state.csrf"), null); assert.equal(h.run("state.streamOwner"), null);
    assert.deepEqual(h.historyEntries, [{ state: null, hash: `#/${selected}` }]);
  }
});

test("navigation links support keyboard clicks, modifiers, repeated selections, back and forward", async () => {
  const h = harness(); await h.ready;
  const click = (name, extra = {}) => {
    let prevented = false;
    h.get(`#nav-${name}`).listeners.click[0]({ button: 0, preventDefault() { prevented = true; }, ...extra });
    return prevented;
  };
  for (const extra of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
    assert.equal(click("settings", extra), false); assert.equal(h.run("navigation.view"), "chat");
  }
  assert.equal(click("garmin"), true); assert.equal(h.context.document.activeElement.id, "garmin-title");
  click("settings"); click("settings"); assert.equal(h.historyEntries.length, 3);
  assert.equal(h.context.document.title, "Settings · JARVIS");
  h.history.go(-1); assert.equal(h.run("navigation.view"), "garmin"); assert.equal(h.context.document.activeElement.id, "garmin-title");
  h.history.go(-1); assert.equal(h.run("navigation.view"), "chat"); assert.equal(h.context.document.activeElement.id, "chat-title");
  h.history.go(1); assert.equal(h.run("navigation.view"), "garmin");
  h.location.hash = "#/unrecognized"; h.windowEvents.hashchange();
  assert.equal(h.run("navigation.view"), "chat"); assert.equal(h.location.hash, "#/chat");
  assert.ok(h.historyEntries.every(entry => entry.state === null)); assert.equal(h.requests.length, 0);
});

test("navigation preserves one queued stream owner, session, conversation and in-memory draft", async () => {
  const h = harness(); await h.ready; streamSession(h);
  const lock = deferred(); let owners = 0;
  h.context.navigator.locks = { request: async (_, options, callback) => { owners++; await lock.promise; return callback({}); } };
  h.run("state.conversation='synthetic-conversation';startStreamOwnership()");
  const owner = h.run("state.streamOwner"), generation = h.run("state.sessionGeneration");
  h.get("#message").value = "Unsent synthetic draft";
  h.run("selectView('garmin');selectView('settings');selectView('chat')");
  assert.equal(owners, 1); assert.equal(h.requests.length, 0); assert.equal(h.run("state.streamOwner"), owner);
  assert.equal(owner.controller.signal.aborted, false); assert.equal(h.run("state.sessionGeneration"), generation);
  assert.equal(h.run("state.conversation"), "synthetic-conversation"); assert.equal(h.get("#message").value, "Unsent synthetic draft");
  lock.resolve(); await h.waitForRequests(1); h.run("selectView('settings')");
  respondStream(h, h.requests[0]); await h.waitForRequests(2);
  assert.equal(h.run("state.online"), true); assert.equal(h.get("#connection").textContent, "Connected");
  assert.equal(h.run("navigation.view"), "settings"); assert.equal(h.run("state.streamOwner"), owner);
  assert.ok(h.requests.every(request => request.url.startsWith("/api/v1/client/events?")));
  h.run("stopStream()"); await flush();
});

test("off-screen streaming retains reader position and returning to Chat shows one completed answer", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("state.subscription='synthetic-subscription';state.conversation='synthetic-conversation'");
  h.get("#message").value = "Synthetic navigation prompt";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const id = JSON.parse(h.requests[0].options.body).request_id;
  const log = h.get("#log"); log.scrollHeight = 2000; log.clientHeight = 300; log.scrollTop = 120;
  h.run("selectView('garmin')");
  // Real browsers report zero layout for hidden ancestors. Never overwrite the saved position.
  log.scrollTop = 0; log.scrollHeight = 0; log.clientHeight = 0;
  h.run(`processEvent(${JSON.stringify({ cursor: 1, topic: "chat", event_type: "chat.delta", request_id: id, payload: { content_delta: "Partial", conversation_id: "synthetic-conversation" } })})`);
  h.run("selectView('settings')");
  h.respond(h.requests[0], { request_id: id, status: "completed", conversation_id: "synthetic-conversation", reply: "One complete synthetic reply" }); await send;
  assert.equal(h.run("state.pendingRequest"), null); assert.equal(h.requests.length, 1);
  log.scrollHeight = 2400; log.clientHeight = 300;
  h.run("selectView('chat')");
  assert.equal(log.scrollTop, 120); assert.equal(h.get("#jump-latest").hidden, false);
  assert.equal(log.children.length, 2); assert.equal(log.children[1].textContent, "JARVIS: One complete synthetic reply");
  assert.equal(h.get("#message").value, ""); assert.equal(h.get("#send").disabled, false);
});

test("hidden Chat follows latest only when the reader left it at the end", async () => {
  const h = harness(); await h.ready;
  const log = h.get("#log"); log.scrollHeight = 1000; log.clientHeight = 300; log.scrollTop = 700;
  h.run("selectView('garmin')"); log.scrollTop = 0; log.scrollHeight = 0; log.clientHeight = 0;
  h.run("row('jarvis','Synthetic off-screen reply','synthetic-request')");
  log.scrollHeight = 1400; log.clientHeight = 300; h.run("selectView('chat')");
  assert.equal(log.scrollTop, 1400); assert.equal(h.get("#jump-latest").hidden, true);
});

test("navigation during uncertain Retry preserves original request and explicit Cancel behavior", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Original synthetic prompt";
  const send = h.run("sendMessage({preventDefault(){}})"); await h.waitForRequests(1);
  const original = JSON.parse(h.requests[0].options.body);
  h.run("selectView('garmin')"); h.requests[0].pending.reject(new Error("Synthetic lost acknowledgment")); await send;
  h.run("selectView('chat')"); assert.equal(h.get("#retry-chat").hidden, false);
  const retry = h.run("retryChat()"); await h.waitForRequests(2);
  h.run("selectView('settings');selectView('garmin')");
  h.respond(h.requests[1], {}, 404); await h.waitForRequests(3);
  assert.deepEqual(JSON.parse(h.requests[2].options.body), original);
  h.respond(h.requests[2], { request_id: original.request_id, conversation_id: "synthetic-conversation", status: "running" }, 202); await retry;
  h.run("selectView('chat')"); const cancel = h.run("cancelChat()"); await h.waitForRequests(4);
  h.run("selectView('settings')");
  h.respond(h.requests[3], { request_id: original.request_id, conversation_id: "synthetic-conversation", status: "cancelled" }); await cancel;
  h.run("selectView('chat')"); assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
  assert.equal(h.get("#log").children.filter(row => row.className === "entry user").length, 1);
  assert.equal(h.requests.length, 4); assert.equal(h.run("state.pendingRequest"), null);
});

test("view selection neither reads Garmin nor grants health access; an explicit refresh survives navigation", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.healthAllowed=false;updateControls();selectView('garmin')");
  assert.equal(h.requests.length, 0); assert.equal(h.get("#refresh-garmin").disabled, true);
  h.run("state.healthAllowed=true;updateControls()"); const refresh = h.run("refreshGarmin(true)");
  const controller = h.run("state.healthAbort");
  h.run("selectView('settings');selectView('chat');selectView('garmin')");
  assert.equal(h.requests.length, 1); assert.equal(h.requests[0].url, "/api/v1/client/garmin?refresh=true");
  assert.equal(h.run("state.healthAbort"), controller); assert.equal(controller.signal.aborted, false);
  h.respond(h.requests[0], h.summary(123)); await refresh;
  h.clock.now += 300000; h.run("selectView('settings');selectView('garmin')"); h.runTimer(delay => delay === 300000);
  assert.match(h.get("#garmin-state").textContent, /Stale/); assert.equal(h.requests.length, 1);
});

test("offline navigation keeps chat disabled and preserves the same recovery stream owner", async () => {
  const h = harness(); await h.ready; streamSession(h); h.run("startStreamOwnership()"); await h.waitForRequests(1);
  const owner = h.run("state.streamOwner");
  h.context.navigator.onLine = false; h.windowEvents.offline(); await flush();
  h.run("selectView('settings');selectView('garmin');selectView('chat')");
  assert.equal(h.requests.length, 1); assert.equal(h.get("#send").disabled, true); assert.equal(h.get("#connection").textContent, "Network offline");
  h.context.navigator.onLine = true; h.windowEvents.online(); await h.waitForRequests(2);
  assert.equal(h.run("state.streamOwner"), owner); assert.equal(h.get("#send").disabled, true);
  h.run("selectView('garmin')"); respondStream(h, h.requests[1]); await h.waitForRequests(3);
  assert.equal(h.get("#connection").textContent, "Connected"); h.run("selectView('chat')");
  assert.equal(h.get("#send").disabled, false); h.run("stopStream()"); await flush();
});

test("logout erases hidden views and late results cannot resurrect them through back navigation", async () => {
  const h = harness(); await h.ready; h.activate(); h.setIdentity({ deviceId: "synthetic-device" });
  h.get("#message").value = "Synthetic private draft";
  const garmin = h.run("refreshGarmin(true)"), status = h.run("refreshStatus()"), tasks = h.run("refreshTasks()");
  h.run("selectView('garmin');selectView('settings')"); await h.run("logout()");
  assert.equal(h.run("navigation.view"), "settings"); assert.equal(h.context.document.activeElement.id, "ticket");
  h.respond(h.requests[0], h.summary(999)); h.respond(h.requests[1], { device: { display_name: "Obsolete" }, session: { id: "old" } }); h.respond(h.requests[2], [{ id: "obsolete-task", status: "running" }]);
  await Promise.all([garmin, status, tasks]); h.history.go(-1); h.history.go(-1);
  for (const id of ["garmin-metrics", "garmin-activities", "device-status", "tasks", "log"]) assert.equal(h.get(`#${id}`).children.length, 0);
  assert.equal(h.get("#message").value, ""); assert.equal(h.run("state.csrf"), null); assert.equal(h.get("#send").disabled, true);
  assert.equal(h.records.size, 0); assert.equal(h.requests.length, 4);
  h.respond(h.requests[3], {}); await flush();
});

test("late logout cleanup cannot hide a newer view or focus an invisible ticket", async () => {
  const h = harness(); await h.ready; h.activate();
  const cleanup = deferred(); h.context.navigator.serviceWorker = { getRegistrations: () => cleanup.promise };
  const logout = h.run("logout()"); await flush(); h.run("selectView('chat')");
  cleanup.resolve([]); await logout;
  assert.equal(h.run("navigation.view"), "chat"); assert.equal(h.context.document.activeElement.id, "chat-title");
  assert.equal(h.get("#view-settings").hidden, true); h.respond(h.requests[0], {}); await flush();
});
