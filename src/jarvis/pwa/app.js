const API="/api/v1";
const PRIVATE_GARMIN=document.body?.dataset?.profile==="private-garmin";
const PRIVATE_FILES=document.body?.dataset?.profile==="private-files";
const PROTOTYPE=["prototype-text","daily-text","private-garmin","private-files","private-memory","public-research"].includes(document.body?.dataset?.profile);
const DB_NAME="jarvis-private-client";
const STORE="identity";
const SCOPES=["browser.session","identity.read","events.read","session.revoke","client.chat","client.tasks.read","client.status.read"];
const HEALTH_SCOPE="client.health.read";
const encoder=new TextEncoder();
const state={csrf:null,subscription:null,cursor:0,conversation:null,online:false,stopping:false,streamAbort:null,streamOwner:null,streamWake:null,hasIdentity:false,sessionGeneration:0,logoutPending:null,bootstrap:null,identityWrite:null,connecting:false,enrolling:false,sending:false,tasksBusy:false,healthAllowed:false,healthGeneration:0,healthAbort:null,healthSnapshot:null,healthTimer:null,healthMessage:"",chatActive:new Set(),chatAnnounced:new Map(),chatDrafts:new Map(),deviceId:null,pendingRequest:null,chatAction:null,chatMarkerWrite:null,historyGeneration:0,historyBusy:false,historyBefore:null,historyReady:false};
const ui=Object.fromEntries(Object.entries({connection:"connection",setup:"setup",ticket:"ticket",ticketError:"ticket-error",accessStatus:"access-status",enroll:"enroll",connect:"connect",notify:"notify",logout:"logout",chat:"chat",chatStatus:"chat-status",message:"message",send:"send",log:"log",jumpLatest:"jump-latest",conversations:"conversation-list",newConversation:"new-conversation",refreshHistory:"refresh-history",olderHistory:"older-history",cancelChat:"cancel-chat",retryChat:"retry-chat",tasks:"tasks",taskPanel:"task-panel",tasksState:"tasks-state",refreshTasks:"refresh-tasks",device:"device-status",notice:"notice",garmin:"garmin",refreshGarmin:"refresh-garmin",garminState:"garmin-state",garminMetrics:"garmin-metrics",garminActivities:"garmin-activities"}).map(([name,id])=>[name,document.querySelector(`#${id}`)]));

Object.assign(state,{voice:null,voiceReady:false,voiceMax:30000,composerRevision:0});
Object.assign(state,{attachments:[],attachmentsAllowed:false,search:null,searchBefore:null,searchQuery:"",taskRead:null,taskSelected:null,taskOffset:0,taskChecked:0,taskTimer:null,threadDrafts:new Map()});
Object.assign(state,{libraryRead:null,libraryPage:null,libraryOffset:0,libraryArchived:false,libraryMutation:null});
Object.assign(state,{attachmentRead:null,attachmentPage:null,attachmentOffset:0,reuseSelected:new Set(),reuseDrafts:new Map(),attachmentTimer:null,attachmentPending:false});
Object.assign(state,{taskRevision:null,taskPageOffset:0,taskListAbort:null,timelineRead:null,timelineBefore:null,timelinePage:null});
Object.assign(ui,Object.fromEntries(Object.entries({taskFilter:"task-filter",taskSort:"task-sort",previousTasks:"previous-tasks",taskEvents:"task-events",timelineState:"task-timeline-state",eventsOlder:"task-events-older",eventsLatest:"task-events-latest",timelineTitle:"task-timeline-title"}).map(([key,id])=>[key,document.querySelector(`#${id}`)])));
Object.assign(ui,Object.fromEntries(Object.entries({conversationAttachments:"conversation-attachments",conversationAttachmentsState:"conversation-attachments-state",refreshAttachments:"refresh-attachments",attachmentsPrevious:"attachments-previous",attachmentsNext:"attachments-next"}).map(([key,id])=>[key,document.querySelector(`#${id}`)])));
Object.assign(ui,Object.fromEntries(Object.entries({library:"library",libraryState:"library-state",libraryArchived:"library-archived",libraryRefresh:"library-refresh",libraryPrevious:"library-previous",libraryNext:"library-next",libraryTitle:"library-title"}).map(([key,id])=>[key,document.querySelector(`#${id}`)])));
Object.assign(ui,Object.fromEntries(Object.entries({attachmentFile:"attachment-file",attachmentState:"attachment-state",attachments:"attachments",searchForm:"search-history",searchQuery:"history-query",searchSubmit:"search-submit",searchClear:"search-clear",searchState:"search-state",searchResults:"search-results",searchMore:"search-more",moreTasks:"more-tasks",taskDetail:"task-detail",taskDetailTitle:"task-detail-title",taskDetailState:"task-detail-state",taskProgress:"task-progress",taskNodes:"task-nodes",cancelTask:"cancel-task"}).map(([key,id])=>[key,document.querySelector(`#${id}`)])));
Object.assign(ui,Object.fromEntries(Object.entries({record:"record-message",stopVoice:"stop-recording",discardVoice:"discard-recording",voiceStatus:"voice-status"}).map(([key,id])=>[key,document.querySelector(`#${id}`)])));
// Navigation owns presentation only. Session, requests and private data stay in their existing owners.
const views=Object.fromEntries(["chat","garmin","settings"].map(name=>[name,{panel:document.querySelector(`#view-${name}`),link:document.querySelector(`#nav-${name}`),heading:document.querySelector(`#${name}-title`)}]));
const navigation={view:null,chatScroll:0,chatFollow:true};
function selectView(name,{replace=false,focus=true}={}){
  if(!Object.hasOwn(views,name)||(PROTOTYPE&&!PRIVATE_GARMIN&&name==="garmin"))name="chat";
  const hash=`#/${name}`;
  if(window.location.hash!==hash)window.history[replace?"replaceState":"pushState"](null,"",hash);
  if(navigation.view==="chat"){
    navigation.chatScroll=ui.log.scrollTop;navigation.chatFollow=nearLatest()&&!historySelected();
  }
  if(name!=="chat"){discardVoice();clearAttachments();clearSearch();cancelTaskRead();cancelTaskList();cancelLibrary();cancelAttachmentRead();}
  navigation.view=name;
  for(const [key,view] of Object.entries(views)){
    view.panel.hidden=key!==name;
    if(key===name)view.link.setAttribute("aria-current","page");else view.link.removeAttribute("aria-current");
  }
  document.title=`${views[name].link.textContent} · JARVIS`;
  if(name==="chat"){ui.log.scrollTop=navigation.chatFollow?ui.log.scrollHeight:navigation.chatScroll;updateJump();}
  if(focus){window.scrollTo(0,0);views[name].heading.focus();}
}
function restoreView({focus=true}={}){
  const name=window.location.hash.slice(2),valid=window.location.hash===`#/${name}`&&Object.hasOwn(views,name);
  if(!valid||navigation.view!==name)selectView(valid?name:"chat",{replace:true,focus});
}
for(const [name,view] of Object.entries(views))view.link.addEventListener("click",event=>{
  if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  event.preventDefault();selectView(name);
});
window.addEventListener("popstate",()=>restoreView());
window.addEventListener("hashchange",()=>restoreView());
restoreView({focus:false});

function renderGarmin(summary){
  ui.garminMetrics.replaceChildren();
  const values=[["Steps",summary.steps],["Resting heart rate",summary.resting_heart_rate==null?null:`${summary.resting_heart_rate} bpm`],["Sleep",summary.sleep_minutes==null?null:`${Math.floor(summary.sleep_minutes/60)}h ${summary.sleep_minutes%60}m`],["Stress",summary.stress],["Body Battery",summary.body_battery]];
  for(const [label,value] of values){const card=document.createElement("div"),dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value==null?"Unavailable":String(value);card.append(dt,dd);ui.garminMetrics.append(card);}
  ui.garminActivities.replaceChildren();
  for(const activity of summary.activities||[]){const item=document.createElement("li");item.textContent=`${activity.name} · ${activity.type}${activity.started?` · ${activity.started.slice(0,10)}`:""}`;ui.garminActivities.append(item);}
  if(!ui.garminActivities.children.length){const item=document.createElement("li");item.textContent=summary.activities_available===false?"Recent activities unavailable.":"No recent activities.";ui.garminActivities.append(item);}
  state.healthSnapshot={date:summary.date,refreshed:Date.parse(summary.refreshed_at)};state.healthMessage="";renderGarminStatus();
}
function renderGarminStatus(){
  clearTimeout(state.healthTimer);state.healthTimer=null;
  const snapshot=state.healthSnapshot;
  if(!snapshot){if(state.healthMessage)ui.garminState.textContent=state.healthMessage;return;}
  const now=new Date(),day=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
  const age=Date.now()-snapshot.refreshed,valid=Number.isFinite(snapshot.refreshed),stale=!valid||age<0||age>=300000||snapshot.date!==day;
  const checked=valid?new Date(snapshot.refreshed).toLocaleString():"Unknown";
  ui.garminState.textContent=`${state.healthMessage?state.healthMessage+" ":""}${snapshot.date} · last checked ${checked}${stale?" · Stale. Refresh Garmin to check current data.":""}`;
  if(!stale){const midnight=new Date(now);midnight.setHours(24,0,0,0);state.healthTimer=setTimeout(renderGarminStatus,Math.min(300000-age,midnight-Date.now()));}
}
function cancelGarmin(){state.healthGeneration+=1;state.healthAbort?.abort();state.healthAbort=null;}
function clearGarmin(){
  cancelGarmin();clearTimeout(state.healthTimer);state.healthTimer=null;state.healthSnapshot=null;state.healthMessage="";state.healthAllowed=false;
  ui.refreshGarmin.disabled=true;ui.garmin.setAttribute("aria-busy","false");ui.garminMetrics.replaceChildren();ui.garminActivities.replaceChildren();ui.garminState.textContent="Connect JARVIS to see Garmin data.";
}
async function refreshGarmin(force){
  if(PROTOTYPE&&!PRIVATE_GARMIN)return;
  if(!state.online||!state.healthAllowed)return;
  cancelGarmin();
  const generation=state.healthGeneration,csrf=state.csrf,controller=new AbortController();state.healthAbort=controller;
  const current=()=>generation===state.healthGeneration&&state.csrf===csrf&&state.online&&state.healthAllowed&&!controller.signal.aborted;
  state.healthMessage="Checking Garmin…";renderGarminStatus();updateControls();
  try{const summary=await (await api(`/client/garmin${force?"?refresh=true":""}`,{signal:controller.signal})).json();if(current())renderGarmin(summary);}
  catch(error){if(current()&&error.name!=="AbortError"){
    if(error.status===403){clearGarmin();ui.garminState.textContent="Garmin access denied. Connect existing device; review approved access on your trusted laptop.";return;}
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
async function dbAction(mode,operation){const db=await openDb();return new Promise((resolve,reject)=>{const tx=db.transaction(STORE,mode),store=tx.objectStore(STORE);let request,result;try{request=operation(store);}catch(error){db.close();reject(error);return;}request.onsuccess=()=>{result=request.result;};request.onerror=()=>reject(request.error);tx.oncomplete=()=>{db.close();resolve(result);};tx.onabort=()=>{db.close();reject(tx.error||new Error("Device storage transaction aborted"));};tx.onerror=()=>reject(tx.error);});}
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
    return {ok:response.ok,status:response.status,headers:response.headers,json:()=>consume("json"),text:()=>consume("text"),discard:cleanup};
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
  clearWorkflows();
  discardVoice();state.voiceReady=false;
  ++state.sessionGeneration;stopStream();state.csrf=null;state.subscription=null;state.cursor=0;state.conversation=null;
  clearChat();
  clearGarmin();state.connecting=false;state.sending=false;state.tasksBusy=false;state.chatActive.clear();state.chatAnnounced.clear();state.chatDrafts.clear();ui.chat.setAttribute("aria-busy","false");ui.chatStatus.textContent="";ui.tasksState.textContent="";
  ui.device.replaceChildren();ui.tasks.replaceChildren();ui.log.replaceChildren();ui.jumpLatest.hidden=true;
  for(const key of ["jarvis-subscription","jarvis-cursor"])sessionStorage.removeItem(key);
  setConnected(false,label);ui.accessStatus.textContent=guidance;announce(guidance);
}
async function api(path,options={}){
  const headers={...(options.headers||{})},method=options.method||"GET",csrf=state.csrf,generation=state.sessionGeneration;
  if(method==="GET")headers["X-Jarvis-Browser-Origin"]=window.location.origin;
  if(method!=="GET"&&state.csrf)headers["X-Jarvis-CSRF"]=state.csrf;
  const timeout=path.startsWith("/client/voice/transcriptions")?110000:path.startsWith("/client/events?")?30000:path.startsWith("/client/garmin")?95000:10000;
  const response=await timedFetch(`${API}${path}`,{credentials:"include",cache:"no-store",...options,headers},timeout);
  if(options.signal?.aborted){response.discard();throw new DOMException("Request aborted","AbortError");}
  if(response.status===401){response.discard();if(currentSession(generation,csrf))invalidateSession();throw new ApiError("Session expired",401);}
  if(!response.ok){let detail=`HTTP ${response.status}`;try{detail=(await response.json()).detail||detail;}catch{}throw new ApiError(detail,response.status);}
  return response;
}
function updateControls(){
  for(const element of [ui.message,ui.notify])element.disabled=!state.online;
  const chatBlocked=Boolean(state.sending||state.pendingRequest||state.chatActive.size||state.historyBusy||state.chatAction);
  ui.send.disabled=!state.online||!state.historyReady||chatBlocked;
  for(const control of [ui.conversations,ui.newConversation])control.disabled=!state.online||chatBlocked;
  ui.refreshHistory.disabled=!state.online||Boolean(state.historyBusy||state.chatAction);
  ui.olderHistory.disabled=!state.online||Boolean(state.historyBusy||state.pendingRequest);
  ui.cancelChat.disabled=!state.online||!state.pendingRequest||Boolean(state.chatAction);
  ui.retryChat.disabled=!state.online||!state.pendingRequest||Boolean(state.sending||state.chatAction||state.historyBusy);
  ui.retryChat.hidden=!state.pendingRequest?.uncertain;
  ui.refreshTasks.disabled=!state.online||Boolean(state.tasksBusy);
  ui.refreshGarmin.disabled=!state.online||!state.healthAllowed||Boolean(state.healthAbort);
  ui.enroll.disabled=state.hasIdentity||Boolean(state.enrolling)||Boolean(state.connecting);
  ui.connect.disabled=Boolean(state.enrolling)||Boolean(state.connecting);
  ui.logout.disabled=!state.hasIdentity;
  ui.setup.setAttribute("aria-busy",String(Boolean(state.enrolling||state.connecting)));
  updateVoiceControls();
  ui.garmin.setAttribute("aria-busy",String(Boolean(state.healthAbort)));
  ui.taskPanel.setAttribute("aria-busy",String(Boolean(state.tasksBusy)));
  updateWorkflowControls();
}
function setConnected(value,label=value?"Connected":"Offline shell"){
  state.online=value&&navigator.onLine;
  const connectionText=navigator.onLine?label:"Network offline";
  if(ui.connection.textContent!==connectionText)ui.connection.textContent=connectionText;
  ui.connection.className=`status ${state.online?"online":navigator.onLine?"warn":""}`;
  if(!state.online){cancelLibrary();cancelAttachmentRead();discardVoice();clearAttachments();clearSearch();cancelTaskRead();cancelTaskList();cancelGarmin();if(state.healthAllowed){state.healthMessage=navigator.onLine?"Connection unavailable. Shown Garmin data may be stale.":"Offline. Shown Garmin data may be stale.";renderGarminStatus();}}
  else if(/^(Offline\.|Connection unavailable\.)/.test(state.healthMessage)){state.healthMessage="";renderGarminStatus();}
  updateControls();
}
function announce(message){ui.notice.textContent=message;}
function nearLatest(){return navigation.view!=="chat"?navigation.chatFollow:ui.log.scrollHeight-ui.log.clientHeight-ui.log.scrollTop<=48;}
function historySelected(){const selection=document.getSelection?.();return Boolean(selection&&!selection.isCollapsed&&ui.log.contains(selection.anchorNode));}
function updateJump(){if(navigation.view==="chat")ui.jumpLatest.hidden=nearLatest()&&!historySelected();}
function row(kind,text,requestId,structured=false){
  text=String(text);if(text.length>100008)text=text.slice(0,99928)+"\n[Reply display limit reached. Refresh history for Core excerpt.]";
  const follow=nearLatest()&&!historySelected();
  let target=requestId?ui.log.querySelector(`[data-request="${CSS.escape(requestId)}"]`):null;
  if(!target){target=document.createElement("div");target.className=`entry ${kind}`;if(requestId)target.dataset.request=requestId;ui.log.append(target);}
  target.className=`entry ${kind}`;
  const previous=target.replyText??target.textContent,textNode=target.firstChild;
  target.replyText=text;
  // Append deltas to the existing text node so selected reply text survives streaming.
  if(text!==previous){
    if(textNode?.nodeType===3&&target.childNodes.length===1&&text.startsWith(previous))textNode.appendData(text.slice(previous.length));
    else if(kind==="jarvis"&&(historySelected()||target.contains(document.activeElement))){target.pendingFormat=true;}
    else{target.textContent=text;target.formatted=false;}
  }
  if(follow&&navigation.view==="chat")ui.log.scrollTop=ui.log.scrollHeight;
  ui.jumpLatest.hidden=follow&&nearLatest();
  if(structured&&kind==="jarvis")formatReply(target);
  trimHistory(target);
  return target;
}
function trimHistory(keep,{older=false}={}){
  const rows=[...ui.log.children],position=ui.log.scrollTop,height=ui.log.scrollHeight,selection=document.getSelection?.();
  let count=rows.length,chars=rows.reduce((sum,node)=>sum+(node.replyText??node.textContent).length,0);
  for(const node of older?rows.reverse():rows){
    if(count<=200&&chars<=512000)break;
    if(node===keep||node.contains(document.activeElement)||selection&&!selection.isCollapsed&&node.contains(selection.anchorNode))continue;
    count--;chars-=(node.replyText??node.textContent).length;node.remove?.();
  }
  if(navigation.view==="chat"&&!nearLatest())ui.log.scrollTop=Math.max(0,position+ui.log.scrollHeight-height);
}
// A deliberately bounded Markdown subset. Every untrusted value enters text nodes only.
// No HTML parser, remote images, embeds, syntax engines or source-authority inference.
function renderReply(text){
  const root=document.createElement("div");root.className="reply-body";
  let nodes=0,links=0,codes=0;
  const make=(tag,value)=>{if(++nodes>1200)throw new Error("render limit");const node=document.createElement(tag);if(value!==undefined)node.textContent=value;return node;};
  const citation=label=>label.replace(/^source:/,"Source · ").replace(/^attachment:/,"Attachment · ").replace(/#chunk:/," · chunk ").replace(/#image$/," · image");
  function inline(parent,value,depth=0){
    const escapes=[...value.matchAll(/\\([\\`*_{}\[\]()<>#+.!|~-])/g)];
    if(escapes.length){let start=0;for(const match of escapes){if(match.index>start)inline(parent,value.slice(start,match.index),depth);parent.append(make("span",match[1]));start=match.index+match[0].length;}if(start<value.length)inline(parent,value.slice(start),depth);return;}
    if(depth>=4){parent.append(make("span",value));return;}
    const tokens=/!?\[([^\]\n]{1,200})\]\((<?[^\s)]{1,2048}>?)\)|\[((?:source|attachment):[^\]\n]{1,200})\]|(`)([^`\n]{1,2000})`|(\*\*|__)([^\n]{1,2000}?)\6|(\*|_)([^\n]{1,1000}?)\8/g;
    let start=0;
    for(const match of value.matchAll(tokens)){
      if(match.index>start)parent.append(make("span",value.slice(start,match.index)));
      let node;
      if(match[1]){
        let url;try{url=new URL(match[2].replace(/^<|>$/g,""));}catch{}
        const safe=!match[0].startsWith("!")&&url&&["https:","http:"].includes(url.protocol)&&!url.username&&!url.password&&++links<=40;
        if(safe){node=make("a",citation(match[1]));node.href=url.href;node.target="_blank";node.rel="noopener noreferrer";node.referrerPolicy="no-referrer";}
        else node=make("span",match[0]);
      }else if(match[3]){node=make("span",citation(match[3]));node.className="citation";}
      else if(match[4])node=make("code",match[5]);
      else{node=make(match[6]?"strong":"em");inline(node,match[7]||match[9],depth+1);}
      parent.append(node);start=match.index+match[0].length;
    }
    if(start<value.length)parent.append(make("span",value.slice(start)));
  }
  const lines=text.slice(0,32000).replaceAll("\r\n","\n").split("\n");
  try{
    for(let i=0;i<lines.length;i++){
      const line=lines[i];if(!line.trim())continue;
      const fence=line.match(/^\s{0,3}(`{3,}|~{3,})([^`~]*)$/);
      if(fence){
        let end=i+1;while(end<lines.length&&!lines[end].trim().startsWith(fence[1]))end++;
        if(end===lines.length||++codes>12){root.append(make("pre",lines.slice(i).join("\n")));break;}
        const value=lines.slice(i+1,end).join("\n"),wrap=make("div"),pre=make("pre"),code=make("code",value);pre.append(code);wrap.append(pre);
        if(value.length<=16000)wrap.append(copyControl("Copy code",()=>value));root.append(wrap);i=end;continue;
      }
      if(i+1<lines.length&&line.includes("|")&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])){
        const scroll=make("div"),table=make("table"),head=make("thead"),body=make("tbody");scroll.className="table-scroll";scroll.tabIndex=0;scroll.setAttribute("aria-label","Reply table");
        const cells=value=>value.replace(/^\s*\||\|\s*$/g,"").split("|").slice(0,12);
        const add=(value,parent,tag)=>{const tr=make("tr");for(const cell of cells(value)){const td=make(tag);if(tag==="th")td.setAttribute("scope","col");inline(td,cell.trim());tr.append(td);}parent.append(tr);};
        add(line,head,"th");i+=2;let count=0;
        while(i<lines.length&&lines[i].includes("|")&&count++<50){add(lines[i],body,"td");i++;}i--;table.append(head,body);scroll.append(table);root.append(scroll);continue;
      }
      const heading=line.match(/^(#{1,6})\s+(.+)$/),list=line.match(/^\s{0,12}([-+*]|\d{1,6}[.)])\s+(.+)$/),quote=line.match(/^>\s?(.*)$/);
      if(list){const ordered=/\d/.test(list[1]),ul=make(ordered?"ol":"ul");let match=list;
        do{const li=make("li");inline(li,match[2]);ul.append(li);const next=lines[i+1]?.match(/^\s{0,12}([-+*]|\d{1,6}[.)])\s+(.+)$/);if(!next||/\d/.test(next[1])!==ordered)break;match=next;i++;}while(true);root.append(ul);continue;}
      const node=make(heading?`h${Math.min(6,heading[1].length+2)}`:quote?"blockquote":"p");inline(node,heading?heading[2]:quote?quote[1]:line);root.append(node);
    }
    if(text.length>32000)root.append(make("pre",text.slice(32000)));
  }catch{root.replaceChildren();root.textContent=text;}
  return root;
}
function copyControl(label,value){
  const button=document.createElement("button");button.type="button";button.className="secondary";button.textContent=label;
  button.addEventListener("click",async()=>{
    const generation=state.sessionGeneration,csrf=state.csrf;
    try{if(!navigator.clipboard?.writeText)throw new Error("clipboard unavailable");await navigator.clipboard.writeText(value());if(currentSession(generation,csrf))announce(`${label}: copied.`);}
    catch{if(currentSession(generation,csrf))announce(`${label} failed. Select text and copy using your device controls.`);}
  });return button;
}
function formatReply(target){
  if(target.formatted||!target.replyText)return;
  if(historySelected()||target.contains(document.activeElement)){target.pendingFormat=true;return;}
  const follow=nearLatest(),position=ui.log.scrollTop,text=target.replyText.replace(/^JARVIS: /,"");
  const body=ui.log.querySelectorAll?.(".reply-body *").length>6000?document.createElement("pre"):renderReply(text);
  if(body.tagName==="PRE")body.textContent=text;
  target.replaceChildren(body,copyControl("Copy response",()=>text));target.formatted=true;target.pendingFormat=false;
  ui.log.scrollTop=follow?ui.log.scrollHeight:position;
}
document.addEventListener("selectionchange",()=>{if(!historySelected())for(const target of ui.log.children)if(target.pendingFormat)formatReply(target);});
ui.log.addEventListener("focusout",()=>{Promise.resolve().then(()=>{for(const target of ui.log.children)if(target.pendingFormat)formatReply(target);});});
ui.log.addEventListener("scroll",updateJump);
ui.jumpLatest.addEventListener("click",()=>{ui.log.scrollTop=ui.log.scrollHeight;ui.jumpLatest.hidden=true;ui.log.focus({preventScroll:true});});
function completeReply(id,message,completed=false){
  state.chatActive.delete(id);ui.chat.setAttribute("aria-busy",String(state.chatActive.size>0));
  if(state.chatAnnounced.has(id))return;
  state.chatAnnounced.set(id,completed);
  if(completed&&state.chatDrafts.has(id)&&ui.message.value.trim()===state.chatDrafts.get(id))ui.message.value="";
  state.chatDrafts.delete(id);
  if(completed){const target=ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`);if(target)formatReply(target);}
  if(state.pendingRequest?.request_id===id){state.pendingRequest=null;writeChatMarker(null).catch(()=>{});}
  updateControls();
  ui.chatStatus.textContent=message.slice(0,320);
  if(completed)notifyGeneric();
}

function clearChat(){
  discardVoice();
  navigation.chatScroll=0;navigation.chatFollow=true;
  ++state.historyGeneration;state.historyBusy=false;state.historyBefore=null;state.historyReady=false;
  state.pendingRequest=null;state.chatAction=null;state.chatActive.clear();state.chatAnnounced.clear();state.chatDrafts.clear();
  ui.log.replaceChildren();ui.conversations.replaceChildren();ui.conversations.value="";ui.olderHistory.hidden=true;ui.jumpLatest.hidden=true;ui.chatStatus.textContent="";
}
// Only an opaque device-associated request reference persists. Core owns all transcript text.
function writeChatMarker(request){
  const generation=state.sessionGeneration,deviceId=state.deviceId,previous=state.chatMarkerWrite;
  const write=(async()=>{if(previous)await previous.catch(()=>{});if(state.sessionGeneration!==generation||state.deviceId!==deviceId)return;
    return dbAction("readwrite",store=>request?store.put({deviceId,request_id:request.request_id},"chat-request"):store.delete("chat-request"));})();
  state.chatMarkerWrite=write;write.finally(()=>{if(state.chatMarkerWrite===write)state.chatMarkerWrite=null;}).catch(()=>{});return write;
}
function applyChatResult(result,{silent=false}={}){
  const id=result.request_id;if(!id)return;
  if(!silent&&state.chatAnnounced.has(id))return;
  if(result.conversation_id&&state.conversation&&result.conversation_id!==state.conversation)return;
  if(result.conversation_id){state.conversation=result.conversation_id;selectCurrentConversation();if(state.attachmentPending)scheduleAttachmentRefresh();}
  if(result.status==="running"){
    if(state.chatAnnounced.has(id))return;
    const pending=state.pendingRequest?.request_id===id?state.pendingRequest:{request_id:id};state.pendingRequest=pending;pending.uncertain=Boolean(pending.cancelIntent);
    state.chatActive.add(id);ui.chat.setAttribute("aria-busy","true");
    if(!ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`))row("jarvis","JARVIS: Reply in progress…",id);
    const runningText=pending.cancelIntent?"Cancellation unconfirmed. Retry request checks Core; generation may still be running.":"JARVIS is replying. Cancel reply stops generation on Core.";
    if(!silent&&ui.chatStatus.textContent!==runningText)ui.chatStatus.textContent=runningText;
    updateControls();return;
  }
  if(!["completed","cancelled","failed","interrupted"].includes(result.status))throw new Error("Invalid Core chat status");
  const completed=result.status==="completed";
  if(result.status==="failed"&&!ui.message.value){const draft=state.chatDrafts.get(id)||(state.pendingRequest?.request_id===id?state.pendingRequest.payload?.message:null);if(draft){ui.message.value=draft;state.composerRevision++;}}
  if(silent&&completed&&result.reply===undefined&&state.pendingRequest?.request_id===id&&!ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`))return;
  const message=completed?"Reply complete.":result.status==="cancelled"?"Request cancelled.":result.status==="interrupted"?"Reply interrupted. Original request will not run again. Review history before sending a new message.":result.error?.code==="upload_unavailable"?"Attachment upload expired or unavailable. Select files again, then Send a new message.":result.error?.code==="attachment_processing_failed"?"Attachment processing failed. Check file format and host attachment readiness; draft kept.":attachmentRecovery(result.error?.code)||modelRecovery(result.error?.code)||"Request failed safely.";
  if(!silent&&!state.chatAnnounced.has(id))row(completed?"jarvis":"meta",completed?`JARVIS: ${result.reply||"Completed"}${result.reply_truncated?"\n[Reply excerpt. Review Core history.]":""}`:message,id);
  if(silent){if(completed&&typeof result.reply==="string")row("jarvis",`JARVIS: ${result.reply}${result.reply_truncated?"\n[Reply excerpt. Review Core history.]":""}`,id,true);state.chatActive.delete(id);state.chatAnnounced.set(id,completed);if(completed&&state.chatDrafts.has(id)&&ui.message.value.trim()===state.chatDrafts.get(id))ui.message.value="";state.chatDrafts.delete(id);if(state.pendingRequest?.request_id===id){state.pendingRequest=null;writeChatMarker(null).catch(()=>{});}updateControls();}
  else completeReply(id,completed?`${message} ${result.reply||""}`:message,completed);
}
function modelRecovery(code){
  if(code==="provider_error")return "Model unavailable or request rejected. Check the configured model on your laptop, then review history before sending a new message. No automatic provider change.";
  if(code==="invalid_provider_response")return "Model returned an invalid reply. Review history before sending a new message; no automatic retry.";
  if(code==="request_timeout")return "Reply timed out. Review the original request and history before sending a new message; no automatic retry.";
  return null;
}
async function checkPendingRequest({silent=false}={}){
  const pending=state.pendingRequest;if(!pending)return;
  pending.lastChecked=Date.now();
  const generation=state.sessionGeneration,csrf=state.csrf;
  try{const result=await (await api(`/client/chat/${encodeURIComponent(pending.request_id)}${state.subscription?`?subscription_id=${encodeURIComponent(state.subscription)}`:""}`)).json();
    if(currentSession(generation,csrf)&&state.pendingRequest===pending)applyChatResult(result,{silent});
  }catch(error){if(!currentSession(generation,csrf)||state.pendingRequest!==pending)return;
    if(error.status===404){pending.uncertain=true;ui.chatStatus.textContent=pending.payload?"Core has no accepted request. Retry request safely uses the original request ID.":"Core has no accepted request. Draft was not stored; enter your message again.";
      if(!pending.payload){pending.cancelIntent=true;try{await cancelPendingOnCore(pending,generation,csrf);}catch(cancelError){if(currentSession(generation,csrf)&&state.pendingRequest===pending){ui.chatStatus.textContent="Request closure unconfirmed. Retry request checks Core and retries cancellation before another message can be sent.";updateControls();}throw cancelError;}if(currentSession(generation,csrf)&&!state.pendingRequest)ui.chatStatus.textContent="Unaccepted request closed on Core. Draft was not stored; enter your message again.";}}
    else{pending.uncertain=true;ui.chatStatus.textContent="Request status unavailable. Retry request checks Core before any resubmission.";}
    updateControls();if(error.status!==404)throw error;
  }
}
function selectCurrentConversation(){
  for(const item of ui.library.children)if(item.controls?.[0])item.controls[0].setAttribute("aria-current",String(item.controls[0].dataset.conversation===state.conversation));
  if(!state.conversation)return;
  if(![...ui.conversations.children].some(option=>option.value===state.conversation)){const option=document.createElement("option");option.value=state.conversation;option.textContent="Current conversation";ui.conversations.append(option);}
  ui.conversations.value=state.conversation;
}
async function refreshHistory({conversation,older=false,matchSequence=null}={}){
  discardVoice();
  if(!state.csrf||state.historyBusy)return;
  const generation=state.sessionGeneration,csrf=state.csrf,history=++state.historyGeneration,operation={};state.historyBusy=operation;updateControls();
  const current=()=>currentSession(generation,csrf)&&state.historyGeneration===history;
  try{
    if(!older){
      const listing=await (await api("/client/conversations?limit=20")).json();if(!current())return;
      if(!state.libraryArchived&&!state.libraryOffset&&!state.libraryRead&&!state.libraryMutation)renderLibrary(listing);
      ui.conversations.replaceChildren();const empty=document.createElement("option");empty.value="";empty.textContent="New conversation";ui.conversations.append(empty);
      for(const saved of listing.conversations){const option=document.createElement("option");option.value=saved.id;option.textContent=saved.title||"Conversation";ui.conversations.append(option);}
      if(conversation===undefined)conversation=state.conversation||listing.active_request?.conversation_id||listing.conversations[0]?.id||null;
      if(listing.active_request&&!state.pendingRequest)state.pendingRequest={request_id:listing.active_request.request_id};
    }
    const selected=older?state.conversation:conversation;
    if(!selected){if(current()){state.conversation=null;ui.log.replaceChildren();state.historyBefore=null;ui.olderHistory.hidden=true;state.historyReady=true;}return;}
    const partialRow=state.pendingRequest?ui.log.querySelector(`[data-request="${CSS.escape(state.pendingRequest.request_id)}"]`):null,partial=partialRow?.className==="entry jarvis"?partialRow.textContent:null;
    const before=matchSequence?matchSequence+1:older?state.historyBefore:null;
    const page=await (await api(`/client/conversations/${encodeURIComponent(selected)}/messages?limit=50${before?`&before=${before}`:""}`)).json();
    if(!current()||page.conversation_id!==selected)return;
    const oldRows=older?[...ui.log.children]:[],position=ui.log.scrollTop,height=ui.log.scrollHeight;
    state.conversation=selected;ui.conversations.value=selected;ui.log.replaceChildren();
    for(const message of page.messages)row(message.role==="user"?"user":"jarvis",`${message.role==="user"?"You":"JARVIS"}: ${message.content}${message.truncated?"\n[Message excerpt]":""}`,message.request_id?`${message.request_id}${message.role==="user"?":user":""}`:`message:${message.id}`,message.role!=="user");
    for(const target of oldRows)ui.log.append(target);
    if(page.attachment_page){state.attachmentOffset=0;renderAttachmentMetadata(page.attachment_page);}
    if(older)ui.log.scrollTop=position+ui.log.scrollHeight-height;
    state.historyBefore=page.next_before;ui.olderHistory.hidden=!page.has_more;
    trimHistory(older?ui.log.firstChild:ui.log.lastChild,{older});
    if(!older){
      state.chatActive.clear();state.chatAnnounced.clear();
      for(const request of page.requests||[])if(request.status!=="running")applyChatResult(request,{silent:true});
      const running=(page.requests||[]).find(request=>request.status==="running");
      if(running){applyChatResult(running,{silent:true});if(partial)row("jarvis",partial,running.request_id);}
      await checkPendingRequest({silent:true});if(!current())return;
    }
    state.historyReady=true;selectCurrentConversation();ui.chat.setAttribute("aria-busy",String(state.chatActive.size>0));
    if(!state.pendingRequest)ui.chatStatus.textContent=matchSequence?"Matching message is last in this history page. Refresh history for latest messages.":older?"Earlier messages loaded.":"Conversation restored from Core.";
  }catch(error){if(current()){state.historyReady=false;ui.chatStatus.textContent="History unavailable. Refresh history after connection recovers; sending stays disabled.";}throw error;}
  finally{if(state.historyBusy===operation)state.historyBusy=false;updateControls();}
}
async function chooseConversation(conversation,matchSequence=null){
  discardVoice();
  if(!state.online||state.pendingRequest||state.sending||state.chatActive.size||state.chatAction)return;
  const generation=state.sessionGeneration,csrf=state.csrf;
  state.threadDrafts.set(state.conversation,ui.message.value);
  if(!ui.message.value)state.threadDrafts.delete(state.conversation);
  if(state.threadDrafts.size>20){state.threadDrafts.delete(state.conversation);ui.chatStatus.textContent="20 unsent conversation drafts already open. Send or clear a draft before opening another conversation. Current text kept.";selectCurrentConversation();return;}
  state.reuseDrafts.set(state.conversation,new Set(state.reuseSelected));
  if(state.reuseDrafts.size>20)state.reuseDrafts.delete(state.reuseDrafts.keys().next().value);
  clearAttachments();clearAttachmentMetadata();clearChat();state.conversation=conversation||null;state.reuseSelected=new Set(state.reuseDrafts.get(state.conversation)||[]);
  ui.message.value=state.threadDrafts.get(state.conversation)||"";state.composerRevision++;
  await refreshHistory({conversation:state.conversation,matchSequence});
  if(currentSession(generation,csrf)){selectCurrentConversation();updateControls();}
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
  const previousPending=state.pendingRequest,previousDevice=state.deviceId;
  const generation=++state.sessionGeneration,current=()=>state.sessionGeneration===generation;
  state.connecting=generation;clearWorkflows();clearGarmin();stopStream();state.csrf=null;state.subscription=null;setConnected(false,"Connecting");
  clearChat();state.conversation=null;state.sending=false;
  ui.accessStatus.textContent="Connecting existing device. Chat stays disabled until live transport is ready.";
  try{
    if(state.logoutPending)await state.logoutPending;if(!current())return;
    const previous=state.bootstrap;
    if(previous){if(!previous.headersReceived)previous.controller.abort();try{await previous.promise;}catch{}if(!current())return;}
    const identity=await loadIdentity();if(!current())return;
    if(!identity)throw new Error("No enrolled device key in this browser. Paste an approved, unexpired ticket to enroll.");
    state.hasIdentity=true;state.deviceId=identity.deviceId;
    const marker=await dbAction("readonly",store=>store.get("chat-request"));if(!current())return;
    if(previousDevice===identity.deviceId&&previousPending)state.pendingRequest=previousPending;
    else if(marker?.deviceId===identity.deviceId)state.pendingRequest={request_id:marker.request_id};
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
    await checkPendingRequest({silent:true});if(!current())return;
    await refreshHistory();if(!current())return;
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
async function refreshStatus(){
  const generation=state.sessionGeneration,csrf=state.csrf,status=await (await api("/client/status")).json();if(!currentSession(generation,csrf))return;
  state.attachmentsAllowed=(!PROTOTYPE||PRIVATE_FILES)&&status.attachments?.available===true;state.voiceReady=!PROTOTYPE&&status.voice?.available===true;state.voiceMax=Math.min(30000,Math.max(120,status.voice?.max_duration_ms||30000));updateVoiceControls();
  document.querySelector("#file-capabilities").textContent=state.attachmentsAllowed?`Text/MD and text PDFs: local extraction. PNG/JPEG: local normalization. ${status.attachments.vision_configured?"Local image interpretation configured; each request checks availability. OCR is not guaranteed.":"Image understanding unavailable: no local vision model configured."}`:"File processing unavailable for this profile or approved device access.";
  if(status.garmin?.available===false){clearGarmin();ui.garminState.textContent="Garmin unavailable for this profile or approved device access. Review access on your trusted laptop.";}
  ui.device.replaceChildren();
  const entries=[["Name",status.device.display_name],["State",status.device.state],["Key version",status.device.key_version],["Session",status.session.id]];
  if(["prototype-text","daily-text","private-garmin","private-files","private-memory","public-research"].includes(status.assistant?.profile))entries.push(["Assistant",`${status.assistant.provider} · ${status.assistant.model} · ${status.assistant.cloud_policy}`]);
  for(const [name,value] of entries){const wrap=document.createElement("div"),dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=name;dd.textContent=String(value);wrap.append(dt,dd);ui.device.append(wrap);}
}
async function refreshTasks({more=false,offset:requestedOffset=null}={}){
  if(PROTOTYPE)return;
  if(state.tasksBusy||!state.csrf)return;
  const generation=state.sessionGeneration,csrf=state.csrf,operation={};state.tasksBusy=operation;
  const offset=requestedOffset??(more?state.taskOffset:state.taskPageOffset),abort=new AbortController();state.taskListAbort=abort;ui.tasksState.textContent="Checking tasks…";updateControls();
  try{
    const response=await api(`/client/tasks?limit=50${offset?`&offset=${offset}`:""}${ui.taskFilter.value?`&status=${encodeURIComponent(ui.taskFilter.value)}`:""}&sort=${ui.taskSort.value||"newest"}${(more||requestedOffset!==null)&&state.taskRevision!==null?`&revision=${state.taskRevision}`:""}`,{signal:abort.signal}),tasks=await response.json();
    if(!currentSession(generation,csrf)||state.tasksBusy!==operation||!navigator.onLine||(!state.online&&!state.connecting))return;
    const focused=document.activeElement,restore=focused?.dataset?.task;ui.tasks.replaceChildren();
    if(!tasks.length&&!offset){const item=document.createElement("li");item.textContent="No tasks.";ui.tasks.append(item);}
    for(const task of tasks){
      const item=document.createElement("li"),button=document.createElement("button");button.type="button";button.className="secondary";
      button.textContent=`${task.id} · ${task.status}${Number.isInteger(task.total_nodes)?` · ${task.completed_nodes}/${task.total_nodes} steps complete`:""}`;
      if(task.verifying_nodes)button.textContent+=` · ${task.verifying_nodes} verifying`;
      button.dataset.task=task.id;button.setAttribute("aria-current",String(state.taskSelected===task.id));
      button.addEventListener("click",()=>guarded(()=>loadTask(task.id,{focus:true})));item.append(button);ui.tasks.append(item);
      if(restore===task.id)button.focus({preventScroll:true});
    }
    if(restore&&document.activeElement===focused)ui.refreshTasks.focus({preventScroll:true});
    state.taskRevision=response.headers?.get?.("X-Jarvis-Task-Revision")??null;state.taskPageOffset=offset;ui.previousTasks.hidden=offset===0;
    state.taskOffset=offset+tasks.length;ui.moreTasks.hidden=tasks.length<50||state.taskOffset>100000;
    state.taskChecked=Date.now();ui.tasksState.textContent=tasks.length?`Tasks ${offset+1}–${offset+tasks.length} checked. Select task for details.`:"No tasks match this filter. Refresh tasks to return to first page.";
    if(state.taskSelected)await loadTask(state.taskSelected);
    scheduleTaskRefresh();
  }catch(error){if(!currentSession(generation,csrf)||state.tasksBusy!==operation||error.name==="AbortError")return;ui.tasksState.textContent=error.status===409?"Task list changed. Refresh tasks to restart pagination; selected task stays selected.":"Task check failed. Displayed state may be stale. Refresh tasks after connection recovers.";throw error;}
  finally{if(state.tasksBusy===operation){state.tasksBusy=false;state.taskListAbort=null;}updateControls();}
}
function processEvent(event){
  if(!Number.isInteger(event.cursor)||event.cursor<1)throw new Error("Invalid event cursor");
  if(event.cursor<=state.cursor)return;
  if(event.cursor!==state.cursor+1)throw new Error("Event cursor gap");
  state.cursor=event.cursor;sessionStorage.setItem("jarvis-cursor",String(state.cursor));
  if(event.topic==="chat"){
    const id=event.request_id;
    if(state.pendingRequest?.request_id!==id&&!state.chatActive.has(id)&&!state.chatDrafts.has(id))return;
    if(event.payload.conversation_id&&state.conversation&&event.payload.conversation_id!==state.conversation)return;
    // HTTP completion and replayed stream frames share one reply/announcement identity.
    if(state.chatAnnounced.has(id))return;
    if(event.event_type==="chat.started"){if(event.payload.conversation_id){state.conversation=event.payload.conversation_id;selectCurrentConversation();}state.pendingRequest=state.pendingRequest?.request_id===id?state.pendingRequest:{request_id:id};state.chatActive.add(id);ui.chat.setAttribute("aria-busy","true");row("jarvis","JARVIS: ",id);ui.chatStatus.textContent="JARVIS is replying.";updateControls();}
    if(event.event_type==="chat.delta"||event.event_type==="chat.frame"&&event.payload.type==="assistant_delta"){
      const existing=ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`);
      const prior=existing?.className==="entry jarvis"?(existing.replyText??existing.textContent):"JARVIS: ";
      row("jarvis",(prior==="JARVIS: Reply in progress…"?"JARVIS: ":prior)+(event.payload.content_delta||""),id);
    }
    if(event.event_type==="chat.completed"){
      state.conversation=event.payload.conversation_id||state.conversation;
      if(typeof event.payload.reply==="string")row("jarvis",`JARVIS: ${event.payload.reply}${event.payload.reply_truncated?"\n[Reply excerpt. Review Core history.]":""}`,id);
      const answer=ui.log.querySelector(`[data-request="${CSS.escape(id)}"]`)?.textContent||"Reply available in conversation.";
      completeReply(id,`Reply complete. ${answer}`,true);
    }
    if(["chat.failed","chat.cancelled","chat.interrupted"].includes(event.event_type)){
      applyChatResult({...event.payload,request_id:id,status:event.event_type.slice(5)});
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
      if(!state.historyReady){await refreshHistory();if(!current())break;}
      if(state.pendingRequest&&(!state.pendingRequest.lastChecked||Date.now()-state.pendingRequest.lastChecked>=2000)){await checkPendingRequest();if(!current())break;}
      setConnected(true);
      if(state.attachmentPending&&!state.attachmentTimer)scheduleAttachmentRefresh();
      if(owner?.tasksPending){owner.tasksPending=false;scheduleTaskRefresh(0);}
      const readyText="Live connection ready. Enrolled key retained; use Connect existing device for session renewal.";
      if(ui.accessStatus.textContent!==readyText)ui.accessStatus.textContent=readyText;
      if(owner?.healthPending){owner.healthPending=false;refreshGarmin(false).catch(()=>{});}
      // A fast local model can wake one poll per token. Bound polling to leave
      // capacity for history, status and chat under the existing request limit.
      await streamPause(500);
    }catch(error){
      if(!current())break;
      if(error.status===401||error.status===403){invalidateSession("Access denied","Live access denied. Connect existing device; if rejected, request approved recovery on your trusted host.");break;}
      setConnected(false,"Reconnecting");if(owner)owner.tasksPending=true;
      if(error.status===404||error.status===409){
        try{await resetSubscription();if(!current())break;state.historyReady=false;announce("Stream restarted. Checking live connection.");continue;}catch(restartError){if(!current())break;if(restartError.status===403){invalidateSession("Access denied","Stream access denied. Review approved device access on your trusted host.");break;}}
      }
      await streamPause(Math.min(5000,500+Math.random()*1500));
    }finally{if(state.streamAbort===controller)state.streamAbort=null;}
  }
}
function startStreamOwnership(){
  if(!state.csrf||!state.subscription||state.connecting)return;
  if(state.streamOwner){state.streamWake?.();return state.streamOwner.promise;}
  state.stopping=false;
  const owner={tasksPending:true,generation:state.sessionGeneration,controller:new AbortController(),cancelled:false,promise:null,healthPending:!PRIVATE_GARMIN&&state.healthAllowed&&!state.healthSnapshot};state.streamOwner=owner;
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
  if(state.composing||state.voice||state.attachments.some(item=>item.phase!=="ready")||state.reuseSelected.size&&!state.attachmentPage){event.preventDefault();return;}
  event.preventDefault();if(!state.online||!state.subscription||state.sending||state.pendingRequest||state.chatActive.size||!state.historyReady||state.historyBusy)return;
  const message=ui.message.value.trim();if(!message)return;
  const pending={request_id:randomId("request"),payload:{message,conversation_id:state.conversation,...(state.attachments.length?{upload_ids:state.attachments.map(item=>item.id)}:{}),...(state.reuseSelected.size?{attachment_ids:[...state.reuseSelected]}:{})},uncertain:false,posted:false};state.pendingRequest=pending;
  state.attachmentPending=Boolean(state.attachments.length||state.reuseSelected.size);state.reuseSelected.clear();state.reuseDrafts.delete(state.conversation);
  state.threadDrafts.delete(state.conversation);
  clearAttachments({discard:false});
  row("user",`You: ${message}`,`${pending.request_id}:user`);state.chatDrafts.set(pending.request_id,message);
  await submitPending(pending);
}
async function submitPending(pending){
  const generation=state.sessionGeneration,csrf=state.csrf,operation={};state.sending=operation;state.chatActive.add(pending.request_id);
  ui.chat.setAttribute("aria-busy","true");ui.chatStatus.textContent="Sending message…";updateControls();
  try{
    await writeChatMarker(pending);if(!currentSession(generation,csrf)||state.pendingRequest!==pending)return;
    if(pending.cancelIntent){applyChatResult({request_id:pending.request_id,conversation_id:state.conversation,status:"cancelled"});return;}
    pending.posted=true;
    const response=await api("/client/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...pending.payload,request_id:pending.request_id,subscription_id:state.subscription})});
    const result=await response.json();if(!currentSession(generation,csrf))return;
    if(result.status!=="failed"&&ui.message.value.trim()===pending.payload.message)ui.message.value="";
    applyChatResult({...result,request_id:result.request_id||pending.request_id,status:result.status|| (response.status===202?"running":"completed")});
    if(pending.cancelIntent&&state.pendingRequest===pending)await cancelPendingOnCore(pending,generation,csrf);
  }catch(error){
    if(currentSession(generation,csrf)){
      if(state.chatAnnounced.get(pending.request_id)===true){if(ui.message.value.trim()===pending.payload.message)ui.message.value="";}
      else if(!state.chatAnnounced.has(pending.request_id)){
        pending.uncertain=true;
        row("meta",pending.cancelIntent?"Cancellation unconfirmed. Retry request checks Core and retries cancellation.":"Send outcome unconfirmed. Retry request checks Core using the same request ID. Your draft is kept.",pending.request_id);
        state.chatActive.delete(pending.request_id);ui.chat.setAttribute("aria-busy",String(state.chatActive.size>0));
        ui.chatStatus.textContent=pending.cancelIntent?"Cancellation unconfirmed. Retry request checks Core; generation may still be running.":"Send outcome unconfirmed. Draft kept. Retry request checks Core before resubmitting.";
      }
    }
  }finally{if(state.sending===operation)state.sending=false;updateControls();}
}
async function retryChat(){
  const pending=state.pendingRequest;if(!state.online||!pending||state.chatAction||state.sending)return;
  const operation={},generation=state.sessionGeneration,csrf=state.csrf;state.chatAction=operation;updateControls();
  try{await checkPendingRequest();if(!currentSession(generation,csrf))return;
    if(state.pendingRequest===pending&&pending.cancelIntent){await cancelPendingOnCore(pending,generation,csrf);}
    else if(state.pendingRequest===pending&&pending.uncertain&&pending.payload)await submitPending(pending);
  }finally{if(state.chatAction===operation)state.chatAction=null;updateControls();}
}
async function cancelChat(){
  const pending=state.pendingRequest;if(!state.online||!pending||state.chatAction)return;
  pending.cancelIntent=true;
  const operation={},generation=state.sessionGeneration,csrf=state.csrf;state.chatAction=operation;ui.chatStatus.textContent="Stopping reply on Core…";updateControls();
  try{if(pending.posted===false){applyChatResult({request_id:pending.request_id,conversation_id:state.conversation,status:"cancelled"});return;}
    await cancelPendingOnCore(pending,generation,csrf);
  }catch(error){if(currentSession(generation,csrf)&&state.pendingRequest===pending){pending.uncertain=true;ui.chatStatus.textContent="Cancellation unconfirmed. Retry request checks Core; generation may still be running.";}throw error;}
  finally{if(state.chatAction===operation)state.chatAction=null;updateControls();}
}
async function cancelPendingOnCore(pending,generation,csrf){
  const result=await (await api(`/client/chat/${encodeURIComponent(pending.request_id)}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})).json();
  if(currentSession(generation,csrf)&&state.pendingRequest===pending)applyChatResult(result);
}
async function enableNotifications(){const generation=state.sessionGeneration,csrf=state.csrf;if(!("Notification" in window))throw new Error("Notifications unsupported");const permission=await Notification.requestPermission();if(!currentSession(generation,csrf))return;if(permission!=="granted")throw new Error("Notification permission denied");sessionStorage.setItem("jarvis-notifications","enabled");ui.notify.textContent="Notifications enabled";announce("Notifications contain generic text only");}
function notifyGeneric(){if(sessionStorage.getItem("jarvis-notifications")==="enabled"&&document.hidden&&Notification.permission==="granted")new Notification("JARVIS",{body:"JARVIS has an update.",tag:"jarvis-update",renotify:false,silent:true});}
async function logout(){
  clearWorkflows();
  selectView("settings",{replace:true,focus:false});
  const csrf=state.csrf,generation=++state.sessionGeneration,bootstrap=state.bootstrap,write=state.identityWrite,markerWrite=state.chatMarkerWrite,previous=state.logoutPending;
  clearGarmin();stopStream();if(bootstrap&&!bootstrap.headersReceived)bootstrap.controller.abort();
  state.csrf=null;state.subscription=null;state.cursor=0;state.conversation=null;state.hasIdentity=false;
  clearChat();state.deviceId=null;
  state.connecting=false;state.enrolling=false;state.sending=false;state.tasksBusy=false;state.chatActive.clear();state.chatAnnounced.clear();state.chatDrafts.clear();
  ui.chat.setAttribute("aria-busy","false");ui.chatStatus.textContent="";ui.tasksState.textContent="";ui.ticketError.textContent="";ui.ticket.removeAttribute("aria-invalid");
  ui.device.replaceChildren();ui.tasks.replaceChildren();ui.log.replaceChildren();ui.jumpLatest.hidden=true;ui.message.value="";ui.ticket.value="";
  setConnected(false,"Logging out");ui.accessStatus.textContent="Erasing local device access. Server sign-out is pending.";
  for(const key of ["jarvis-subscription","jarvis-cursor","jarvis-notifications"])sessionStorage.removeItem(key);
  const remote=csrf?revokeRemoteSession(csrf):Promise.resolve(false);
  const bootstrapCleanup=bootstrap?bootstrap.promise.then(credential=>revokeRemoteSession(credential.csrf_token),()=>false):Promise.resolve(true);
  const local=(async()=>{
    if(write){try{await write;}catch{}}if(markerWrite){try{await markerWrite;}catch{}}await clearIdentity();
    for(const registration of await navigator.serviceWorker?.getRegistrations?.()||[]){registration.active?.postMessage("JARVIS_LOGOUT");await registration.unregister();}
    for(const key of await caches.keys())if(key.startsWith("jarvis-shell-"))await caches.delete(key);
    if(state.sessionGeneration===generation){
      setConnected(false,"Logged out — device key erased");
      ui.accessStatus.textContent="Local device key and displayed data erased. Server sign-out pending. New access needs an approved enrollment ticket.";
      announce(ui.accessStatus.textContent);if(navigation.view==="settings")ui.ticket.focus();
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
function voiceCurrent(op){return state.voice===op&&currentSession(op.generation,op.csrf)&&state.conversation===op.conversation&&state.composerRevision===op.revision&&navigation.view==="chat"&&!document.hidden&&state.online;}
function updateVoiceControls(){
  const op=state.voice,blocked=state.attachments.length||state.sending||state.pendingRequest||state.chatActive.size||state.historyBusy||state.chatAction;
  ui.record.disabled=!state.online||!state.historyReady||!state.voiceReady||Boolean(op)||Boolean(blocked)||Boolean(ui.message.value);
  ui.record.hidden=Boolean(op);ui.stopVoice.hidden=op?.phase!=="recording";ui.discardVoice.hidden=!op;
  ui.message.readOnly=Boolean(op);if(op)ui.send.disabled=true;
  if(!op&&state.online&&state.voiceReady&&ui.voiceStatus.textContent.startsWith("Local voice unavailable."))ui.voiceStatus.textContent=`Record up to ${state.voiceMax/1000} seconds. Review transcript, then Send.`;
}
function closeVoiceGraph(op){
  clearTimeout(op.permissionTimer);clearTimeout(op.timer);clearTimeout(op.tick);clearTimeout(op.drainTimer);
  op.stream?.getTracks().forEach(track=>{track.onended=null;track.onmute=null;track.stop();});op.stream=null;
  if(op.node){op.node.onprocessorerror=null;op.node.port.onmessage=null;op.node.port.close();op.node.disconnect();op.node=null;}
  op.source?.disconnect();op.source=null;
  if(op.context){op.context.onstatechange=null;op.context.close().catch(()=>{});op.context=null;}
}
function discardVoice(label="Recording discarded. Type or record a new message."){
  const op=state.voice;if(!op)return;
  state.voice=null;op.abort.abort();op.drain?.();closeVoiceGraph(op);op.chunks=[];
  ui.voiceStatus.textContent=label;updateControls();
}
async function recordMessage(){
  updateVoiceControls();if(ui.record.disabled||navigation.view!=="chat"||document.hidden)return;
  if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext||!window.AudioWorkletNode){ui.voiceStatus.textContent="Microphone capture unsupported. Type a message.";return;}
  const op={generation:state.sessionGeneration,csrf:state.csrf,conversation:state.conversation,revision:state.composerRevision,phase:"permission",abort:new AbortController(),chunks:[],bytes:0};state.voice=op;
  ui.voiceStatus.textContent="Requesting microphone permission. Discard or Escape cancels.";updateControls();
  op.permissionTimer=setTimeout(()=>{if(state.voice===op)discardVoice("Microphone permission timed out. Type or record again.");},30000);
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:16000,echoCancellation:true,noiseSuppression:true},video:false});
    if(!voiceCurrent(op)){stream.getTracks().forEach(track=>track.stop());return;}
    op.stream=stream;stream.getTracks().forEach(track=>{track.onended=track.onmute=()=>discardVoice("Microphone interrupted. Recording discarded.");});
    op.context=new window.AudioContext({sampleRate:16000});
    if(op.context.sampleRate<16000||op.context.sampleRate>96000)throw new Error("Unsupported sample rate");
    await op.context.audioWorklet.addModule("/app/pcm-worklet.js?v=12");if(!voiceCurrent(op))return;
    op.node=new window.AudioWorkletNode(op.context,"jarvis-pcm",{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1],processorOptions:{maxSamples:state.voiceMax*16}});
    // Worklet writes only zeros to this output; connection keeps browser render graph pulling.
    op.node.connect(op.context.destination);
    op.node.onprocessorerror=()=>discardVoice("Audio capture failed. Type a message.");
    op.node.port.onmessage=event=>{
      if(!voiceCurrent(op))return;
      if(event.data.error){discardVoice("Audio capture overloaded. Type a message.");return;}
      if(event.data.pcm){
        const bytes=new Uint8Array(event.data.pcm);
        if(bytes.length>2048||bytes.length%2||op.bytes+bytes.length>state.voiceMax*32){discardVoice("Recording limit exceeded. Type or record again.");return;}
        op.chunks.push(bytes);op.bytes+=bytes.length;op.node?.port.postMessage("ack");
      }
      if(event.data.done){if(op.drain)op.drain();else stopRecording(op,true);}
    };
    op.source=op.context.createMediaStreamSource(stream);op.source.connect(op.node);
    await op.context.resume();if(!voiceCurrent(op))return;
    clearTimeout(op.permissionTimer);op.phase="recording";op.started=Date.now();
    op.context.onstatechange=()=>{if(op.context?.state!=="running")discardVoice("Audio context interrupted. Recording discarded.");};
    const tick=()=>{if(state.voice!==op||op.phase!=="recording")return;ui.voiceStatus.textContent=`Microphone on: ${Math.floor((Date.now()-op.started)/1000)} seconds. Stop or Discard.`;op.tick=setTimeout(tick,1000);};tick();
    op.timer=setTimeout(()=>stopRecording(op),state.voiceMax);updateControls();ui.stopVoice.focus();
  }catch{if(state.voice===op)discardVoice("Microphone unavailable or permission denied. Type a message.");}
}
async function stopRecording(op=state.voice,done=false){
  if(!op||!voiceCurrent(op)||op.phase!=="recording")return;
  op.phase="stopping";clearTimeout(op.timer);clearTimeout(op.tick);
  op.stream?.getTracks().forEach(track=>{track.onended=null;track.onmute=null;track.stop();});
  ui.voiceStatus.textContent="Microphone off. Preparing local transcription.";updateControls();
  if(!done)await new Promise(resolve=>{op.drain=resolve;op.drainTimer=setTimeout(()=>{discardVoice("Audio capture did not finish. Type or record again.");resolve();},1000);op.node.port.postMessage("stop");});
  if(!voiceCurrent(op))return;closeVoiceGraph(op);
  if(op.bytes<3840){discardVoice("Recording too short. Type or record again.");return;}
  const pcm=new Uint8Array(op.bytes);let offset=0;for(const chunk of op.chunks){pcm.set(chunk,offset);offset+=chunk.length;}op.chunks=[];
  op.phase="transcribing";ui.voiceStatus.textContent="Transcribing locally. Discard or Escape cancels.";updateControls();
  try{
    const result=await(await api("/client/voice/transcriptions",{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:pcm,signal:op.abort.signal})).json();
    if(!voiceCurrent(op)||ui.message.value)return;
    if(typeof result.text!=="string"||!result.text.trim()||result.text.length>100000)throw new Error("Invalid transcript");
    ui.message.value=result.text;state.composerRevision++;state.voice=null;ui.voiceStatus.textContent="Review transcript, then Send.";updateControls();ui.message.focus();
  }catch{if(state.voice===op)discardVoice("Local transcription unavailable. Type or record again.");}
  finally{if(state.voice===op)discardVoice();}
}
ui.record.addEventListener("click",recordMessage);
ui.stopVoice.addEventListener("click",()=>stopRecording());
ui.discardVoice.addEventListener("click",()=>{discardVoice();ui.record.focus();});
ui.message.addEventListener("input",()=>{state.composerRevision++;if(state.voice)discardVoice();updateVoiceControls();});
ui.message.addEventListener("compositionstart",()=>{state.composing=true;ui.send.disabled=true;});
ui.message.addEventListener("compositionend",()=>{state.composing=false;updateControls();});
ui.message.addEventListener("keydown",event=>{
  if(event.key!=="Enter"||(!event.ctrlKey&&!event.metaKey))return;
  event.preventDefault();if(state.composing||event.isComposing||event.keyCode===229||event.repeat)return;
  if(!ui.send.disabled)ui.chat.requestSubmit();
});
document.addEventListener("keydown",event=>{if(event.key==="Escape"&&state.voice){event.preventDefault();discardVoice();ui.record.focus();}});
window.addEventListener("pagehide",()=>discardVoice());
document.addEventListener("visibilitychange",()=>{if(document.hidden)discardVoice();});
function updateWorkflowControls(){
  const blocked=Boolean(state.sending||state.pendingRequest||state.chatActive.size||state.historyBusy||state.chatAction);
  ui.attachmentFile.disabled=!state.online||!state.historyReady||!state.attachmentsAllowed||blocked||Boolean(state.voice)||state.attachments.length+state.reuseSelected.size>=4;
  if(state.composing||state.attachments.some(item=>item.phase!=="ready"))ui.send.disabled=true;
  ui.searchQuery.disabled=!state.online;ui.searchSubmit.disabled=!state.online;
  ui.searchMore.disabled=!state.online||Boolean(state.search);
  for(const item of ui.searchResults.children)for(const button of item.children)if(button.tagName==="BUTTON"||button.type==="button")button.disabled=!state.online||blocked;
  ui.moreTasks.disabled=!state.online||Boolean(state.tasksBusy);
  for(const item of ui.tasks.children)for(const button of item.children||[])button.disabled=!state.online;
  ui.cancelTask.disabled=true;
  ui.previousTasks.disabled=!state.online||Boolean(state.tasksBusy);
  ui.taskFilter.disabled=ui.taskSort.disabled=!state.online;
  ui.eventsOlder.disabled=ui.eventsLatest.disabled=!state.online||Boolean(state.timelineRead);
  const libraryBlocked=!state.online||blocked||Boolean(state.libraryRead||state.libraryMutation);
  for(const control of [ui.libraryRefresh,ui.libraryArchived,ui.libraryPrevious,ui.libraryNext])control.disabled=libraryBlocked;
  for(const row of ui.library.children)for(const control of row.controls||[])control.disabled=libraryBlocked;
  ui.library.setAttribute("aria-busy",String(Boolean(state.libraryRead||state.libraryMutation)));
  ui.conversationAttachments.setAttribute("aria-busy",String(Boolean(state.attachmentRead)));
  ui.taskEvents.setAttribute("aria-busy",String(Boolean(state.timelineRead)));
  const attachmentBlocked=!state.online||!state.conversation||Boolean(state.attachmentRead);
  for(const control of [ui.refreshAttachments,ui.attachmentsPrevious,ui.attachmentsNext])control.disabled=attachmentBlocked;
  for(const row of ui.conversationAttachments.children)if(row.reuse)row.reuse.disabled=attachmentBlocked||blocked||Boolean(state.voice)||!row.ready||(!state.reuseSelected.has(row.attachmentId)&&state.reuseSelected.size+state.attachments.length>=4);
  if(state.reuseSelected.size&&!state.attachmentPage)ui.send.disabled=true;
}
function renderLibrary(page){
  state.libraryPage=page;ui.library.replaceChildren();
  for(const saved of page.conversations.slice(0,20)){
    const item=document.createElement("li"),open=document.createElement("button"),excerpt=document.createElement("p"),stamp=document.createElement("p"),form=document.createElement("form"),label=document.createElement("label"),title=document.createElement("input"),rename=document.createElement("button"),pin=document.createElement("button"),archive=document.createElement("button");
    open.type="button";open.className="secondary";open.textContent=`${saved.pinned?"Pinned · ":""}${saved.title||"Conversation"}`;
    open.dataset.conversation=saved.id;
    open.setAttribute("aria-current",saved.id===state.conversation?"true":"false");
    open.addEventListener("click",()=>guarded(()=>chooseConversation(saved.id)));
    excerpt.textContent=saved.excerpt||"No messages yet.";stamp.textContent=`Updated ${Number.isFinite(Date.parse(saved.updated_at))?new Date(saved.updated_at).toLocaleString():"time unavailable"}`;
    title.type="text";title.maxLength=80;title.value=saved.title||"";title.autocomplete="off";title.id=`rename-${saved.id}`;label.setAttribute("for",title.id);label.textContent="Conversation title";
    rename.type="submit";rename.textContent="Save title";pin.type=archive.type="button";pin.textContent=saved.pinned?"Unpin":"Pin";archive.textContent=saved.archived?"Unarchive":"Archive";
    for(const button of [rename,pin,archive])button.className="secondary";
    form.addEventListener("submit",event=>{event.preventDefault();guarded(()=>changeConversationMetadata(saved,{title:title.value}));});
    pin.addEventListener("click",()=>guarded(()=>changeConversationMetadata(saved,{pinned:!saved.pinned})));
    archive.addEventListener("click",()=>guarded(()=>changeConversationMetadata(saved,{archived:!saved.archived})));
    form.append(label,title,rename);item.append(open,excerpt,stamp,form,pin,archive);item.controls=[open,title,rename,pin,archive];ui.library.append(item);
  }
  ui.libraryPrevious.hidden=state.libraryOffset===0;ui.libraryNext.hidden=!page.has_more;
  ui.libraryState.textContent=page.conversations.length?`${state.libraryArchived?"Archived":"Active"} conversations ${state.libraryOffset+1}–${state.libraryOffset+page.conversations.length}. Select to open.`:`No ${state.libraryArchived?"archived":"active"} conversations.`;
  updateControls();
}
function cancelLibrary(){state.libraryRead?.abort.abort();state.libraryRead=null;if(state.libraryPage)ui.libraryState.textContent="Shown library may be stale. Refresh library before editing.";}
function attachmentRecovery(code){
  const messages={storage_quota:"Core attachment capacity reached. Wait for retention expiry or ask trusted host to review storage. Draft kept.",attachment_unavailable:"Selected attachment expired or unavailable. Refresh attachment status, review selection, then Send a new request. Draft kept.",processing_interrupted:"Core processing interrupted. No automatic retry. Select original file again after reviewing status. Draft kept.",processing_timeout:"Parser timed out. Choose a smaller supported file and Send a new request. Draft kept.",attachments_disabled:"Attachments unavailable on Core. Ask trusted host to check existing configuration. Draft kept.",processing_rejected:"Parser rejected file. Choose a readable TXT/MD, text PDF or supported PNG/JPEG. No automatic reprocessing.",processing_cancelled:"Processing cancelled. Select original file again only when ready to Send."};
  return Object.hasOwn(messages,code)?messages[code]:"";
}
function cancelAttachmentRead(){state.attachmentRead?.abort.abort();state.attachmentRead=null;clearTimeout(state.attachmentTimer);state.attachmentTimer=null;if(state.attachmentPage)ui.conversationAttachmentsState.textContent="Displayed attachment status may be stale. Refresh after reconnecting.";}
function clearAttachmentMetadata(){cancelAttachmentRead();state.attachmentPage=null;state.attachmentOffset=0;state.reuseSelected.clear();ui.conversationAttachments.replaceChildren();ui.conversationAttachmentsState.textContent="Open a saved conversation to inspect attachments.";ui.attachmentsNext.hidden=ui.attachmentsPrevious.hidden=true;}
function renderAttachmentMetadata(page){
  if(page.conversation_id!==state.conversation)return;
  state.attachmentPage=page;ui.conversationAttachments.replaceChildren();let processing=false;
  for(const attachment of page.attachments.slice(0,20)){
    const item=document.createElement("li"),label=document.createElement("p"),source=document.createElement("p"),reuse=document.createElement("button");
    const expired=attachment.expires_at&&Date.parse(attachment.expires_at)<=Date.now(),status=expired?"expired":attachment.status;
    if(status!=="ready"||page.available===false)state.reuseSelected.delete(attachment.id);
    label.textContent=`${attachment.filename||"Unavailable attachment"} · ${attachment.byte_size||0} bytes · ${status}${page.available===false?" · unavailable on Core":""}${attachment.expires_at?` · expires ${new Date(attachment.expires_at).toLocaleString()}`:""}`;
    source.textContent=`Source ${attachment.id}${attachment.request_ids?.length?` · used by ${attachment.request_ids.length} recent request(s)`:" · earlier conversation attachment"}. ${attachmentRecovery(attachment.error_code)}${status==="expired"||status==="unavailable"?" Select original file again; Send remains deliberate.":""}${attachment.media_type?.startsWith("image/")&&!page.vision_available?" Local vision unavailable; image cannot be interpreted. Use text or ask trusted host to check an already installed model.":""}`;
    reuse.type="button";reuse.className="secondary";reuse.textContent=state.reuseSelected.has(attachment.id)?`Remove reuse ${attachment.filename}`:`Reuse ${attachment.filename||"attachment"}`;reuse.setAttribute("aria-pressed",String(state.reuseSelected.has(attachment.id)));
    reuse.addEventListener("click",()=>{if(state.reuseSelected.has(attachment.id))state.reuseSelected.delete(attachment.id);else if(state.attachments.length+state.reuseSelected.size<4)state.reuseSelected.add(attachment.id);reuse.textContent=state.reuseSelected.has(attachment.id)?`Remove reuse ${attachment.filename}`:`Reuse ${attachment.filename}`;reuse.setAttribute("aria-pressed",String(state.reuseSelected.has(attachment.id)));updateControls();});
    item.reuse=reuse;item.attachmentId=attachment.id;item.ready=status==="ready"&&page.available!==false;processing ||= status==="processing";item.append(label,source,reuse);ui.conversationAttachments.append(item);
    for(const id of attachment.request_ids||[]){const message=ui.log.querySelector(`[data-request="${CSS.escape(id+":user")}"]`);if(message){if(!message.attachmentLabel){message.attachmentLabel=document.createElement("p");message.append(message.attachmentLabel);}message.attachmentLabel.textContent="Attachment source metadata available below composer.";}}
  }
  ui.attachmentsPrevious.hidden=state.attachmentOffset===0;ui.attachmentsNext.hidden=!page.has_more;
  ui.conversationAttachmentsState.textContent=page.attachments.length?`Core attachment status checked. ${state.reuseSelected.size} selected for reuse; review, then Send.`:"No persisted attachments in this conversation.";
  if(processing)scheduleAttachmentRefresh();else state.attachmentPending=false;
  updateControls();
}
function scheduleAttachmentRefresh(){
  clearTimeout(state.attachmentTimer);state.attachmentTimer=null;
  if(state.csrf&&state.online&&state.conversation&&navigation.view==="chat"&&!document.hidden)state.attachmentTimer=setTimeout(()=>loadAttachmentMetadata(),2000);
}
async function loadAttachmentMetadata({offset=state.attachmentOffset}={}){
  if(PROTOTYPE&&!PRIVATE_FILES)return;
  if(!state.online||!state.conversation)return;cancelAttachmentRead();
  const op={generation:state.sessionGeneration,csrf:state.csrf,conversation:state.conversation,abort:new AbortController()};state.attachmentRead=op;ui.conversationAttachmentsState.textContent="Checking Core attachment status…";updateControls();
  const current=()=>state.attachmentRead===op&&currentSession(op.generation,op.csrf)&&state.conversation===op.conversation&&state.online;
  try{
    const page=await(await api(`/client/conversations/${encodeURIComponent(op.conversation)}/attachments?offset=${offset}`,{signal:op.abort.signal})).json();
    if(current()&&page.conversation_id===op.conversation){state.attachmentOffset=offset;renderAttachmentMetadata(page);}
  }catch(error){if(current()&&error.name!=="AbortError")ui.conversationAttachmentsState.textContent="Attachment status unavailable. Refresh after reconnecting. No upload or processing resumes automatically.";}
  finally{if(state.attachmentRead===op)state.attachmentRead=null;updateControls();}
}
ui.refreshAttachments.addEventListener("click",()=>loadAttachmentMetadata({offset:0}));
ui.attachmentsPrevious.addEventListener("click",()=>loadAttachmentMetadata({offset:Math.max(0,state.attachmentOffset-20)}));
ui.attachmentsNext.addEventListener("click",()=>loadAttachmentMetadata({offset:state.attachmentPage?.next_offset||0}));
async function loadLibrary({offset=0,focus=false}={}){
  if(!state.online)return;cancelLibrary();
  const op={generation:state.sessionGeneration,csrf:state.csrf,abort:new AbortController(),focus:document.activeElement},archived=ui.libraryArchived.checked===true;
  state.libraryRead=op;ui.libraryState.textContent="Loading conversation library…";updateControls();
  const current=()=>state.libraryRead===op&&currentSession(op.generation,op.csrf)&&state.online;
  try{
    const page=await(await api("/client/conversations/library",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({archived,offset,revision:offset?state.libraryPage?.revision:null}),signal:op.abort.signal})).json();
    if(!current())return;state.libraryOffset=offset;state.libraryArchived=archived;renderLibrary(page);
    if(focus&&navigation.view==="chat"&&(document.activeElement===op.focus||document.activeElement===document.body))ui.libraryTitle.focus();
  }catch(error){if(current()&&error.name!=="AbortError"){ui.libraryState.textContent=error.status===409?"Library changed on Core. Refresh library to restart pagination.":"Library unavailable. Refresh library after reconnecting.";ui.libraryNext.hidden=true;}}
  finally{if(state.libraryRead===op)state.libraryRead=null;updateControls();}
}
async function changeConversationMetadata(saved,change){
  if(!state.online||state.libraryMutation||state.pendingRequest)return;
  const op={generation:state.sessionGeneration,csrf:state.csrf,focus:document.activeElement};state.libraryMutation=op;updateControls();
  try{
    (await api(`/client/conversations/${encodeURIComponent(saved.id)}/metadata`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision:saved.revision,title:saved.title||null,pinned:Boolean(saved.pinned),archived:Boolean(saved.archived),...change})})).discard();
    if(currentSession(op.generation,op.csrf)&&state.online&&navigation.view==="chat"){await loadLibrary({focus:document.activeElement===op.focus||document.activeElement===document.body});if(currentSession(op.generation,op.csrf)&&state.libraryMutation===op)ui.libraryState.textContent+=" Change saved on Core.";}
  }catch(error){if(currentSession(op.generation,op.csrf))ui.libraryState.textContent=error.status===409?"Concurrent change. Your edit was not applied. Refresh library, review latest metadata, then edit again.":"Change outcome unavailable. Refresh library before retrying; no automatic retry.";}
  finally{if(state.libraryMutation===op)state.libraryMutation=null;updateControls();}
}
ui.libraryRefresh.addEventListener("click",()=>loadLibrary());
ui.libraryArchived.addEventListener("change",()=>loadLibrary({focus:true}));
ui.libraryPrevious.addEventListener("click",()=>loadLibrary({offset:Math.max(0,state.libraryOffset-20),focus:true}));
ui.libraryNext.addEventListener("click",()=>loadLibrary({offset:state.libraryPage?.next_offset||0,focus:true}));
function renderAttachments(){
  const focused=document.activeElement?.dataset?.attachment;
  ui.attachments.replaceChildren();
  for(const item of state.attachments){
    const row=document.createElement("li"),label=document.createElement("p"),progress=document.createElement("progress"),remove=document.createElement("button");
    label.textContent=`${item.name} · ${item.size} bytes · ${item.phase==="ready"?"Staged in temporary Core memory. Review, then Send to process.":item.phase==="failed"?`${item.error||"Upload failed or expired."} Remove and select again.`:"Uploading…"}`;
    progress.max=100;progress.value=item.progress;progress.setAttribute("aria-label",`Upload ${item.name}`);
    remove.type="button";remove.className="secondary";remove.textContent=item.phase==="uploading"?`Cancel upload ${item.name}`:`Remove ${item.name}`;
    remove.dataset.attachment=item.id;
    remove.addEventListener("click",()=>{removeAttachment(item);updateControls();ui.attachmentFile.focus();});row.append(label,progress,remove);
    if(item.url){const image=document.createElement("img");image.src=item.url;image.alt=`Selected photo: ${item.name}`;row.append(image);}
    if(item.preview){const preview=document.createElement("pre");preview.textContent=item.preview;row.append(preview);}
    if(item.type==="application/pdf"){const preview=document.createElement("p");preview.textContent="PDF selected. Core extracts text after Send; embedded content is not opened.";row.append(preview);}
    ui.attachments.append(row);
    if(focused===item.id)remove.focus({preventScroll:true});
  }
}
function removeAttachment(item,{discard=true}={}){
  state.attachments=state.attachments.filter(value=>value!==item);
  item.xhr?.abort();item.xhr=null;clearTimeout(item.timer);
  if(item.url)URL.revokeObjectURL(item.url);item.url=null;item.preview=null;
  if(discard&&state.csrf)api(`/client/attachments/${item.id}`,{method:"DELETE"}).then(response=>response.discard()).catch(()=>{});
  renderAttachments();
}
function clearAttachments(options={}){for(const item of [...state.attachments])removeAttachment(item,options);ui.attachmentFile.value="";}
async function selectAttachments(files){
  updateControls();if(ui.attachmentFile.disabled)return;
  const generation=state.sessionGeneration,csrf=state.csrf,conversation=state.conversation;
  for(const file of files){
    if(state.attachments.length+state.reuseSelected.size>=4){ui.attachmentState.textContent="Four-file limit. Remove a file before selecting another.";break;}
    const extension=file.name.split(".").pop().toLowerCase(),type={txt:"text/plain",md:"text/plain",pdf:"application/pdf",png:"image/png",jpg:"image/jpeg",jpeg:"image/jpeg"}[extension];
    if(!type||file.size<=0||file.size>1048576||file.name.length>120){ui.attachmentState.textContent="Unsupported or oversized file. Choose PNG/JPEG, PDF or TXT/MD, 1 byte–1 MiB each.";continue;}
    const item={id:crypto.randomUUID().replaceAll("-",""),name:file.name,size:file.size,type,phase:"uploading",progress:0,xhr:null};
    state.attachments.push(item);
    const current=()=>currentSession(generation,csrf)&&state.conversation===conversation&&state.attachments.includes(item)&&state.online;
    if(type.startsWith("image/"))item.url=URL.createObjectURL(file);
    if(type==="text/plain")file.slice(0,2048).text().then(text=>{if(current()){item.preview=text.slice(0,1000);renderAttachments();}}).catch(()=>{});
    renderAttachments();updateControls();
    try{
      const xhr=new XMLHttpRequest();item.xhr=xhr;
      xhr.open("POST",`${API}/client/attachments/${item.id}`);xhr.withCredentials=true;xhr.responseType="json";xhr.timeout=20000;
      xhr.setRequestHeader("Content-Type",type);xhr.setRequestHeader("X-Jarvis-CSRF",csrf);xhr.setRequestHeader("X-Jarvis-Filename",encodeURIComponent(file.name));
      xhr.upload.onprogress=event=>{if(current()&&event.lengthComputable){item.progress=Math.min(99,Math.round(event.loaded/event.total*100));renderAttachments();}};
      const failed=(message="Upload failed.")=>{if(current()){item.phase="failed";item.error=message;item.xhr=null;renderAttachments();updateControls();}};
      xhr.onerror=()=>failed("Network upload failed.");xhr.ontimeout=()=>failed("Upload timed out.");xhr.onabort=()=>failed("Upload cancelled.");
      xhr.onload=()=>{
        if(!current())return;item.xhr=null;
        if(xhr.status===401){invalidateSession();return;}
        if(xhr.status!==201||xhr.response?.id!==item.id||xhr.response?.status!=="staged"){failed(({403:"Upload access denied.",409:"Upload unavailable or capacity reached.",413:"File exceeds upload limit.",422:"Filename or file type rejected.",429:"Too many uploads. Wait before selecting again.",503:"Attachments disabled on Core."})[xhr.status]||"Upload failed.");return;}
        item.phase="ready";item.progress=100;
        item.timer=setTimeout(()=>{if(current()){item.phase="failed";item.error="Temporary upload expired.";item.preview=null;if(item.url)URL.revokeObjectURL(item.url);item.url=null;renderAttachments();updateControls();}},600000);
        ui.attachmentState.textContent="Uploaded to temporary Core memory for up to 10 minutes. Review, then Send. Removing or leaving Chat discards selection.";
        renderAttachments();updateControls();
      };
      xhr.send(file);
    }catch{if(current()){item.phase="failed";renderAttachments();updateControls();}}
  }
  ui.attachmentFile.value="";
}
function clearSearch({erase=false}={}){
  state.search?.abort.abort();state.search=null;state.searchBefore=null;state.searchQuery="";
  ui.searchResults.replaceChildren();ui.searchMore.hidden=true;ui.searchState.textContent="";
  if(erase)ui.searchQuery.value="";
}
async function searchHistory({more=false}={}){
  if(!state.online)return;
  const query=ui.searchQuery.value.trim();if(!query){clearSearch();ui.searchState.textContent="Enter text to search saved messages.";return;}
  const before=more&&query===state.searchQuery?state.searchBefore:null;
  if(more&&!before)return;
  state.search?.abort.abort();
  const op={generation:state.sessionGeneration,csrf:state.csrf,abort:new AbortController()};state.search=op;state.searchQuery=query;
  const current=()=>state.search===op&&currentSession(op.generation,op.csrf)&&state.online;
  if(!more)ui.searchResults.replaceChildren();ui.searchState.textContent="Searching Core history…";ui.searchMore.hidden=true;updateControls();
  try{
    const page=await(await api("/client/conversations/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,before}),signal:op.abort.signal})).json();
    if(!current())return;
    for(const match of page.results){
      if(ui.searchResults.children.length>=100){ui.searchState.textContent="100 matching messages shown. Refine search to browse more.";break;}
      const item=document.createElement("li"),button=document.createElement("button"),excerpt=document.createElement("p");button.type="button";button.className="secondary";
      button.textContent=`Open ${match.role==="user"?"your message":"JARVIS reply"} · message ${match.sequence}`;excerpt.textContent=match.excerpt;
      button.addEventListener("click",()=>guarded(()=>chooseConversation(match.conversation_id,match.sequence)));item.append(button,excerpt);ui.searchResults.append(item);
    }
    state.searchBefore=page.next_before;ui.searchMore.hidden=!page.has_more||ui.searchResults.children.length>=100;
    ui.searchState.textContent=ui.searchResults.children.length?`${ui.searchResults.children.length} matching messages shown.`:"No matching messages.";
  }catch(error){if(current()&&error.name!=="AbortError")ui.searchState.textContent="Search failed. Search again after connection recovers.";}
  finally{if(state.search===op)state.search=null;updateControls();}
}
function cancelTaskRead(){
  state.timelineRead?.abort.abort();state.timelineRead=null;
  state.taskRead?.abort.abort();state.taskRead=null;clearTimeout(state.taskTimer);state.taskTimer=null;
  if(state.taskSelected)ui.taskDetailState.textContent="Displayed task may be stale. Refresh tasks to recover current Core state.";
  if(state.taskChecked||state.tasksBusy)ui.tasksState.textContent="Displayed tasks may be stale. Refresh tasks after connection recovers.";
  if(state.taskSelected)ui.timelineState.textContent="Timeline may be stale. Refresh tasks to recover Core events.";
}
function renderTaskTimeline(page){
  if(page.task_id!==state.taskSelected)return;
  state.timelinePage=page;ui.taskEvents.replaceChildren();
  for(const event of page.events.slice(0,50)){
    const item=document.createElement("li");item.textContent=`${event.created_at?new Date(event.created_at).toLocaleString():"Time unavailable"} · ${String(event.event_type).replaceAll("_"," ")} · ${String(event.task_status).replaceAll("_"," ")}${event.node_id?` · step ${event.node_id}`:""}${event.node_status?` · ${String(event.node_status).replaceAll("_"," ")}`:""} · ${event.explanation||"Core state transition."}`;ui.taskEvents.append(item);
  }
  ui.eventsOlder.hidden=!page.has_more;ui.eventsLatest.hidden=state.timelineBefore===null;
  ui.timelineState.textContent=page.events.length?`${state.timelineBefore?"Earlier":"Latest"} ${page.events.length} Core events. Timeline is read-only.`:"No Core events available.";
}
async function loadTaskTimeline({before=null,focus=false}={}){
  if(!state.online||!state.taskSelected)return;
  state.timelineRead?.abort.abort();
  const op={generation:state.sessionGeneration,csrf:state.csrf,id:state.taskSelected,abort:new AbortController()};state.timelineRead=op;ui.timelineState.textContent="Loading Core events…";updateControls();
  const current=()=>state.timelineRead===op&&currentSession(op.generation,op.csrf)&&state.taskSelected===op.id&&state.online;
  try{
    const page=await(await api(`/client/tasks/${encodeURIComponent(op.id)}/events?limit=50${before?`&before=${before}`:""}`,{signal:op.abort.signal})).json();
    if(current()&&page.task_id===op.id){state.timelineBefore=before;renderTaskTimeline(page);if(focus)ui.timelineTitle.focus();}
  }catch(error){if(current()&&error.name!=="AbortError")ui.timelineState.textContent="Core timeline unavailable. Refresh tasks after reconnecting; displayed events may be stale.";}
  finally{if(state.timelineRead===op)state.timelineRead=null;updateControls();}
}
ui.eventsOlder.addEventListener("click",()=>loadTaskTimeline({before:state.timelinePage?.next_before,focus:true}));
ui.eventsLatest.addEventListener("click",()=>loadTaskTimeline({focus:true}));
function resetTaskList(){
  state.taskListAbort?.abort();state.taskListAbort=null;state.tasksBusy=false;state.taskRevision=null;state.taskPageOffset=0;
  return refreshTasks();
}
function cancelTaskList(){state.taskListAbort?.abort();state.taskListAbort=null;state.tasksBusy=false;}
ui.taskFilter.addEventListener("change",()=>guarded(resetTaskList));ui.taskSort.addEventListener("change",()=>guarded(resetTaskList));
ui.previousTasks.addEventListener("click",()=>guarded(()=>refreshTasks({offset:Math.max(0,state.taskPageOffset-50)})));
async function loadTask(id,{focus=false}={}){
  if(!state.online||!state.csrf)return;
  cancelTaskRead();if(state.taskSelected!==id){state.timelineBefore=null;state.timelinePage=null;ui.taskEvents.replaceChildren();}state.taskSelected=id;
  for(const item of ui.tasks.children){const button=item.children?.[0];if(button?.dataset.task)button.setAttribute("aria-current",String(button.dataset.task===id));}
  const op={generation:state.sessionGeneration,csrf:state.csrf,abort:new AbortController()};state.taskRead=op;
  const current=()=>state.taskRead===op&&currentSession(op.generation,op.csrf)&&state.online;
  ui.taskDetail.hidden=false;ui.taskDetailState.textContent="Loading task details…";ui.taskNodes.replaceChildren();ui.taskProgress.value=0;
  try{
    const task=await(await api(`/client/tasks/${encodeURIComponent(id)}`,{signal:op.abort.signal})).json();if(!current()||task.id!==id)return;
    ui.taskDetailTitle.textContent=task.objective;
    const completed=task.nodes.filter(node=>node.status==="completed").length;
    ui.taskProgress.max=task.nodes.length||1;ui.taskProgress.value=completed;
    ui.taskDetailState.textContent=`${task.status} · ${completed}/${task.nodes.length} steps complete · checked ${new Date().toLocaleTimeString()}${task.cancel_requested?" · cancellation requested; await Core state":""}`;
    for(const node of task.nodes){const item=document.createElement("li");item.textContent=`${node.id} · ${node.status} · ${node.attempts} attempts${node.failure_class?` · ${node.failure_class}`:""}${node.explanation?` · ${node.explanation}`:""}`;ui.taskNodes.append(item);}
    if(task.timeline){if(state.timelineBefore)await loadTaskTimeline({before:state.timelineBefore});else renderTaskTimeline(task.timeline);}
    if(!current())return;
    if(focus)ui.taskDetailTitle.focus();scheduleTaskRefresh();
  }catch(error){if(current()){ui.taskDetailTitle.textContent="Task details";ui.taskDetailState.textContent=error.status===404?"Task no longer available. Refresh tasks.":"Task details unavailable. Refresh tasks after connection recovers.";}}
  finally{if(state.taskRead===op)state.taskRead=null;updateControls();}
}
function scheduleTaskRefresh(delay=30000){
  clearTimeout(state.taskTimer);state.taskTimer=null;
  if(state.online&&navigation.view==="chat"&&!document.hidden)state.taskTimer=setTimeout(()=>refreshTasks().catch(()=>{}),delay);
}
function clearWorkflows(){
  state.composing=false;
  state.taskListAbort?.abort();state.taskListAbort=null;state.tasksBusy=false;state.taskPageOffset=0;state.taskRevision=null;state.timelineBefore=null;state.timelinePage=null;ui.taskEvents.replaceChildren();ui.timelineState.textContent="";ui.eventsOlder.hidden=ui.eventsLatest.hidden=ui.previousTasks.hidden=true;ui.taskFilter.value="";ui.taskSort.value="newest";
  clearAttachmentMetadata();state.reuseDrafts.clear();state.reuseSelected.clear();state.attachmentPending=false;
  cancelLibrary();state.libraryMutation=null;state.libraryPage=null;state.libraryOffset=0;state.libraryArchived=false;ui.libraryArchived.checked=false;ui.library.replaceChildren();ui.libraryState.textContent="Connect to browse saved conversations.";ui.libraryNext.hidden=ui.libraryPrevious.hidden=true;
  clearAttachments();clearSearch({erase:true});cancelTaskRead();state.taskSelected=null;state.taskOffset=0;state.taskChecked=0;
  state.threadDrafts.clear();ui.message.value="";state.composerRevision++;state.attachmentsAllowed=false;
  ui.taskDetail.hidden=true;ui.taskDetailTitle.textContent="Task details";ui.taskDetailState.textContent="";ui.taskNodes.replaceChildren();ui.taskProgress.value=0;ui.moreTasks.hidden=true;
}
ui.attachmentFile.addEventListener("change",()=>selectAttachments(Array.from(ui.attachmentFile.files||[])));
ui.searchForm.addEventListener("submit",event=>{event.preventDefault();searchHistory();});
ui.searchQuery.addEventListener("input",()=>clearSearch());
ui.searchClear.addEventListener("click",()=>{clearSearch({erase:true});updateControls();ui.searchQuery.focus();});
ui.searchMore.addEventListener("click",()=>searchHistory({more:true}));
ui.moreTasks.addEventListener("click",()=>guarded(()=>refreshTasks({more:true})));
window.addEventListener("pagehide",()=>{clearAttachments();clearSearch();cancelTaskRead();});
document.addEventListener("visibilitychange",()=>{if(document.hidden){clearAttachments();clearSearch();cancelTaskRead();}});
async function guarded(action){try{await action();}catch(error){announce(typeof error.message==="string"?error.message:"Operation failed safely");}}

ui.enroll.addEventListener("click",()=>guarded(enroll));ui.connect.addEventListener("click",()=>guarded(connect));ui.chat.addEventListener("submit",sendMessage);ui.notify.addEventListener("click",()=>guarded(enableNotifications));ui.logout.addEventListener("click",()=>guarded(logout));ui.refreshTasks.addEventListener("click",()=>guarded(resetTaskList));
ui.cancelChat.addEventListener("click",()=>guarded(cancelChat));ui.retryChat.addEventListener("click",()=>guarded(retryChat));ui.refreshHistory.addEventListener("click",()=>guarded(()=>refreshHistory()));ui.olderHistory.addEventListener("click",()=>guarded(()=>refreshHistory({older:true})));ui.newConversation.addEventListener("click",()=>guarded(()=>chooseConversation(null)));ui.conversations.addEventListener("change",()=>guarded(()=>chooseConversation(ui.conversations.value)));
window.addEventListener("offline",()=>{state.streamAbort?.abort();setConnected(false,"Network offline");ui.accessStatus.textContent="Network offline. Chat disabled; recovery will check the live connection.";state.streamWake?.();});
window.addEventListener("online",()=>{
  setConnected(false,state.csrf?"Reconnecting":"Online — connect device");
  if(state.csrf&&state.subscription&&!state.connecting)startStreamOwnership();
  else if(!state.connecting)ui.accessStatus.textContent=state.hasIdentity?"Connect existing device to start a fresh authenticated session.":"Paste an approved ticket to enroll.";
});
window.addEventListener("pageshow",()=>{renderGarminStatus();if(state.csrf&&state.subscription&&!state.connecting){if(state.streamOwner)state.streamOwner.tasksPending=true;state.streamAbort?.abort();setConnected(false,"Checking live connection");startStreamOwnership();}});
document.addEventListener("visibilitychange",()=>{if(!document.hidden){renderGarminStatus();if(state.csrf&&state.subscription&&!state.connecting){if(state.streamOwner)state.streamOwner.tasksPending=true;state.streamAbort?.abort();setConnected(false,"Checking live connection");startStreamOwnership();}}});
if("serviceWorker" in navigator)navigator.serviceWorker.register("/app/sw.js?v=18",{scope:"/app/"}).catch(()=>announce("Offline shell unavailable"));
const initialGeneration=state.sessionGeneration;
loadIdentity().then(identity=>{if(state.sessionGeneration!==initialGeneration)return;state.hasIdentity=Boolean(identity);updateControls();if(identity){ui.accessStatus.textContent="Enrolled key found. Connect existing device to start a fresh session.";announce(ui.accessStatus.textContent);}}).catch(()=>{if(state.sessionGeneration===initialGeneration)announce("Device storage unavailable");});

// Local memory approval is a trusted-host surface, never a remote chat scope.
const memoryLink=document.querySelector("#memory-link");
if(memoryLink&&document.body.dataset.profile==="private-memory"&&["127.0.0.1","localhost","[::1]"].includes(window.location.hostname))memoryLink.hidden=false;
