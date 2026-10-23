const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=name=>fs.readFileSync(path.join(__dirname,'../src/static/'+name),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const origin='http://127.0.0.1:8012',task='a'.repeat(32),other='b'.repeat(32);
const run='20261022T010000Z-'+'d'.repeat(32);
const selected=(image='reference_001',revision=3,run_id=run,task_id=task)=>({task_id,image_id:image,revision,run_id});
class Element{
  constructor(){this.children=[];this.dataset={};this.attributes={};this._text='';this.hidden=false;this.value='';this.open=false;const classes=new Set();this.classList={toggle(k,force){const enabled=force??!classes.has(k);if(enabled)classes.add(k);else classes.delete(k);},add(k){classes.add(k);},remove(k){classes.delete(k);},contains:k=>classes.has(k)};}
  set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=[];this._text='';this.append(...items);}
  setAttribute(k,v){this.attributes[k]=v;}removeAttribute(k){delete this[k];}
  getAttribute(k){return this.attributes[k]??null;}
  getBoundingClientRect(){return {width:900,height:570,left:0,top:0};}
  setPointerCapture(){}
  showModal(){this.open=true;}close(){this.open=false;}focus(){this.focused=true;}
}
function clock(){
  let now=0,next=0;const timers=new Map();
  return {Date:class extends Date{static now(){return now;}},setTimeout(fn,ms){const id=++next;timers.set(id,{fn,at:now+ms});return id;},
    clearTimeout(id){timers.delete(id);},advance(ms){const end=now+ms;while(true){const due=[...timers].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}now=end;},timers};
}
function parentHarness({legacy=false,runtimeScope=false}={}){
  const nodes=new Map(['toggle-inspector','debug-sidebar','debug-inspector-frame','debug-sidebar-message','close-inspector','expand-inspector','local-debug-config','inspector-authorization'].map(k=>[k,new Element()]));
  nodes.get('expand-inspector').textContent='展开大视图';
  nodes.get('local-debug-config').textContent=JSON.stringify({mode:runtimeScope?'LIVE DEBUG':'MOCK',task_id:task,authorized:true,task_scope:runtimeScope?'runtime':'allowlist'});
  if(legacy)nodes.delete('local-debug-config');
  let selection=selected(),handler=async id=>({task_id:id,authorized:[task,other].includes(id)});
  const messages=[],requests=[],events={},documentEvents={},time=clock();
  const child={postMessage:(data,to)=>messages.push({data,to})};nodes.get('debug-inspector-frame').contentWindow=child;
  const window={location:{origin},ImageGeneration:{getDebugSelection:()=>selection},addEventListener:(n,f)=>events[n]=f};
  const document={body:new Element(),hidden:false,getElementById:id=>nodes.get(id),addEventListener:(n,f)=>documentEvents[n]=f};
  vm.runInNewContext(source('debug_sidebar.js'),{window,document,JSON,AbortController,encodeURIComponent,Date:time.Date,setTimeout:time.setTimeout,clearTimeout:time.clearTimeout,
    async fetch(url,options){requests.push({url,options});const body=await handler(new URL(url,origin).searchParams.get('task_id'));return {ok:true,json:async()=>body};}});
  function open(){nodes.get('toggle-inspector').onclick();nodes.get('debug-inspector-frame').onload();}
  function ack(value=selection,ok=true,options={}){events.message({origin,source:child,data:{type:'inspector:result',selection:value,ok},...options});}
  return {nodes,events,documentEvents,document,time,messages,requests,child,open,ack,set selection(v){selection=v;},set accessHandler(v){handler=v;}};
}
function view(selection,failed=false,quick=false){
  return {selection,images:[{id:selection.image_id}],revisions:[selection.revision],runs:[selection.run_id],
    nodes:[{id:'inputs',label:'原始资料',status:'OBSERVED',note:'来源陈述',documents:[]},
      {id:'planning',label:'Planning',status:quick?'NOT_APPLICABLE':'MISSING',applicable:!quick,note:quick?'无独立 Planning':'证据缺失',documents:[]},
      {id:'generation',label:'Generation',status:'OBSERVED',execution_status:failed?'FAILED':'SUCCEEDED',note:'技术状态不是业务验收',
        documents:[{key:'run.json',file:'run.json',status:'OBSERVED',sha256:'anonymous',data:{run_id:selection.run_id,image_id:selection.image_id,status:failed?'FAILED':'SUCCEEDED'}},
          {key:'response.json',file:'response.json',status:'MISSING',note:'原始文件缺失'}]}],edges:[],assets:[],limitations:['模型内部行为未知']};
}
function childHarness(embedded=true,{legacyTemplate=false}={}){
  const template=fs.readFileSync(path.join(__dirname,'../src/templates/inspector.html'),'utf8');
  const nodes=new Map([...template.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  if(legacyTemplate)for(const id of [...nodes.keys()])if(id.startsWith('flow-'))nodes.delete(id);
  const calls=[],messages=[],events={},time=clock();let handler=async()=>({tasks:[{id:task,title:'匿名'}]});
  const parent={postMessage:(data,to)=>messages.push({data,to})};
  const window={parent,location:{origin},addEventListener:(n,f)=>events[n]=f};
  const document={body:new Element(),getElementById:id=>nodes.get(id),createElement:()=>new Element(),createElementNS:()=>new Element()};document.body.dataset.embedded=String(embedded);
  vm.runInNewContext(source('inspector.js'),{window,document,URLSearchParams,AbortController,JSON,Number,encodeURIComponent,
    setTimeout:time.setTimeout,clearTimeout:time.clearTimeout,
    async fetch(url,options){calls.push({url,options});const value=await handler(url,options);return {ok:value.ok!==false,json:async()=>value.body||value};}});
  function select(selection,options={}){events.message({origin,source:parent,data:{type:'inspector:selection',selection},...options});}
  return {nodes,calls,messages,events,parent,time,select,set handler(fn){handler=fn;}};
}
test('closed sidebar does nothing; open follows exact identity and serializes five-second GET refreshes',()=>{
  const h=parentHarness();assert.equal(h.messages.length,0);assert.equal(h.time.timers.size,0);
  h.open();assert.equal(h.nodes.get('debug-inspector-frame').src,'/inspector?embedded=1');
  assert.deepEqual(JSON.parse(JSON.stringify(h.messages[0].data.selection)),selected());
  h.time.advance(10000);assert.equal(h.messages.length,1); // No overlapping refresh while child is reading.
  h.ack();h.time.advance(500);assert.equal(h.messages.length,2);h.ack();
  h.time.advance(4500);assert.equal(h.messages.length,2);h.time.advance(500);assert.equal(h.messages.length,3);
});
test('legacy server without trusted configuration is marked unverified and never reads Evidence',()=>{
  const h=parentHarness({legacy:true});
  assert.equal(h.nodes.get('toggle-inspector').disabled,true);
  assert.match(h.nodes.get('toggle-inspector').textContent,/环境未核验/);
  assert.equal(h.messages.length,0);assert.equal(h.requests.length,0);assert.equal(h.time.timers.size,0);
});
test('Task/Image/revision/Run changes require server authorization and stale acknowledgments are ignored',async()=>{
  const h=parentHarness();h.open();const first=selected();
  const next=selected('product_002',4,'20261022T020000Z-'+'e'.repeat(32),other);h.selection=next;h.time.advance(500);
  assert.equal(h.nodes.get('debug-inspector-frame').src,'about:blank');
  assert.equal(h.messages.length,1);await tick();h.nodes.get('debug-inspector-frame').onload();
  assert.deepEqual(JSON.parse(JSON.stringify(h.messages.at(-1).data.selection)),next);
  h.ack(first);assert.match(h.nodes.get('debug-sidebar-message').textContent,/正在读取/);
  h.ack(next);assert.match(h.nodes.get('debug-sidebar-message').textContent,/已读取/);
  assert.equal(h.messages.every(m=>m.to===origin&&m.data.type==='inspector:selection'),true);
});
test('unauthorized new Task clears old Evidence immediately and never sends it to the child',async()=>{
  const h=parentHarness();h.open();h.ack();const count=h.messages.length;
  h.selection=selected('product_001',1,null,'c'.repeat(32));h.events['workspace:task-changed']();
  assert.equal(h.nodes.get('debug-inspector-frame').src,'about:blank');
  assert.equal(h.nodes.get('toggle-inspector').disabled,true);
  await tick();h.time.advance(20000);
  assert.equal(h.messages.length,count);assert.match(h.nodes.get('inspector-authorization').textContent,/未获调试授权/);
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].options.method,'GET');assert.equal(h.requests[0].options.body,undefined);
});
test('late authorization for another Task cannot unlock or load its Evidence',async()=>{
  const h=parentHarness();h.open();let complete;
  h.accessHandler=()=>new Promise(resolve=>complete=resolve);
  h.selection=selected('product_001',1,null,other);h.events['workspace:task-changed']();const finish=complete;
  h.accessHandler=async id=>({task_id:id,authorized:false});
  h.selection=selected('product_001',1,null,'c'.repeat(32));h.events['workspace:task-changed']();await tick();
  finish({task_id:other,authorized:true});await tick();
  assert.equal(h.requests[0].options.signal.aborted,true);assert.equal(h.nodes.get('toggle-inspector').disabled,true);
  assert.equal(h.nodes.get('debug-inspector-frame').src,'about:blank');assert.equal(h.messages.length,1);
});
test('authorization failure fails closed while closed sidebar performs no Evidence polling',async()=>{
  const h=parentHarness();h.accessHandler=async()=>{throw new Error('offline');};
  h.selection=selected('product_001',1,null,other);h.events['workspace:task-changed']();await tick();
  assert.match(h.nodes.get('inspector-authorization').textContent,/无法确认/);
  assert.equal(h.messages.length,0);assert.equal(h.nodes.get('toggle-inspector').disabled,true);
  assert.equal(h.time.timers.size,0);h.time.advance(30000);assert.equal(h.requests.length,1);
});
test('local runtime scope follows multiple newly saved Tasks without restart or a grant request',async()=>{
  const h=parentHarness({runtimeScope:true});h.open();h.ack();
  assert.match(h.nodes.get('inspector-authorization').textContent,/无需逐项授权/);
  h.accessHandler=async id=>({task_id:id,authorized:true,task_scope:'runtime'});
  for(const identity of ['c'.repeat(32),'d'.repeat(32)]){
    h.selection=selected('product_001',1,null,identity);
    h.events['workspace:task-changed']();
    assert.equal(h.nodes.get('debug-inspector-frame').src,'about:blank');
    await tick();
    assert.equal(h.nodes.get('toggle-inspector').disabled,false);
    assert.equal(h.nodes.get('debug-inspector-frame').src,'/inspector?embedded=1');
    h.nodes.get('debug-inspector-frame').onload();
    assert.equal(h.messages.at(-1).data.selection.task_id,identity);h.ack();
  }
  assert.equal(h.requests.length,2);
  assert.ok(h.requests.every(request=>request.options.method==='GET'&&!request.options.body));
  assert.doesNotMatch(h.nodes.get('inspector-authorization').textContent,/未获调试授权/);
});
test('close cancels polling and unloads iframe, and reopening rereads current selection',()=>{
  const h=parentHarness();h.open();h.ack();h.nodes.get('close-inspector').onclick();
  assert.equal(h.nodes.get('debug-sidebar').hidden,true);assert.equal(h.time.timers.size,0);
  assert.equal(h.nodes.get('debug-inspector-frame').src,'about:blank');const count=h.messages.length;h.time.advance(20000);assert.equal(h.messages.length,count);
  h.selection=selected('reference_002');h.open();assert.equal(h.messages.length,count+1);
  h.events.keydown({key:'Escape'});assert.equal(h.nodes.get('toggle-inspector').focused,true);assert.equal(h.time.timers.size,0);
});
test('foreign messages cannot complete refresh; hidden pages pause; pagehide stops everything',()=>{
  const h=parentHarness();h.open();h.ack(selected(),true,{origin:'https://evil.invalid'});h.ack(selected(),true,{source:{}});
  assert.match(h.nodes.get('debug-sidebar-message').textContent,/正在读取/);
  h.ack();h.document.hidden=true;h.time.advance(10000);assert.equal(h.messages.length,1);
  h.document.hidden=false;h.documentEvents.visibilitychange();assert.equal(h.messages.length,2);
  h.events.pagehide();assert.equal(h.time.timers.size,0);
});
test('wide Context view preserves the same iframe and accepts only current same-origin child requests',()=>{
  const h=parentHarness();h.open();const url=h.nodes.get('debug-inspector-frame').src;
  const expand=(options={})=>h.events.message({origin,source:h.child,data:{type:'inspector:expand',selection:selected()},...options});
  expand({origin:'https://evil.invalid'});expand({source:{}});
  expand({data:{type:'inspector:expand',selection:selected('reference_002')}});
  assert.equal(h.document.body.classList.contains('debug-sidebar-wide'),false);
  expand();assert.equal(h.document.body.classList.contains('debug-sidebar-wide'),true);
  assert.equal(h.nodes.get('debug-inspector-frame').src,url);assert.equal(h.requests.length,0);
  h.nodes.get('expand-inspector').onclick();assert.equal(h.document.body.classList.contains('debug-sidebar-wide'),false);
  h.nodes.get('expand-inspector').onclick();h.nodes.get('close-inspector').onclick();
  assert.equal(h.document.body.classList.contains('debug-sidebar-wide'),false);
});

function contextView(s=selected('product_001')){
  const result=view(s,false,true);
  const source={node_id:'generation',document_key:'request.json',file:'request.json',pointer:'/prompt',sha256:'saved-hash',status:'OBSERVED'};
  const prompt='Saved full Prompt\n<operator_design_requirements>匿名要求</operator_design_requirements>\n<script>never execute</script>';
  result.nodes[2].documents.push({key:'request.json',file:'request.json',status:'OBSERVED',sha256:'saved-hash',data:{prompt}});
  result.assets=[{key:'run-input-0',status:'OBSERVED',label:'商品原图',sha256:'original-hash'},
    {key:'run-input-1',status:'OBSERVED',label:'设计参考',sha256:'reference-hash'},
    {key:'output',status:'OBSERVED',label:'生成图',sha256:'output-hash'}];
  const inputs=[{id:'product_001',position:1,slot:1,role:'original',asset_key:'run-input-0',sources:[source]},
    {id:'reference_001',position:2,slot:2,role:'design_reference',asset_key:'run-input-1',sources:[source]}];
  result.context_view={supported:true,note:'保存快照不等于全部发送',warnings:[],prompt:{status:'OBSERVED',value:prompt,sources:[source]},
    prompt_file:{status:'MISSING',value:null,sources:[]},comparison:{before:'run-input-0',after:'output'},
    cards:['product','references','requirements','assembly','request','output'].map(id=>({id,title:id,status:'OBSERVED',summary:'已保存摘要',note:'',
      fields:[{label:'本次整体设计要求',value:id==='requirements'?'匿名用户要求':'来源字段',status:'OBSERVED',sources:[source]}],checks:[],
      images:id==='product'?[inputs[0]]:id==='references'?[inputs[1]]:id==='request'?inputs:[]}))};
  return result;
}
const descend=(root,predicate)=>{if(predicate(root))return root;for(const child of root.children){const found=descend(child,predicate);if(found)return found;}};
test('legacy V0.6 projection remains readable if graph data is unavailable, raw JSON collapsed',async()=>{
  const h=childHarness(),selection=selected('product_001');h.handler=async()=>contextView(selection);h.select(selection);await tick();
  assert.equal(h.nodes.get('context-cards').children.length,6);assert.equal(h.nodes.get('advanced-evidence').open,false);
  assert.match(h.nodes.get('context-cards').textContent,/匿名用户要求/);
  const image=descend(h.nodes.get('context-cards').children[1],e=>e.src);
  assert.ok(image.src.startsWith('/api/inspector/tasks/'+task+'/assets/run-input-1?'));
  assert.ok(image.src.includes('run_id='+run));assert.equal(h.calls.length,1);
});
test('V0.6 full Prompt and comparison are read-only, sourced, and request parent expansion',async()=>{
  const h=childHarness(),selection=selected('product_001'),data=contextView(selection);
  h.handler=async()=>data;h.select(selection);await tick();
  descend(h.nodes.get('context-cards'),e=>e.textContent==='查看完整 Prompt').onclick();
  assert.equal(h.nodes.get('context-dialog').open,true);
  assert.match(h.nodes.get('context-dialog-body').textContent,/<script>never execute<\/script>/);
  assert.equal(h.messages.at(-1).data.type,'inspector:expand');
  assert.deepEqual(JSON.parse(JSON.stringify(h.messages.at(-1).data.selection)),selection);
  descend(h.nodes.get('context-dialog-body'),e=>e.className==='source-ref').onclick();
  assert.equal(h.nodes.get('context-dialog').open,false);assert.equal(h.nodes.get('advanced-evidence').open,true);
  assert.match(h.nodes.get('file-meta').textContent,/request.json/);
  descend(h.nodes.get('context-cards'),e=>e.textContent==='原图 / 成图对照').onclick();
  const pair=descend(h.nodes.get('context-dialog-body'),e=>e.className==='comparison-pair');
  assert.equal(pair.children.length,2);assert.ok(descend(pair.children[0],e=>e.src).src.includes('/assets/run-input-0?'));
  assert.ok(descend(pair.children[1],e=>e.src).src.includes('/assets/output?'));
  assert.equal(h.calls.length,1);h.select(null);assert.equal(h.nodes.get('context-dialog').open,false);
});
test('embedded inspector waits for authenticated parent selection and only sends scoped GET',async()=>{
  const h=childHarness();assert.equal(h.calls.length,0);
  h.handler=async()=>view(selected());
  h.select(selected(),{source:{}});h.select(selected(),{origin:'https://evil.invalid'});h.select({...selected(),task_id:'../.env'});assert.equal(h.calls.length,0);
  h.select(selected());await tick();assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,'/api/inspector/tasks/'+task+'?image_id=reference_001&revision=3&run_id='+run);
  assert.equal(h.calls[0].options.method,'GET');assert.equal(h.calls[0].options.body,undefined);
  assert.match(h.nodes.get('identity').textContent,/reference_001/);assert.equal(h.messages.at(-1).data.ok,true);
});
test('late response for another picture is discarded and the old request is aborted',async()=>{
  const h=childHarness(),a=selected(),b=selected('reference_002');let resolve;
  h.handler=()=>new Promise(r=>resolve=r);h.select(a);const finish=resolve;
  h.handler=async()=>view(b,true);h.select(b);await tick();assert.equal(h.calls[0].options.signal.aborted,true);
  finish(view(a));await tick();assert.match(h.nodes.get('identity').textContent,/reference_002/);assert.doesNotMatch(h.nodes.get('identity').textContent,/reference_001/);
  assert.match(h.nodes.get('document').textContent,/FAILED/);assert.equal(h.messages.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(h.messages[0].data.selection)),b);
});
test('unchanged polls preserve open image and node/file selection; clearing removes old evidence',async()=>{
  const h=childHarness();h.handler=async()=>view(selected());h.select(selected());await tick();
  h.nodes.get('file-list').children[1].onclick();h.nodes.get('image-dialog').showModal();
  h.select(selected());await tick();assert.equal(h.nodes.get('image-dialog').open,true);assert.match(h.nodes.get('document').textContent,/原始文件缺失/);
  h.select(null);assert.equal(h.nodes.get('evidence').hidden,true);assert.equal(h.nodes.get('image-dialog').open,false);
  assert.equal(h.calls.length,2);
});
test('Quick marks Planning inapplicable; errors and missing files remain observable without commands',async()=>{
  const h=childHarness(),s=selected('product_001');h.handler=async()=>view(s,false,true);h.select(s);await tick();
  h.nodes.get('graph').children[1].onclick();assert.match(h.nodes.get('node-title').textContent,/不适用/);
  assert.equal(h.nodes.get('file-list').children.length,0);
  h.handler=async()=>({ok:false,body:{error:'证据文件缺失'}});h.select(s);await tick();
  assert.equal(h.nodes.get('evidence').hidden,true);assert.match(h.nodes.get('message').textContent,/缺失/);assert.equal(h.messages.at(-1).data.ok,false);
  assert.equal(h.calls.every(c=>c.options.method==='GET'),true);
});
test('standalone V0 still loads task list and exposes its original selectors',async()=>{
  const h=childHarness(false);h.handler=async()=>view(selected());await tick();
  assert.equal(h.calls[0].url,'/api/inspector/tasks');assert.equal(h.calls[1].url,'/api/inspector/tasks/'+task+'?');
  assert.equal(h.nodes.get('task-select').children[0].value,task);assert.equal(h.messages.length,0);
});

function graphView(selection=selected('product_001')){
  const result=contextView(selection),id=key=>JSON.stringify(selection)+':'+key;
  const keys=['N01','N02','N03','N04','N05','N06','N07','N08','N09','N10','N11','N12','N13','N14','P01','P02','P03'];
  const names={N01:'商品原图',N02:'参考图片',N03:'运营要求',N08:'最终 Prompt',N09:'Images Request',N11:'生成图片',P01:'Context Assembly'};
  const source={node_id:'generation',document_key:'request.json',file:'request.json',pointer:'/prompt',exists:true,text_span:{start:0,end:17},line_range:[1,1]};
  const nodes=keys.map(key=>({id:id(key),key,kind:key.startsWith('P')?'ACTIVITY':'ARTIFACT',label:names[key]||key,evidence_status:key==='P01'?'INFERRED':'OBSERVED',execution_status:'UNKNOWN',summary:'保存证据，不代表模型质量通过',uncertainty_reason:'远端未知',
    fields:result.context_view.cards[2].fields,images:key==='N01'?[result.context_view.cards[0].images[0]]:key==='N02'?[result.context_view.cards[1].images[0]]:[],evidence_refs:[source],consistency_checks:[],default_visible:!['N05','N12','N13','N14','P03'].includes(key)}));
  const pairs=[['N01','N07'],['N02','N07'],['N03','N06'],['N04','N06'],['N05','N06'],['N03','P01'],['N04','P01'],['N07','P01'],['P01','N06'],['P01','N08'],['N03','N08'],['N04','N08'],['N08','N09'],['N07','N09'],['N09','P02'],['P02','N10'],['P02','N11'],['N11','P03'],['P03','N12'],['N13','P01'],['N14','N07']];
  result.graph_view={supported:true,nodes,edges:pairs.map(([from,to],i)=>({id:id('E'+(i+1)),key:'E'+String(i+1).padStart(2,'0'),source:id(from),target:id(to),relation_type:'INCLUDED_IN',claim:'实际传递关系',evidence_status:'INFERRED',evidence_refs:[source],consistency_checks:[],uncertainty_reason:'无远端确认'})),warnings:[],
    stages:[['输入依据',['N01','N02']],['Context',['P01','N06']],['模型请求',['N09']],['执行',['P02']],['输出',['N11','N12']]].map(([label,members])=>({label,node_ids:members.map(id)}))};
  return result;
}
test('V0.7 defaults to five compact stages, with no cards, UUID or raw document in summary',async()=>{
  const h=childHarness(),selection=selected('product_001'),data=graphView(selection);
  data.graph_view.nodes.find(n=>n.key==='P01').consistency_checks=[{label:'Prompt hash',result:'MISMATCH'}];
  h.handler=async()=>data;h.select(selection);await tick();
  assert.equal(h.nodes.get('flow-summary').children.length,5);assert.equal(h.nodes.get('context-cards').children.length,0);
  assert.equal(h.nodes.get('flow-workbench').hidden,true);assert.equal(h.nodes.get('advanced-evidence').open,false);
  assert.doesNotMatch(h.nodes.get('flow-summary').textContent,new RegExp(task));
  assert.match(h.nodes.get('flow-summary').textContent,/MISMATCH · 证据不一致/);
  assert.equal(h.nodes.get('flow-detail').children.some(e=>e.className==='graph-raw'),false);
});
test('graph nodes and edges are clickable and keyboard selectable with progressive relationships',async()=>{
  const h=childHarness(),selection=selected('product_001');h.handler=async()=>graphView(selection);h.select(selection);await tick();
  h.nodes.get('expand-context').onclick();assert.equal(h.nodes.get('flow-workbench').hidden,false);
  const group=()=>h.nodes.get('flow-canvas').children[1],nodes=()=>group().children.filter(e=>e.attributes['data-node']);
  assert.equal(nodes().length,12);nodes().find(e=>e.attributes['data-node']==='N01').onclick();
  assert.ok(descend(h.nodes.get('flow-detail'),e=>e.src).src.includes('/assets/run-input-0?'));
  nodes().find(e=>e.attributes['data-node']==='N03').onclick();
  assert.match(nodes().find(e=>e.attributes['data-node']==='N02').attributes.class,/dimmed/); // A co-input is not upstream of N03.
  assert.doesNotMatch(nodes().find(e=>e.attributes['data-node']==='N08').attributes.class,/dimmed/);
  const edge=group().children.find(e=>e.attributes['data-edge']==='E13');let prevented=false;
  edge.onkeydown({key:'Enter',preventDefault(){prevented=true;}});assert.equal(prevented,true);
  assert.match(h.nodes.get('flow-detail').textContent,/实际传递关系/);assert.match(h.nodes.get('flow-detail').textContent,/最终 Prompt → Images Request/);
  h.nodes.get('flow-more').onclick();assert.equal(nodes().length,17);assert.equal(group().children.filter(e=>e.attributes['data-edge']).length,21);
  h.nodes.get('flow-more').onclick();h.nodes.get('flow-relation-list').children[18].onclick();
  assert.equal(nodes().length,14);assert.match(h.nodes.get('flow-detail').textContent,/实际传递关系/);
});
test('detail levels expose saved text, Prompt highlighting, order and opt-in provenance',async()=>{
  const h=childHarness(),selection=selected('product_001');h.handler=async()=>graphView(selection);h.select(selection);await tick();
  h.nodes.get('flow-relation-list').children[10].onclick();assert.match(h.nodes.get('flow-detail').textContent,/保存 Prompt 中的对应原文/);
  descend(h.nodes.get('flow-detail'),e=>e.textContent==='定位 Prompt 全文').onclick();
  assert.equal(h.nodes.get('context-dialog').open,true);assert.ok(descend(h.nodes.get('context-dialog-body'),e=>e.textContent==='Saved full Prompt'));
  descend(h.nodes.get('flow-detail'),e=>e.textContent==='3 · 来源证据').onclick();
  assert.match(descend(h.nodes.get('flow-detail'),e=>e.className==='graph-raw').textContent,/text_span/);
  assert.equal(h.nodes.get('advanced-evidence').open,false);assert.equal(h.calls.length,1);
});
test('graph zoom, fit, pan and keyboard transform only the canvas, without network requests',async()=>{
  const h=childHarness(),selection=selected('product_001');h.handler=async()=>graphView(selection);h.select(selection);await tick();
  h.nodes.get('expand-context').onclick();h.nodes.get('flow-fit').onclick();const canvas=h.nodes.get('flow-canvas'),group=canvas.children[1];
  const original=group.attributes.transform;h.nodes.get('flow-zoom-in').onclick();assert.notEqual(group.attributes.transform,original);
  h.nodes.get('flow-fit').onclick();assert.equal(group.attributes.transform,original);
  canvas.onpointerdown({target:canvas,clientX:5,clientY:10,pointerId:1});canvas.onpointermove({clientX:35,clientY:60});canvas.onpointerup();assert.notEqual(group.attributes.transform,original);
  canvas.onkeydown({key:'0',preventDefault(){}});assert.equal(group.attributes.transform,original);
  canvas.onkeydown({key:'ArrowLeft',preventDefault(){}});assert.notEqual(group.attributes.transform,original);assert.equal(h.calls.length,1);
});
test('Run/Image/Task changes clear graph selection, details, dialogs and expanded extra relationships',async()=>{
  const h=childHarness(),a=selected('product_001'),b=selected('product_002',4,'20261023T010000Z-'+'f'.repeat(32),other);
  h.handler=async()=>graphView(a);h.select(a);await tick();h.nodes.get('flow-more').onclick();h.nodes.get('flow-relation-list').children[10].onclick();
  h.handler=async()=>graphView(b);h.select(b);await tick();
  assert.equal(h.nodes.get('flow-canvas').children[1].children.filter(e=>e.attributes['data-node']).length,12);
  assert.match(h.nodes.get('identity').textContent,new RegExp(other));assert.doesNotMatch(h.nodes.get('flow-detail').textContent,new RegExp(task));
  assert.match(h.nodes.get('flow-detail').textContent,/Context Assembly/);assert.equal(h.nodes.get('context-dialog').open,false);
});
test('graph output opens scoped side-by-side comparison and parent collapse retains same graph identity',async()=>{
  const h=childHarness(),selection=selected('product_001');h.handler=async()=>graphView(selection);h.select(selection);await tick();
  h.nodes.get('expand-context').onclick();h.nodes.get('flow-canvas').children[1].children.find(e=>e.attributes['data-node']==='N11').onclick();
  descend(h.nodes.get('flow-detail'),e=>e.textContent==='原图 / 成图对照').onclick();const pair=descend(h.nodes.get('context-dialog-body'),e=>e.className==='comparison-pair');
  assert.equal(pair.children.length,2);assert.ok(descend(pair.children[1],e=>e.src).src.includes('/assets/output?'));
  h.events.message({origin,source:h.parent,data:{type:'inspector:layout',selection,expanded:false}});assert.equal(h.nodes.get('flow-workbench').hidden,true);
  assert.equal(h.calls.length,1);assert.ok(h.calls.every(call=>call.options.method==='GET'));
});
test('a cached V0.6 template remains functional with the new static script, without restarting other services',async()=>{
  const h=childHarness(true,{legacyTemplate:true}),selection=selected('product_001');
  h.handler=async()=>graphView(selection);h.select(selection);await tick();
  assert.equal(h.nodes.get('context-cards').children.length,6);assert.equal(h.nodes.get('evidence').hidden,false);
  descend(h.nodes.get('context-cards'),e=>e.textContent==='查看完整 Prompt').onclick();
  assert.equal(h.nodes.get('context-dialog').open,true);assert.equal(h.calls.length,1);
});
