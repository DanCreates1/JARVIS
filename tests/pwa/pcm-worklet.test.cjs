"use strict";
const {test}=require("node:test"),assert=require("node:assert/strict"),vm=require("node:vm"),fs=require("node:fs"),path=require("node:path");
const script=fs.readFileSync(path.join(__dirname,"../../src/jarvis/pwa/pcm-worklet.js"),"utf8");
function harness(rate,limit=480000,ack=true){
  let Processor,processor;const messages=[];
  const context=vm.createContext({sampleRate:rate,AudioWorkletProcessor:class{port={onmessage:null,postMessage(data){messages.push(data);if(data.pcm&&ack)processor.port.onmessage({data:"ack"});}};},registerProcessor(name,value){assert.equal(name,"jarvis-pcm");Processor=value;}});
  vm.runInContext(script,context);processor=new Processor({processorOptions:{maxSamples:limit}});
  return {processor,messages,pcm:()=>Buffer.concat(messages.filter(m=>m.pcm).map(m=>Buffer.from(m.pcm)))};
}
for(const rate of [16000,44100,48000])test(`canonical PCM at ${rate} Hz survives irregular blocks and stereo downmix`,()=>{
  const h=harness(rate),seconds=2,length=rate*seconds,source=Float32Array.from({length},(_,i)=>0.5*Math.sin(2*Math.PI*440*i/rate));
  let cursor=0,block=0;const sizes=[1,127,128,513,37];
  while(cursor<length){const n=Math.min(sizes[block++%sizes.length],length-cursor),chunk=source.slice(cursor,cursor+n);h.processor.process([[chunk,chunk]]);cursor+=n;}
  h.processor.port.onmessage({data:"stop"});const pcm=h.pcm();assert.equal(pcm.length,seconds*32000);
  let crossings=0,energy=0,prior=0;for(let i=0;i<pcm.length;i+=2){const sample=pcm.readInt16LE(i);if(prior<0&&sample>=0)crossings++;energy+=(sample/32768)**2;prior=sample;}
  assert.ok(Math.abs(crossings/seconds-440)<1);assert.ok(Math.abs(Math.sqrt(energy/(pcm.length/2))-0.35355)<0.01);
  assert.ok(h.messages.filter(m=>m.pcm).every(m=>m.pcm.byteLength<=2048));assert.ok(h.messages.at(-1).done);
});
test("worklet clamps signed LE samples, enforces exact duration and stops after max",()=>{
  const h=harness(16000,1920),output=Float32Array.from({length:128},()=>1);for(let i=0;i<20;i++)h.processor.process([[Float32Array.from({length:128},(_,j)=>j%2?-2:2)]],[[output]]);
  assert.ok(output.every(sample=>sample===0),"Speaker output must always be silent");
  assert.equal(h.pcm().length,3840);assert.equal(h.pcm().readInt16LE(0),32767);assert.equal(h.pcm().readInt16LE(2),-32768);
  assert.equal(h.processor.process([[new Float32Array(128)]]),false);
});
test("worklet rejects nonfinite samples and bounds unacknowledged message backlog",()=>{
  const broken=harness(16000);broken.processor.process([[Float32Array.of(NaN)]]);assert.ok(broken.messages.at(-1).error);
  const slow=harness(16000,480000,false);for(let i=0;i<100;i++)slow.processor.process([[new Float32Array(128)]]);
  assert.equal(slow.messages.filter(m=>m.pcm).length,9);assert.ok(slow.messages.at(-1).error);
  assert.equal(harness(8000).processor.process([]),false);
});
test("30-second source at 48 kHz never emits more than 960000 bytes",()=>{
  const h=harness(48000);for(let i=0;i<12000;i++)h.processor.process([[new Float32Array(128)]]);
  assert.equal(h.pcm().length,960000);assert.ok(h.messages.at(-1).done);
});

test("cached shell denies microphone offline; live document always fetches current policy; API never cached",async()=>{
  const worker=fs.readFileSync(path.join(__dirname,"../../src/jarvis/pwa/sw.js"),"utf8"),listeners={},calls=[];
  let network=true;const cached=new Response("shell",{headers:{"Permissions-Policy":"microphone=(self)"}});
  const context=vm.createContext({URL,Headers,Response,self:{location:{origin:"https://jarvis.test"},addEventListener:(name,cb)=>listeners[name]=cb},caches:{match:async()=>cached.clone()},fetch:async(req,options)=>{calls.push({req,options});if(!network)throw new Error("offline");return new Response("live",{headers:{"Permissions-Policy":"microphone=()"}});}});
  vm.runInContext(worker,context);
  let promise;const event=url=>({request:{url,method:"GET"},respondWith:p=>promise=p});
  listeners.fetch(event("https://jarvis.test/app/"));assert.equal((await promise).headers.get("Permissions-Policy"),"microphone=()");assert.equal(calls.length,1);
  network=false;listeners.fetch(event("https://jarvis.test/app/"));assert.equal((await promise).headers.get("Permissions-Policy"),"camera=(), microphone=(), geolocation=()");
  promise=null;listeners.fetch(event("https://jarvis.test/api/v1/client/voice/transcriptions"));assert.equal(promise,null);assert.equal(calls.length,2);
});
