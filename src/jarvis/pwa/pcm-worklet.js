// Streaming area-average resampler. State spans render blocks; output never reaches speakers.
class PCMProcessor extends AudioWorkletProcessor{
  constructor(options){
    super();this.ratio=sampleRate/16000;this.area=0;this.weight=0;this.count=0;this.pending=0;
    this.limit=Math.min(480000,options.processorOptions?.maxSamples||480000);
    this.buffer=new Int16Array(1024);this.used=0;this.active=true;
    if(!Number.isFinite(this.ratio)||this.ratio<1||this.ratio>6)this.active=false;
    this.port.onmessage=event=>{
      if(event.data==="ack")this.pending=Math.max(0,this.pending-1);
      if(event.data==="stop"){this.active=false;this.flush();this.port.postMessage({done:true});}
    };
  }
  flush(){
    if(!this.used)return;
    const bytes=new ArrayBuffer(this.used*2),view=new DataView(bytes);
    for(let i=0;i<this.used;i++)view.setInt16(i*2,this.buffer[i],true);
    this.used=0;this.pending++;this.port.postMessage({pcm:bytes},[bytes]);
  }
  process(inputs,outputs=[]){
    for(const output of outputs)for(const channel of output)channel.fill(0);
    if(!this.active)return false;
    const channels=inputs[0];if(!channels?.length)return true;
    for(let i=0;i<channels[0].length&&this.active;i++){
      let value=0;for(const channel of channels)value+=channel[i]/channels.length;
      if(!Number.isFinite(value)){this.active=false;this.port.postMessage({error:true});break;}
      let left=1;
      while(left>1e-9&&this.active){
        const take=Math.min(left,this.ratio-this.weight);this.area+=value*take;this.weight+=take;left-=take;
        if(this.weight+1e-9>=this.ratio){
          const sample=Math.max(-1,Math.min(1,this.area/this.ratio));
          this.buffer[this.used++]=Math.round(sample*(sample<0?32768:32767));this.area=0;this.weight=0;this.count++;
          if(this.used===this.buffer.length)this.flush();
          if(this.pending>8){this.active=false;this.port.postMessage({error:true});}
          if(this.count>=this.limit){this.active=false;this.flush();this.port.postMessage({done:true});}
        }
      }
    }
    return this.active;
  }
}
registerProcessor("jarvis-pcm",PCMProcessor);
