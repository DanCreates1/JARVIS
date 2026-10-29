// Trusted-local review only. No service worker, storage, automatic reads or mutation retries.
const $=id=>document.getElementById(id);
let generation=0,controller=null,selected=null,offset=0,busy=false;
function text(id,value){$(id).textContent=value;}
function clearSelection(){selected=null;text("detail","");$("replacement").value="";for(const id of ["approve","reject","forget","correction"])$(id).hidden=true;}
function clear(){++generation;controller?.abort();controller=null;busy=false;document.querySelector("main").setAttribute("aria-busy","false");clearSelection();for(const id of ["items","hits"])$(id).replaceChildren();for(const id of ["projection","retention"])text(id,"");for(const id of ["query","new-content"])$(id).value="";$("previous").hidden=true;$("next").hidden=true;offset=0;text("status","Private view cleared. Inspect to reload.");}
async function run(work){
  if(busy)return;busy=true;document.querySelector("main").setAttribute("aria-busy","true");const current=++generation;controller=new AbortController();
  const active=controller,signal=active.signal,timer=setTimeout(()=>active.abort(),10000);
  const api=async(path,body,method)=>{
    const response=await fetch(path,{method:method||(body?"POST":"GET"),credentials:"omit",cache:"no-store",signal,headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});
    if(!response.ok)throw new Error(`Request failed (${response.status}).`);
    const value=await response.json();if(current!==generation||signal.aborted)throw new DOMException("Stale view","AbortError");return value;
  };
  try{await work(api);if(current===generation)text("status","Done. Changes require deliberate review.");}
  catch(error){if(current===generation){clearSelection();for(const id of ["items","hits"])$(id).replaceChildren();for(const id of ["projection","retention"])text(id,"");text("status",error.name==="AbortError"?"Request stopped. Inspect current state before retrying.":`${error.message} Inspect current state before retrying.`);}}
  finally{clearTimeout(timer);if(current===generation){busy=false;controller=null;document.querySelector("main").setAttribute("aria-busy","false");}}
}
async function list(api){
  clearSelection();$("items").replaceChildren();
  const params=new URLSearchParams({offset:String(offset)});for(const id of ["state","category"])if($(id).value)params.set(id,$(id).value);
  const page=await api(`/api/memory/workspace/items?${params}`);
  for(const item of page.items){const li=document.createElement("li"),button=document.createElement("button");button.type="button";button.className="secondary";button.textContent=`${item.category} · ${item.state} · ${item.content}${item.truncated?"…":""}`;button.addEventListener("click",()=>load(item.id));li.append(button);$("items").append(li);}
  $("previous").hidden=offset===0;$("next").hidden=!page.has_more||offset>=10000;
  if(!page.items.length)$("items").textContent="No items in this view.";
}
function load(id){return run(async api=>{
  clearSelection();const item=await api(`/api/memory/workspace/items/${encodeURIComponent(id)}`);selected=item;
  text("detail",JSON.stringify(item,null,2));$("replacement").value=item.content;
  $("approve").hidden=$("reject").hidden=item.state!=="candidate";$("correction").hidden=item.state!=="committed";$("forget").hidden=false;$("detail-title").focus();
});}
$("inspect").onclick=()=>{offset=0;return run(list);};
$("previous").onclick=()=>{offset=Math.max(0,offset-20);return run(list);};
$("next").onclick=()=>{offset=Math.min(10000,offset+20);return run(list);};
for(const id of ["state","category"])$(id).onchange=clear;
$("clear").onclick=clear;
$("approve").onclick=()=>{const item=selected;if(!item||!confirm(`Approve this exact candidate as durable context?\n\n${item.content}`))return;return run(async api=>{await api(`/api/memory/candidates/${encodeURIComponent(item.id)}/promote`,{expected_version:item.version,expected_content_sha256:item.content_sha256});await list(api);});};
$("reject").onclick=()=>{const item=selected;if(!item)return;return run(async api=>{await api(`/api/memory/workspace/items/${encodeURIComponent(item.id)}/reject`,{expected_version:item.version});await list(api);});};
$("forget").onclick=()=>{const item=selected;if(!item||!confirm("Permanently remove selected memory and sole-source derivatives from canonical memory? Other versions, transcripts and backups remain. This cannot be undone here."))return;return run(async api=>{await api(`/api/memories/${encodeURIComponent(item.id)}`,null,"DELETE");await list(api);text("projection","");$("hits").replaceChildren();});};
$("correction").onsubmit=event=>{event.preventDefault();const item=selected,content=$("replacement").value;if(!item||!confirm(`Commit this exact replacement? Old content stays as correction lineage.\n\n${content}`))return;return run(async api=>{await api(`/api/memory/${encodeURIComponent(item.id)}/correct`,{expected_version:item.version,content});await list(api);text("projection","");$("hits").replaceChildren();});};
$("remember").onsubmit=event=>{event.preventDefault();const content=$("new-content").value,category=$("new-category").value;if(!confirm(`Save this exact private owner context?\n\n${content}`))return;return run(async api=>{await api("/api/memories",{content,category,provenance:"explicit trusted local memory workspace"});$("new-content").value="";offset=0;await list(api);});};
$("search").onsubmit=event=>{event.preventDefault();const query=$("query").value;return run(async api=>{
  text("projection","");$("hits").replaceChildren();const result=await api("/api/memory/workspace/inspect",{query});
  text("projection",`${result.retrieval_enabled?"Recall enabled. Preview:":"Recall disabled. Inspection preview only:"}\n${result.projection||"No approved relevant context."}`);
  for(const hit of result.hits){const li=document.createElement("li"),button=document.createElement("button");button.type="button";button.className="secondary";button.textContent=`${hit.content} · ${hit.reason} · score ${hit.score.toFixed(3)} · ${hit.projected?"within projection budget":"outside projection budget"}`;button.onclick=()=>load(hit.id);li.append(button);$("hits").append(li);}
});};
$("retention-read").onclick=()=>run(async api=>text("retention",JSON.stringify(await api("/api/memory/workspace/retention"),null,2)));
$("retention-form").onsubmit=event=>{event.preventDefault();const category=$("retention-category").value,days=Number($("days").value);if(!confirm(`Set ${category} retention to ${days} days from creation for existing committed and future items? This can exclude older context immediately.`))return;return run(async api=>{await api("/api/memory/workspace/retention",{category,days});clearSelection();text("projection","");$("hits").replaceChildren();text("retention",JSON.stringify(await api("/api/memory/workspace/retention"),null,2));});};
$("expire").onclick=()=>run(async api=>{await api("/api/memory/workspace/expire",{});text("projection","");$("hits").replaceChildren();await list(api);});
window.addEventListener("pagehide",clear);
window.addEventListener("pageshow",event=>{if(event.persisted)clear();});
document.addEventListener("visibilitychange",()=>{if(document.hidden)clear();});
