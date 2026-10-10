const API="/api/v1";
const DB_NAME="jarvis-private-client";
const STORE="identity";
const SCOPES=["browser.session","identity.read","events.read","session.revoke","client.chat","client.tasks.read","client.status.read"];
const HEALTH_SCOPE="client.health.read";
const encoder=new TextEncoder();
const state={csrf:null,subscription:null,cursor:0,conversation:null,online:false,stopping:false,streamAbort:null,streamOwner:null,streamWake:null,hasIdentity:false,sessionGeneration:0,logoutPending:null,bootstrap:null,identityWrite:null,connecting:false,enrolling:false,sending:false,tasksBusy:false,healthAllowed:false,healthGeneration:0,healthAbort:null,healthSnapshot:null,healthTimer:null,healthMessage:"",chatActive:new Set(),chatAnnounced:new Map(),chatDrafts:new Map()};
const ui=Object.fromEntries(Object.entries({connection:"connection",setup:"setup",ticket:"ticket",ticketError:"ticket-error",accessStatus:"access-status",enroll:"enroll",connect:"connect",notify:"notify",logout:"logout",chat:"chat",chatStatus:"chat-status",message:"message",send:"send",log:"log",jumpLatest:"jump-latest",tasks:"tasks",taskPanel:"task-panel",tasksState:"tasks-state",refreshTasks:"refresh-tasks",device:"device-status",notice:"notice",garmin:"garmin",refreshGarmin:"refresh-garmin",garminState:"garmin-state",garminMetrics:"garmin-metrics",garminActivities:"garmin-activities"}).map(([name,id])=>[name,document.querySelector(`#${id}`)]));

function renderGarmin(summary){
  ui.garminMetrics.replaceChildren();
  const values=[["Steps",summary.steps],["Resting heart rate",summary.resting_heart_rate==null?null:`${summary.resting_heart_rate} bpm`],["Sleep",summary.sleep_minutes==null?null:`${Math.floor(summary.sleep_minutes/60)}h ${summary.sleep_minutes%60}m`],["Stress",summary.stress],["Body Battery",summary.body_battery]];
  for(const [label,value] of values){const card=document.createElement("div"),dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value==null?"Unavailable":String(value);card.append(dt,dd);ui.garminMetrics.append(card);}
  ui.garminActivities.replaceChildren();
  for(const activity of summary.activities||[]){const item=document.createElement("li");item.textContent=`${activity.name} · ${activity.type}${activity.started?` · ${activity.started.slice(0,10)}`:""}`;ui.garminActivities.append(item);}
  if(!ui.garminActivities.children.length){const item=document.createElement("li");item.textContent="No recent activities.";ui.garminActivities.append(item);}
  state.healthSnapshot={date:summary.date,refreshed:Date.parse(summary.refreshed_at)};state.healthMessage="";renderGarminStatus();
}
function renderGarminStatus(){
  clearTimeout(state.healthTimer);state.healthTimer=null;
  const snapshot=state.healthSnapshot;
  if(!snapshot){if(state.healthMessage)ui.garminState.textContent=state.healthMessage;return;}
  const age=Date.now()-snapshot.refreshed,valid=Number.isFinite(snapshot.refreshed),stale=!valid||age<0||age>=300000;
  const checked=valid?new Date(snapshot.refreshed).toLocaleString():"Unknown";
  ui.garminState.textContent=`${state.healthMessage?state.healthMessage+" ":""}${snapshot.date} · last checked ${checked}${stale?" · Stale. Refresh Garmin to check current data.":""}`;
  if(!stale)state.healthTimer=setTimeout(renderGarminStatus,300000-age);
}
function cancelGarmin(){state.healthGeneration+=1;state.healthAbort?.abort();state.healthAbort=null;}
function clearGarmin(){
  cancelGarmin();clearTimeout(state.healthTimer);state.healthTimer=null;state.healthSnapshot=null;state.healthMessage="";state.healthAllowed=false;
  ui.refreshGarmin.disabled=true;ui.garmin.setAttribute("aria-busy","false");ui.garminMetrics.replaceChildren();ui.garminActivities.replaceChildren();ui.garminState.textContent="Connect JARVIS to see Garmin data.";
}
async function refreshGarmin(force){
  if(!state.online||!state.healthAllowed)return;
  cancelGarmin();
  const generation=state.healthGeneration,csrf=state.csrf,controller=new AbortController();state.healthAbort=controller;
  const current=()=>generation===state.healthGeneration&&state.csrf===csrf&&state.online&&state.healthAllowed&&!controller.signal.aborted;
  state.healthMessage="Checking Garmin…";renderGarminStatus();updateControls();
  try{const summary=await (await api(`/client/garmin${force?"?refresh=true":""}`,{signal:controller.signal})).json();if(current())renderGarmin(summary);}
  catch(error){if(current()&&error.name!=="AbortError"){
    const message=error.status===503?"Garmin unavailable. Try again later; if it continues, check Garmin status on your trusted laptop.":"Garmin check failed. Try again after connection recovers.";
    state.healthMessage=message+(ui.garminMetrics.children.length?" Shown Garmin data may be stale.":"");renderGarminStatus();
  }}finally{if(state.healthAbort===controller)state.healthAbort=null;updateControls();}
}
ui.refreshGarmin.addEventListener("click",()=>refreshGarmin(true));
function b64url(bytes){return btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+","-").replaceAll("/","_").replaceAll("=","");}
function randomId(prefix){return `${prefix}:${crypto.randomUUID()}`;}
function proof(profile,...values){let text=`${profile}\n`;for(const value of values){const bytes=encoder.encode(String(value));text+=`${bytes.length}:${value}\n`;}return encoder.encode(text);}
async function digest(value){return b64url(await crypto.subtle.digest("SHA-256",value));}
function timestamp(){return new Date().toISOString().replace(/\.(\d{3})Z$/,".$1000Z");}
async function canonical({method,path,query="",body,identity,date,nonce}){
  const bodyDigest=await digest(body),components=[["@method",method.toUpperCase()],["@authority",location.host.toLowerCase()],["@path",path],["@query",query],["content-digest",`sha-256=:${bodyDigest}:`],["x-jarvis-date",date],["x-jarvis-nonce",nonce],["x-jarvis-audience","jarvis-api"],["x-jarvis-device",identity.deviceId],["x-jarvis-key-version",String(identity.keyVersion)],["authorization-digest","-"]];
  let text="jarvis-http-signature-v1\n";for(const [name,value] of components)text+=`${name}:${encoder.encode(value).length}:${value}\n`;return encoder.encode(text);
}
async function signedHeaders(identity,method,path,body){const date=timestamp(),nonce=b64url(crypto.getRandomValues(new Uint8Array(16))),signature=b64url(await crypto.subtle.sign("Ed25519",identity.privateKey,await canonical({method,path,body,identity,date,nonce})));return {"Content-Type":"application/json","X-Jarvis-Audience":"jarvis-api","X-Jarvis-Date":date,"X-Jarvis-Device":identity.deviceId,"X-Jarvis-Key-Version":String(identity.keyVersion),"X-Jarvis-Nonce":nonce,"X-Jarvis-Signature":signature};}
function openDb(){return new Promise((resolve,reject)=>{const request=indexedDB.open(DB_NAME,1);request.onupgradeneeded=()=>request.result.createObjectStore(STORE);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}
async function dbAction(mode,operation){const db=await openDb();return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,mode),store=tx.objectStore(STORE);let request;try{request=operation(store);}catch(error){db.close();reject(error);return;}request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);tx.oncomplete=()=>db.close();tx.onerror=()=>reject(tx.error);});}
const loadIdentity=()=>dbAction("readonly",store=>store.get("device"));
const saveIdentity=value=>dbAction("readwrite",store=>store.put(value,"device"));
const clearIdentity=()=>dbAction("readwrite",store=>store.clear());
class ApiError extends Error{constructor(message,status){super(message);this.status=status;}}
function currentSession(generation,csrf){return state.sessionGeneration===generation&&state.csrf===csrf;}
function revokeRemoteSession(csrf){const controller=new AbortController();return new Promise(resolve=>{let settled=false;const finish=confirmed=>{if(settled)return;settled=true;clearTimeout(timer);resolve(confirmed===true);},timer=setTimeout(()=>{controller.abort();finish(false);},5000);fetch(`${API}/sessions/current`,{method:"DELETE",credentials:"include",cache:"no-store",headers:{"X-Jarvis-CSRF":csrf},signal:controller.signal}).then(response=>finish(response.ok),()=>finish(false));});}
function startBootstrap(headers,body){const controller=new AbortController(),bootstrap={controller,headersReceived:false,promise:null};let timer;const request=(async()=>{const response=await fetch(`${API}/browser/sessions`,{method:"POST",credentials:"include",cache:"no-store",headers,body,signal:controller.signal});bootstrap.headersReceived=true;if(!response.ok)throw new Error(`Session bootstrap rejected (${response.status})`);return response.json();})();bootstrap.promise=Promise.race([request,new Promise((resolve,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error("Session bootstrap timed out"));},5000);})]).finally(()=>clearTimeout(timer));return bootstrap;}
// Bound both response headers and body consumption, even when a transport ignores abort.
async function timedFetch(url,options={},timeout=10000){
  const controller=new AbortController(),external=options.signal;
  let timer,rejectDeadline;
  const deadline=new Promise((resolve,reject)=>{rejectDeadline=reject;timer=setTimeout(()=>{controller.abort();reject(new Error("Request timed out. Reconnect and check before retrying."));},timeout);});
  const abort=()=>{controller.abort();rejectDeadline(new DOMException("Request aborted","AbortError"));};
  external?.addEventListener("abort",abort,{once:true});
  if(external?.aborted)abort();
  const cleanup=()=>{clearTimeout(timer);external?.removeEventListener("abort",abort);};
  try{
    const response=await Promise.race([fetch(url,{...options,signal:controller.signal}),deadline]);
    const consume=async method=>{try{return await Promise.race([response[method](),deadline]);}finally{cleanup();}};
    return {ok:response.ok,status:response.status,json:()=>consume("json"),text:()=>consume("text"),discard:cleanup};
  }catch(error){cleanup();throw error;}
}
function stopStream(){
  state.stopping=true;
  if(state.streamOwner){state.streamOwner.cancelled=true;state.streamOwner.controller.abort();}
  state.streamAbort?.abort();
  state.streamWake?.();
  state.streamOwner=null;
}
function invalidateSession(label="Session expired",guidance="Session expired. Connect existing device to renew. If rejected, ask your trusted host for device recovery."){
  ++state.sessionGeneration;stopStream();state.csrf=null;state.subscription=null;state.cursor=0;state.conversation=null;
  clearGarmin();state.connecting=false;state.sending=false;state.tasksBusy=false;state.chatActive.clear();state.chatAnnounced.clear();state.chatDrafts.clear();ui.chat.setAttribute("aria-busy","false");ui.chatStatus.textContent="";ui.tasksState.textContent="";
  ui.device.replaceChildren();ui.tasks.replaceChildren();ui.log.replaceChildren();ui.jumpLatest.hidden=true;
  for(const key of ["jarvis-subscription","jarvis-cursor"])sessionStorage.removeItem(key);
  setConnected(false,label);ui.accessStatus.textContent=guidance;announce(guidance);
}
async function api(path,options={}){
  const headers={...(options.headers||{})},method=options.method||"GET",csrf=state.csrf,generation=state.sessionGeneration;
  if(method==="GET")headers["X-Jarvis-Browser-Origin"]=window.location.origin;
  if(method!=="GET"&&state.csrf)headers["X-Jarvis-CSRF"]=state.csrf;
  const timeout=path.startsWith("/client/events?")?30000:path.startsWith("/client/garmin")?95000:10000;
  const response=await timedFetch(`${API}${path}`,{credentials:"include",cache:"no-store",...options,headers},timeout);
  if(options.signal?.aborted){response.discard();throw new DOMException("Request aborted","AbortError");}
  if(response.status===401){response.discard();if(currentSession(generation,csrf))invalidateSession();throw new ApiError("Session expired",401);}
  if(!response.ok){let detail=`HTTP ${response.status}`;try{detail=(await response.json()).detail||detail;}catch{}throw new ApiError(detail,response.status);}
  return response;
}
function updateControls(){
  for(const element of [ui.message,ui.notify])element.disabled=!state.online;
  ui.send.disabled=!state.online||Boolean(state.sending);
  ui.refreshTasks.disabled=!state.online||Boolean(state.tasksBusy);
  ui.refreshGarmin.disabled=!state.online||!state.healthAllowed||Boolean(state.healthAbort);
  ui.enroll.disabled=state.hasIdentity||Boolean(state.enrolling)||Boolean(state.connecting);
  ui.connect.disabled=Boolean(state.enrolling)||Boolean(state.connecting);
  ui.logout.disabled=!state.hasIdentity;
  ui.setup.setAttribute("aria-busy",String(Boolean(state.enrolling||state.connecting)));
  ui.garmin.setAttribute("aria-busy",String(Boolean(state.healthAbort)));
  ui.taskPanel.setAttribute("aria-busy",String(Boolean(state.tasksBusy)));
}
function setConnected(value,label=value?"Connected":"Offline shell"){
  state.online=value&&navigator.onLine;
  const connectionText=navigator.onLine?label:"Network offline";
  if(ui.connection.textContent!==connectionText)ui.connection.textContent=connectionText;
  ui.connection.className=`status ${state.online?"online":navigator.onLine?"warn":""}`;
  if(!state.online){cancelGarmin();if(state.healthAllowed){state.healthMessage=navigator.onLine?"Connection unavailable. Shown Garmin data may be stale.":"Offline. Shown Garmin data may be stale.";renderGarminStatus();}}
  else if(/^(Offline\.|Connection unavailable\.)/.test(state.healthMessage)){state.healthMessage="";renderGarminStatus();}
  updateControls();
}
function announce(message){ui.notice.textContent=message;}
function nearLatest(){return ui.log.scrollHeight-ui.log.clientHeight-ui.log.scrollTop<=48;}
function historySelected(){const selection=document.getSelection?.();return Boolean(selection&&!selection.isCollapsed&&ui.log.contains(selection.anchorNode));}
function updateJump(){ui.jumpLatest.hidden=nearLatest()&&!historySelected();}
function row(kind,text,requestId){
  const follow=nearLatest()&&!historySelected();
  let target=requestId?ui.log.querySelector(`[data-request="${CSS.escape(requestId)}"]`):null;
  if(!target){target=document.createElement("div");target.className=`entry ${kind}`;if(requestId)target.dataset.request=requestId;ui.log.append(target);}
  target.className=`entry ${kind}`;
  const previous=target.textContent,textNode=target.firstChild;
  // Append deltas to the existing text node so selected reply text survives streaming.
  if(text!==previous){
    if(textNode?.nodeType===3&&target.childNodes.length===1&&text.startsWith(previous))textNode.appendData(text.slice(previous.length));
    else target.textContent=text;
  }
  if(follow)ui.log.scrollTop=ui.log.scrollHeight;
  ui.jumpLatest.hidden=follow&&nearLatest();
  return target;
}
ui.log.addEventListener("scroll",updateJump);
ui.jumpLatest.addEventListener("click",()=>{ui.log.scrollTop=ui.log.scrollHeight;ui.jumpLatest.hidden=true;ui.log.focus({preventScroll:true});});
function completeReply(id,message,completed=false){
  state.chatActive.delete(id);ui.chat.setAttribute("aria-busy",String(state.chatActive.size>0));
  if(state.chatAnnounced.has(id))return;
  state.chatAnnounced.set(id,completed);
  if(completed&&state.chatDrafts.has(id)&&ui.message.value.trim()===state.chatDrafts.get(id))ui.message.value="";
  state.chatDrafts.delete(id);
  ui.chatStatus.textContent=message;
  if(completed)notifyGeneric();
}

async function enrollDevice(){if(state.hasIdentity)throw new Error("Log out and erase this device before re-enrollment");const generation=++state.sessionGeneration,current=()=>state.sessionGeneration===generation;if(state.logoutPending)await state.logoutPending;if(!current())return;if(!crypto.subtle||!window.indexedDB)throw new Error("Secure browser cryptography unavailable");const existing=await loadIdentity();if(!current())return;if(existing)throw new Error("Log out and erase this device before re-enrollment");let ticket;try{ticket=JSON.parse(ui.ticket.value);}catch{throw new Error("Enrollment ticket must be complete JSON");}if(!ticket||typeof ticket!=="object")throw new Error("Enrollment ticket is incomplete");for(const key of ["id","challenge"]){if(typeof ticket[key]!=="string")throw new Error("Enrollment ticket is incomplete");}const pair=await crypto.subtle.generateKey("Ed25519",false,["sign","verify"]),publicKey=b64url(await crypto.subtle.exportKey("raw",pair.publicKey)),proofSignature=b64url(await crypto.subtle.sign("Ed25519",pair.privateKey,proof("jarvis-enrollment-v1",ticket.id,ticket.challenge,publicKey,"1")));if(!current())return;const response=await timedFetch(`${API}/enrollments/complete`,{method:"POST",credentials:"omit",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({enrollment_id:ticket.id,challenge:ticket.challenge,public_key:publicKey,proof_signature:proofSignature,protocol_version:"1"})});if(!current())return;if(!response.ok){response.discard();throw new Error("Enrollment rejected");}const device=await response.json();if(!current())return;const write=saveIdentity({privateKey:pair.privateKey,deviceId:device.id,keyVersion:device.key_version,healthAllowed:Array.isArray(ticket.approved_scopes)&&ticket.approved_scopes.includes(HEALTH_SCOPE)});state.identityWrite=write;try{await write;}finally{if(state.identityWrite===write)state.identityWrite=null;}if(!current())return;state.hasIdentity=true;ui.ticket.value="";await connect();}
async function enroll(){
  if(state.hasIdentity)throw new Error("Log out and erase this device before re-enrollment");
  if(state.enrolling)return;
  const operation={};state.enrolling=operation;ui.ticketError.textContent="";ui.ticket.removeAttribute("aria-invalid");updateControls();
  try{await enrollDevice();}
  catch(error){
    if(state.enrolling===operation&&!state.hasIdentity){ui.ticket.setAttribute("aria-invalid","true");ui.ticketError.textContent="Enrollment failed. Use complete JSON from an approved, unexpired, unused ticket. If rejected, request a new ticket on your trusted host.";announce(ui.ticketError.textContent);}
    throw error;
  }finally{if(state.enrolling===operation)state.enrolling=false;updateControls();}
}
async function createSubscription(){const generation=state.sessionGeneration,csrf=state.csrf,subscription=await (await api("/client/subscriptions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({topics:["chat","tasks","device"]})})).json();if(!currentSession(generation,csrf))return;state.subscription=subscription.id;state.cursor=subscription.next_cursor;sessionStorage.setItem("jarvis-subscription",state.subscription);sessionStorage.setItem("jarvis-cursor",String(state.cursor));}
async function resetSubscription(){const generation=state.sessionGeneration,csrf=state.csrf,previous=state.subscription;if(previous){try{(await api(`/client/subscriptions/${encodeURIComponent(previous)}`,{method:"DELETE"})).discard();}catch{}}if(currentSession(generation,csrf))await createSubscription();}
async function connect(){
  if(state.connecting)return;
  const generation=++state.sessionGeneration,current=()=>state.sessionGeneration===generation;
  state.connecting=generation;clearGarmin();stopStream();state.csrf=null;state.subscription=null;setConnected(false,"Connecting");
  ui.accessStatus.textContent="Connecting existing device. Chat stays disabled until live transport is ready.";
  try{
    if(state.logoutPending)await state.logoutPending;if(!current())return;
    const previous=state.bootstrap;
    if(previous){if(!previous.headersReceived)previous.controller.abort();try{await previous.promise;}catch{}if(!current())return;}
    const identity=await loadIdentity();if(!current())return;
    if(!identity)throw new Error("No enrolled device key in this browser. Paste an approved, unexpired ticket to enroll.");
    state.hasIdentity=true;
    const path="/browser/sessions",requestedScopes=identity.healthAllowed?[...SCOPES,HEALTH_SCOPE]:SCOPES;
    const body=encoder.encode(JSON.stringify({requested_scopes:requestedScopes,audience:"jarvis-api"})),headers=await signedHeaders(identity,"POST",`${API}${path}`,body);
    if(!current())return;
    const bootstrap=startBootstrap(headers,body);state.bootstrap=bootstrap;
    let credential;
    try{credential=await bootstrap.promise;}finally{if(state.bootstrap===bootstrap)state.bootstrap=null;}
    if(!current())return;
    state.csrf=credential.csrf_token;state.healthAllowed=Boolean(identity.healthAllowed);
    await createSubscription();if(!current())return;
    await refreshStatus();if(!current())return;
    await refreshTasks();if(!current())return;
    if(!state.healthAllowed)ui.garminState.textContent="Garmin access needs a new approved browser enrollment.";
    setConnected(false,"Checking live connection");
    ui.accessStatus.textContent="Checking live connection. Use Connect existing device if recovery stalls.";
  }catch(error){
    if(current()){
      stopStream();state.csrf=null;state.subscription=null;clearGarmin();setConnected(false,"Connection failed");
      ui.accessStatus.textContent=state.hasIdentity?"Connection failed. Retry Connect existing device. If access is rejected, request approved recovery on your trusted host.":"No enrolled key. Paste an approved, unexpired ticket to enroll.";
      announce(ui.accessStatus.textContent);
      throw error;
    }
  }finally{if(state.connecting===generation)state.connecting=false;updateControls();}
  if(current())startStreamOwnership();
}
async function refreshStatus(){const generation=state.sessionGeneration,csrf=state.csrf,status=await (await api("/client/status")).json();if(!currentSession(generation,csrf))return;ui.device.replaceChildren();const entries=[["Name",status.device.display_name],["State",status.device.state],["Key version",status.device.key_version],["Session",status.session.id]];for(const [name,value] of entries){const wrap=document.createElement("div"),dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=String(value);wrap.append(dt,dd);ui.device.append(wrap);}}
async function refreshTasks(){
  if(state.tasksBusy)return;
  const generation=state.sessionGeneration,csrf=state.csrf;const operation={};state.tasksBusy=operation;ui.tasksState.textContent="Checking tasks…";updateControls();
  try{
    const tasks=await (await api("/client/tasks?limit=50")).json();if(!currentSession(generation,csrf))return;
    ui.tasks.replaceChildren();
    if(!tasks.length){const item=document.createElement("li");item.textContent="No tasks.";ui.tasks.append(item);}
    for(const task of tasks){const item=document.createElement("li");item.textContent=`${task.id} — ${task.status}`;ui.tasks.append(item);}
    ui.tasksState.textContent="Tasks checked.";
  }catch(error){if(currentSession(generation,csrf))ui.tasksState.textContent="Task check failed. Refresh tasks after connection recovers.";throw error;}
  finally{if(state.tasksBusy===operation)state.tasksBusy=false;updateControls();}
}
function processEvent(event){
  if(!Number.isInteger(event.cursor)||event.cursor<1)throw new Error("Invalid event cursor");
  if(event.cursor<=state.cursor)return;
  if(event.cursor!==state.cursor+1)throw new Error("Event cursor gap");
  state.cursor=event.cursor;sessionStorage.setItem("jarvis-cursor",String(state.cursor));
  if(event.topic==="chat"){
    const id=event.request_id;
    // HTTP completion and replayed stream frames share one reply/announcement identity.
    if(state.chatAnnounced.has(id))return;
    if(event.event_type==="chat.started"){state.chatActive.add(id);ui.chat.setAttribute("aria-busy","true");row("jarvis","JARVIS: ",id);ui.chatStatus.textContent="JARVIS is replying.";}
    if(event.event_type==="chat.delta"||event.event_type==="chat.frame"&&event.payload.type==="assistant_delta"){
      const existing=ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`);
      const prior=existing?.className==="entry jarvis"?existing.textContent:"JARVIS: ";
      row("jarvis",prior+(event.payload.content_delta||""),id);
    }
    if(event.event_type==="chat.completed"){
      state.conversation=event.payload.conversation_id||state.conversation;
      const answer=ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`)?.textContent||"Reply available in conversation.";
      completeReply(id,`Reply complete. ${answer}`,true);
    }
    if(event.event_type==="chat.failed"||event.event_type==="chat.cancelled"){
      const message=event.event_type==="chat.cancelled"?"Request cancelled.":"Request failed safely.";
      row("meta",message,id);completeReply(id,message);
    }
  }
  if(event.topic==="tasks")refreshTasks().catch(()=>{});
}
function parseSse(text){for(const block of text.split("\n\n")){const line=block.split("\n").find(item=>item.startsWith("data: "));if(line)processEvent(JSON.parse(line.slice(6)));}}
function streamPause(delay){
  return new Promise(resolve=>{
    const finish=()=>{clearTimeout(timer);if(state.streamWake===finish)state.streamWake=null;resolve();};
    const timer=setTimeout(finish,delay);state.streamWake=finish;
  });
}
async function streamLoop(owner){
  const generation=state.sessionGeneration,csrf=state.csrf;
  const current=()=>currentSession(generation,csrf)&&!state.stopping&&(!owner||state.streamOwner===owner&&!owner.cancelled);
  while(current()&&state.csrf&&state.subscription){
    if(!navigator.onLine){await streamPause(1500);continue;}
    const controller=new AbortController();state.streamAbort=controller;
    try{
      const query=new URLSearchParams({subscription_id:state.subscription,after:String(state.cursor),limit:"100",wait:"20"});
      const response=await api(`/client/events?${query}`,{signal:controller.signal}),text=await response.text();
      if(!current())break;
      if(controller.signal.aborted||!navigator.onLine)continue;
      parseSse(text);
      setConnected(true);
      const readyText="Live connection ready. Enrolled key retained; use Connect existing device for session renewal.";
      if(ui.accessStatus.textContent!==readyText)ui.accessStatus.textContent=readyText;
      if(owner?.healthPending){owner.healthPending=false;refreshGarmin(false).catch(()=>{});}
    }catch(error){
      if(!current())break;
      if(error.status===401||error.status===403){invalidateSession("Access denied","Live access denied. Connect existing device; if rejected, request approved recovery on your trusted host.");break;}
      setConnected(false,"Reconnecting");
      if(error.status===404||error.status===409){
        try{await resetSubscription();if(!current())break;announce("Stream restarted. Checking live connection.");continue;}catch(restartError){if(!current())break;if(restartError.status===403){invalidateSession("Access denied","Stream access denied. Review approved device access on your trusted host.");break;}}
      }
      await streamPause(Math.min(5000,500+Math.random()*1500));
    }finally{if(state.streamAbort===controller)state.streamAbort=null;}
  }
}
function startStreamOwnership(){
  if(!state.csrf||!state.subscription||state.connecting)return;
  if(state.streamOwner){state.streamWake?.();return state.streamOwner.promise;}
  state.stopping=false;
  const owner={generation:state.sessionGeneration,controller:new AbortController(),cancelled:false,promise:null,healthPending:state.healthAllowed&&!state.healthSnapshot};state.streamOwner=owner;
  const run=async()=>{if(state.streamOwner!==owner||owner.cancelled)return;await streamLoop(owner);};
  if(navigator.locks){setConnected(false,"Waiting for live stream");ui.accessStatus.textContent="Waiting for live stream. Another tab may own it; close that tab or retry Connect existing device.";}
  const request=(()=>{try{return navigator.locks
    ?navigator.locks.request("jarvis-pwa-stream",{signal:owner.controller.signal},async lock=>{if(lock)await run();})
    :run();}catch(error){return Promise.reject(error);}})();
  owner.promise=Promise.resolve(request).catch(error=>{
    if(state.streamOwner===owner&&!owner.cancelled){setConnected(false,"Stream unavailable");announce("Live stream unavailable. Connect existing device to retry.");}
  }).finally(()=>{if(state.streamOwner===owner){state.streamOwner=null;if(state.online)setConnected(false,"Stream stopped");}});
  return owner.promise;
}
async function sendMessage(event){
  event.preventDefault();if(!state.online||!state.subscription||state.sending)return;
  const generation=state.sessionGeneration,csrf=state.csrf,message=ui.message.value.trim();if(!message)return;
  const requestId=randomId("request");row("user",`You: ${message}`);const operation={};state.sending=operation;state.chatActive.add(requestId);state.chatDrafts.set(requestId,message);
  ui.chat.setAttribute("aria-busy","true");ui.chatStatus.textContent="Sending message…";updateControls();
  try{
    const response=await api("/client/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request_id:requestId,subscription_id:state.subscription,message,conversation_id:state.conversation})});
    const result=await response.json();if(!currentSession(generation,csrf))return;
    state.conversation=result.conversation_id||state.conversation;
    if(ui.message.value.trim()===message)ui.message.value="";
    state.chatDrafts.delete(requestId);
    if(response.status!==202){
      row("jarvis",`JARVIS: ${result.reply||"Completed"}`,requestId);
      completeReply(requestId,`Reply complete. ${ui.log.querySelector(`[data-request="${CSS.escape(requestId)}"]`)?.textContent||result.reply||"Completed"}`,true);
    }else if(!state.chatAnnounced.has(requestId))ui.chatStatus.textContent="Message accepted. Waiting for JARVIS.";
  }catch(error){
    if(currentSession(generation,csrf)){
      if(state.chatAnnounced.get(requestId)===true){if(ui.message.value.trim()===message)ui.message.value="";}
      else if(!state.chatAnnounced.has(requestId)){
        row("meta","Send outcome unconfirmed. Reconnect and review conversation before sending again. Your draft is kept.",requestId);
        state.chatActive.delete(requestId);ui.chat.setAttribute("aria-busy",String(state.chatActive.size>0));
        ui.chatStatus.textContent="Send outcome unconfirmed. Draft kept. Reconnect and review conversation before sending again.";
      }
    }
  }finally{if(state.sending===operation)state.sending=false;updateControls();}
}
async function enableNotifications(){const generation=state.sessionGeneration,csrf=state.csrf;if(!("Notification" in window))throw new Error("Notifications unsupported");const permission=await Notification.requestPermission();if(!currentSession(generation,csrf))return;if(permission!=="granted")throw new Error("Notification permission denied");sessionStorage.setItem("jarvis-notifications","enabled");ui.notify.textContent="Notifications enabled";announce("Notifications contain generic text only");}
function notifyGeneric(){if(sessionStorage.getItem("jarvis-notifications")==="enabled"&&document.hidden&&Notification.permission==="granted")new Notification("JARVIS",{body:"JARVIS has an update.",tag:"jarvis-update",renotify:false,silent:true});}
async function logout(){
  const csrf=state.csrf,generation=++state.sessionGeneration,bootstrap=state.bootstrap,write=state.identityWrite,previous=state.logoutPending;
  clearGarmin();stopStream();if(bootstrap&&!bootstrap.headersReceived)bootstrap.controller.abort();
  state.csrf=null;state.subscription=null;state.cursor=0;state.conversation=null;state.hasIdentity=false;
  state.connecting=false;state.enrolling=false;state.sending=false;state.tasksBusy=false;state.chatActive.clear();state.chatAnnounced.clear();state.chatDrafts.clear();
  ui.chat.setAttribute("aria-busy","false");ui.chatStatus.textContent="";ui.tasksState.textContent="";ui.ticketError.textContent="";ui.ticket.removeAttribute("aria-invalid");
  ui.device.replaceChildren();ui.tasks.replaceChildren();ui.log.replaceChildren();ui.jumpLatest.hidden=true;ui.message.value="";ui.ticket.value="";
  setConnected(false,"Logging out");ui.accessStatus.textContent="Erasing local device access. Server sign-out is pending.";
  for(const key of ["jarvis-subscription","jarvis-cursor","jarvis-notifications"])sessionStorage.removeItem(key);
  const remote=csrf?revokeRemoteSession(csrf):Promise.resolve(false);
  const bootstrapCleanup=bootstrap?bootstrap.promise.then(credential=>revokeRemoteSession(credential.csrf_token),()=>false):Promise.resolve(true);
  const local=(async()=>{
    if(write){try{await write;}catch{}}await clearIdentity();
    for(const registration of await navigator.serviceWorker?.getRegistrations?.()||[]){registration.active?.postMessage("JARVIS_LOGOUT");await registration.unregister();}
    for(const key of await caches.keys())if(key.startsWith("jarvis-shell-"))await caches.delete(key);
    if(state.sessionGeneration===generation){
      setConnected(false,"Logged out — device key erased");
      ui.accessStatus.textContent="Local device key and displayed data erased. Server sign-out pending. New access needs an approved enrollment ticket.";
      announce(ui.accessStatus.textContent);ui.ticket.focus();
    }
  })();
  const pending=Promise.allSettled([previous,remote,bootstrapCleanup,local]);state.logoutPending=pending;
  pending.then(results=>{
    if(state.logoutPending===pending)state.logoutPending=null;
    if(state.sessionGeneration!==generation||results[3].status!=="fulfilled")return;
    const confirmed=results[1].status==="fulfilled"&&results[1].value===true&&results[2].status==="fulfilled"&&results[2].value===true;
    ui.accessStatus.textContent=`Local device key and displayed data erased. Server sign-out ${confirmed?"confirmed":"unconfirmed; session expiry or trusted-host device revocation may still be needed"}. Device enrollment remains on Core. New access needs an approved ticket.`;
    announce(ui.accessStatus.textContent);
  });
  await local;
}
async function guarded(action){try{await action();}catch(error){announce(error.message||"Operation failed safely");}}

ui.enroll.addEventListener("click",()=>guarded(enroll));ui.connect.addEventListener("click",()=>guarded(connect));ui.chat.addEventListener("submit",sendMessage);ui.notify.addEventListener("click",()=>guarded(enableNotifications));ui.logout.addEventListener("click",()=>guarded(logout));ui.refreshTasks.addEventListener("click",()=>guarded(refreshTasks));
window.addEventListener("offline",()=>{state.streamAbort?.abort();setConnected(false,"Network offline");ui.accessStatus.textContent="Network offline. Chat disabled; recovery will check the live connection.";state.streamWake?.();});
window.addEventListener("online",()=>{
  setConnected(false,state.csrf?"Reconnecting":"Online — connect device");
  if(state.csrf&&state.subscription&&!state.connecting)startStreamOwnership();
  else if(!state.connecting)ui.accessStatus.textContent=state.hasIdentity?"Connect existing device to start a fresh authenticated session.":"Paste an approved ticket to enroll.";
});
window.addEventListener("pageshow",()=>{renderGarminStatus();if(state.csrf&&state.subscription&&!state.connecting){state.streamAbort?.abort();setConnected(false,"Checking live connection");startStreamOwnership();}});
document.addEventListener("visibilitychange",()=>{if(!document.hidden){renderGarminStatus();if(state.csrf&&state.subscription&&!state.connecting){state.streamAbort?.abort();setConnected(false,"Checking live connection");startStreamOwnership();}}});
if("serviceWorker" in navigator)navigator.serviceWorker.register("/app/sw.js?v=7",{scope:"/app/"}).catch(()=>announce("Offline shell unavailable"));
const initialGeneration=state.sessionGeneration;
loadIdentity().then(identity=>{if(state.sessionGeneration!==initialGeneration)return;state.hasIdentity=Boolean(identity);updateControls();if(identity){ui.accessStatus.textContent="Enrolled key found. Connect existing device to start a fresh session.";announce(ui.accessStatus.textContent);}}).catch(()=>{if(state.sessionGeneration===initialGeneration)announce("Device storage unavailable");});
