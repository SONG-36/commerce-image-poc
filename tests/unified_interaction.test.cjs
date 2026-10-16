const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {File}=require('node:buffer'),{webcrypto}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../src/static/generate.js'),'utf8');
const template=fs.readFileSync(path.join(__dirname,'../src/templates/workspace.html'),'utf8');
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this._text='';this._value='';this.files=[];this.hidden=false;this.disabled=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(e=>e.textContent).join(' ');}
  set value(value){this._value=value;if(this.type==='file'&&value==='')this.files=[];}
  get value(){return this._value;}
  append(...nodes){this.children.push(...nodes);for(const n of nodes)n.parent=this;}
  replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
  setAttribute(name,value){this.attributes[name]=value;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);}
  click(){if(!this.disabled)return this.onclick?.();}
  showModal(){this.open=true;} close(){this.open=false;}
}
const walk=(element,predicate)=>{if(predicate(element))return element;for(const child of element.children){const found=walk(child,predicate);if(found)return found;}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(quick=false,task='a'.repeat(32)){
  const ids=[1,2,3].map(n=>(quick?'product':'reference')+'_'+String(n).padStart(3,'0'));
  const state={id:task,revision:4,mode:quick?'quick_redesign':'product_pack',product:quick?null:{identity:'offline'},product_version:1,
    plans:{},references:{},reference_versions:{},plan_status:{},events:[],stale_plans:[]};
  const cards=ids.map((id,index)=>{
    state.plans[id]={goal:'仅 '+id+' 的计划',design:'保留商品'};state.references[id]={style:'参考设计'};state.reference_versions[id]=1;state.plan_status[id]={plan_version:1,confirmed:true};
    const run='run_'+id,version={run_id:run,version:1,created_at:'2026-10-16T01:00:00Z',action:'generate_image',url:'/images/'+run,feedback:'',parent_run_id:null};
    return {id,plan:quick?null:state.plans[id],generation_revision:4,confirmed_revision:4,card_revision:2,reference:{url:'/inputs/'+id,name:id+'.png'},
      status:'SUCCEEDED',versions:[version],selected_run:run,passed_run:index===0?run:null,image_url:version.url,has_generated_history:true,has_passed_history:index===0,
      generation_allowed:true,historical_generation:false,request_uncertain:false,batch_eligible:false,plan_status:quick?null:state.plan_status[id],
      requirements:'只改善视觉表达',product_facts:'不得编造参数',style_references:[],output_size:'1024x1536'};
  });
  return {state,data:{session_id:task,title:'offline',mode:state.mode,cards,auxiliary_purposes:{product_appearance:'商品外观修正',design_style:'设计风格参考',local_content:'局部内容参考'},auxiliary_max_bytes:20*1024*1024}};
}
function harness(initial=fixture(),storage=new Map()){
  const nodes=new Map([...template.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  nodes.get('edit-file').type='file';
  const calls=[],actions=[],events={},downloads=[];
  let current=initial,handler=async()=>response({status:'SUCCEEDED'}),planHandler=async()=>{},refreshes=0;
  const document={body:new Element('body'),getElementById(id){assert.ok(nodes.has(id),'Missing DOM '+id);return nodes.get(id);},createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
  document.body.dataset.sessionId=initial.state.id;
  const window={addEventListener(name,fn){events[name]=fn;},confirm:()=>true,
    PreparePlan:{getState:()=>current.state,getStatus:()=>({busy:false,dirty:false}),setImageBusy(){},
      renderCardPlan(card,editable){assert.equal(editable,false);const details=new Element('details');details.append(Object.assign(new Element('summary'),{textContent:card.plan?.goal||'计划'}));return details;},
      async modifyTarget(action,target,feedback,expected){actions.push({action,target,feedback,expected});await planHandler(action,target,feedback,expected);},
      async confirmPlan(target){actions.push({action:'confirm',target});current.state.plan_status[target].confirmed=true;current.data.cards.find(c=>c.id===target).plan_status.confirmed=true;present();}}};
  const context={window,document,console,Date,JSON,Map,Set,Object,Math,Boolean,String,Error,FormData,crypto:webcrypto,
    sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    URL:{createObjectURL:()=> 'blob:offline-'+webcrypto.randomUUID(),revokeObjectURL(){}},
    setInterval(){},setTimeout(){},clearTimeout(){},
    async fetch(url,options={}){calls.push({url,options});if(url.includes('/export-'))downloads.push(url);return handler(url,options);}};
  context.globalThis=context;
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/static/batch_generate.js'),'utf8'),context);
  window.ImageBatchRunner=context.ImageBatchRunner;
  window.Workspace={async refresh(){refreshes++;present();}};
  vm.runInContext(source,context);
  function present(value){if(value)current=value;window.ImageGeneration.present(current.data,{blocked:false});}
  function node(id){return nodes.get(id);}
  function choose(index){const id=current.data.cards[index-1].id;node('generation-cards').children.find(e=>e.dataset.cardId===id).click();}
  function type(text){node('edit-feedback').value=text;node('edit-feedback').oninput();}
  function action(value){node('edit-action').value=value;node('edit-action').onchange();}
  function file(name='accurate.png',type='image/png',value='actual helper bytes'){
    const file=new File([value],name,{type});node('edit-file').files=[file];node('edit-file').onchange();return file;
  }
  function purpose(value='product_appearance'){node('edit-purpose').value=value;node('edit-purpose').onchange();}
  function detail(text){return walk(node('selected-image-detail'),e=>e.tag==='button'&&e.textContent===text);}
  function versionSelect(){return walk(node('selected-image-detail'),e=>e.attributes['aria-label']==='当前图片的历史版本');}
  present();
  return {node,choose,type,action,file,purpose,present,detail,versionSelect,calls,actions,events,storage,window,
    get current(){return current;},get refreshes(){return refreshes;},set handler(fn){handler=fn;},set planHandler(fn){planHandler=fn;}};
}
function response(data,ok=true){return {ok,async json(){return data;},async blob(){return new Blob(['offline zip']);},headers:{get(){return null;}}};}
function addVersion(h,index,feedback=''){
  const card=h.current.data.cards[index],run='new_'+card.id+'_'+card.versions.length;
  card.versions.push({version:card.versions.length+1,run_id:run,created_at:'2026-10-16T02:00:00Z',action:'revise_image',parent_run_id:card.selected_run,feedback,url:'/images/'+run});
  card.selected_run=run;card.image_url='/images/'+run;card.card_revision+=2;return run;
}
test('one OUTPUT composer, explicit selection, identity and read-only big image',()=>{
  const output=template.slice(template.indexOf('<section id="output"'));
  assert.equal((output.match(/<textarea/g)||[]).length,1);assert.equal((output.match(/type="file"/g)||[]).length,1);
  const h=harness();assert.equal(h.node('send-edit').disabled,true);assert.equal(h.calls.length,0);
  h.choose(2);assert.match(h.node('edit-target').textContent,/reference_002.*#02/s);assert.match(h.node('edit-target').textContent,/run_reference_002/);
  assert.equal(h.node('generation-cards').children[1].attributes['aria-pressed'],'true');
  h.detail('查看大图').click();assert.equal(h.node('image-viewer').open,true);assert.equal(h.node('viewer-image').src,'/images/run_reference_002');
  assert.equal(h.calls.length,0);
});
test('A: switching pictures and actions preserves text, file and role without leaking',()=>{
  const h=harness();h.choose(2);h.type('仅修改 #02');h.file();h.purpose();
  h.choose(3);assert.equal(h.node('edit-feedback').value,'');assert.equal(h.node('edit-preview').hidden,true);
  h.type('仅修改 #03');h.choose(2);assert.equal(h.node('edit-feedback').value,'仅修改 #02');assert.equal(h.node('edit-filename').textContent,'accurate.png');assert.equal(h.node('edit-purpose').value,'product_appearance');
  h.action('plan');assert.equal(h.node('edit-feedback').value,'');assert.equal(h.node('edit-auxiliary').hidden,true);
  h.action('image');assert.equal(h.node('edit-feedback').value,'仅修改 #02');assert.equal(h.node('edit-filename').textContent,'accurate.png');
  h.file('bad.gif','image/gif');assert.match(h.node('generation-message').textContent,/JPG/);assert.equal(h.node('edit-filename').textContent,'accurate.png');
  assert.equal(h.calls.length,0);
});
test('B: frozen multipart binds #02; late response stays there and keeps a newer draft',async()=>{
  const h=harness();h.choose(2);h.type('发送时的意见');h.file();h.purpose();
  let finish;h.handler=()=>new Promise(resolve=>finish=resolve);
  const promise=h.node('send-edit').click();await tick();
  assert.match(h.node('generation-cards').children[1].textContent,/正在执行/);
  assert.equal(h.calls.length,1);assert.ok(h.calls[0].url.endsWith('/revise/reference_002'));
  const payload=h.calls[0].options.body;
  assert.equal(payload.get('parent_run_id'),'run_reference_002');assert.equal(payload.get('confirmed_revision'),'4');
  assert.equal(payload.get('feedback'),'发送时的意见');assert.equal(payload.get('auxiliary_purpose'),'product_appearance');
  assert.equal(await payload.get('auxiliary').text(),'actual helper bytes');
  h.type('发送期间新增的意见');h.file('later.png');h.purpose('design_style');
  h.choose(3);h.type('第三张草稿');assert.equal(h.node('send-edit').disabled,true);
  const original=h.current.data.cards[0].image_url,run=addVersion(h,1,'发送时的意见');
  finish(response({run_id:run,status:'SUCCEEDED',confirmed_revision:4}));await promise;
  assert.match(h.node('edit-target').textContent,/reference_003/);assert.equal(h.node('edit-feedback').value,'第三张草稿');
  assert.equal(h.current.data.cards[0].image_url,original);assert.equal(h.current.data.cards[0].passed_run,'run_reference_001');
  h.choose(2);assert.equal(h.node('edit-feedback').value,'发送期间新增的意见');assert.equal(h.node('edit-filename').textContent,'later.png');
  assert.equal(h.node('send-edit').disabled,true);assert.equal(h.node('rebase-draft').hidden,false);
  h.node('rebase-draft').click();assert.equal(h.node('send-edit').disabled,false);
  assert.equal(h.calls.length,1);
});
test('C: explicit plan edit uses planning entry and only the selected confirmation changes',async()=>{
  const h=harness();h.choose(1);h.action('plan');h.type('只修改第一张计划');
  h.planHandler=async(action,target,feedback,op)=>{
    assert.equal(action,'plan');assert.equal(op.taskId,'a'.repeat(32));assert.equal(op.imageId,'reference_001');assert.equal(op.stateRevision,4);assert.equal(op.planVersion,1);
    h.current.state.revision++;h.current.state.plans[target].goal=feedback;h.current.state.plan_status[target]={plan_version:2,confirmed:false};
    h.current.data.cards[0].generation_allowed=false;h.current.data.cards[0].plan_status=h.current.state.plan_status[target];
  };
  await h.node('send-edit').click();assert.equal(h.current.state.plans.reference_002.goal,'仅 reference_002 的计划');
  assert.equal(h.current.data.cards[1].plan_status.confirmed,true);assert.equal(h.calls.length,0);
  await h.detail('确认本图计划').click();assert.equal(h.actions.at(-1).target,'reference_001');
  assert.equal(h.current.data.cards[0].plan_status.confirmed,true);
});
test('history selection and Pass send exact Run IDs while an older accepted image remains',async()=>{
  const h=harness();addVersion(h,1,'真实保存的修改意见');h.present();h.choose(2);
  h.handler=async(url,options)=>{
    const body=JSON.parse(options.body),card=h.current.data.cards[1];assert.equal(body.confirmed_revision,4);
    if(body.action==='select'){assert.equal(body.run_id,'run_reference_002');card.selected_run=body.run_id;card.image_url='/images/'+body.run_id;}
    else{assert.equal(body.run_id,card.selected_run);card.passed_run=body.run_id;card.has_passed_history=true;}
    card.card_revision++;return response({event:{}});
  };
  const select=h.versionSelect();select.value='run_reference_002';select.onchange();await tick();
  await h.detail('Pass · 接受当前版本').click();
  assert.equal(h.current.data.cards[1].passed_run,'run_reference_002');assert.equal(h.calls.length,2);
  assert.match(h.node('interaction-records').textContent,/真实保存的修改意见/);assert.match(h.node('interaction-records').textContent,/当前已 Pass/);
});
test('D: Quick mode shares the same text editor, needs no plan and sends no attachment implicitly',async()=>{
  const h=harness(fixture(true));h.choose(2);assert.deepEqual(h.node('edit-action').children.map(e=>e.value),['image']);
  h.type('保留构图，背景更浅');h.handler=async(url,options)=>{
    assert.ok(url.endsWith('/revise/product_002'));const body=JSON.parse(options.body);
    assert.equal(body.parent_run_id,'run_product_002');assert.equal(body.feedback,'保留构图，背景更浅');assert.equal(body.auxiliary,undefined);
    addVersion(h,1);return response({status:'SUCCEEDED'});
  };
  await h.node('send-edit').click();assert.equal(h.node('edit-feedback').value,'');
  h.current.data.cards[2].selected_run=null;h.current.data.cards[2].image_url=null;h.current.data.cards[2].versions=[];h.present();h.choose(3);h.type('没有图时不能编辑');
  assert.equal(h.node('send-edit').disabled,true);assert.equal(h.calls.length,1);
});
test('batch still executes sequentially once, skips existing/Pass and restores without submitting',async()=>{
  const f=fixture();for(const card of f.data.cards.slice(1)){card.versions=[];card.image_url=null;card.selected_run=null;card.has_generated_history=false;card.batch_eligible=true;card.status='NOT_STARTED';}
  const h=harness(f);let active=0,maxActive=0;
  h.handler=async(url,options)=>{
    if(options.method==='POST'){
      active++;maxActive=Math.max(maxActive,active);await tick();
      const id=url.split('/').at(-1),card=h.current.data.cards.find(c=>c.id===id);
      assert.equal(JSON.parse(options.body).batch_only,true);assert.notEqual(id,'reference_001');
      card.batch_eligible=false;card.has_generated_history=true;card.status='SUCCEEDED';active--;return response({status:'SUCCEEDED'});
    }
    return response({status:'SUCCEEDED',uncertain:false});
  };
  assert.match(h.node('batch-generate').textContent,/2 张/);await h.node('batch-generate').click();
  assert.equal(maxActive,1);assert.equal(h.calls.filter(c=>c.options.method==='POST').length,2);assert.match(h.node('batch-progress').textContent,/已完成 2 \/ 2/);
  const before=h.calls.length;h.present();assert.equal(h.calls.length,before);
  const restored=harness(h.current,h.storage);assert.equal(restored.calls.length,0);assert.match(restored.node('batch-progress').textContent,/已完成 2 \/ 2/);
});
test('failure keeps prior image, disables uncertain retry, and task switching isolates drafts and late results',async()=>{
  const h=harness();h.choose(2);h.type('失败前的草稿');const image=h.current.data.cards[1].image_url;
  h.handler=async()=>{h.current.data.cards[1].status='FAILED';h.current.data.cards[1].request_uncertain=true;throw new Error('offline connection lost');};
  await h.node('send-edit').click();assert.equal(h.current.data.cards[1].image_url,image);assert.equal(h.node('edit-feedback').value,'失败前的草稿');assert.equal(h.node('send-edit').disabled,true);
  assert.match(h.node('image-operation').textContent,/待核对/);
  const first=h.current,other=fixture(false,'b'.repeat(32));h.present(other);h.choose(2);assert.equal(h.node('edit-feedback').value,'');h.type('第二个 Task');
  h.present(first);assert.equal(h.node('edit-feedback').value,'失败前的草稿');assert.equal(h.calls.length,1);
  h.events.pagehide();h.events.pageshow({persisted:true});assert.equal(h.calls.length,1);
});
test('export handlers keep task-bound free endpoints and do not invoke generation',async()=>{
  const h=harness();h.choose(1);h.handler=async()=>response({});
  await h.node('export-experiment').click();await h.node('export-passed').click();
  assert.deepEqual(h.calls.map(c=>c.url),['/api/sessions/'+'a'.repeat(32)+'/export-experiment','/api/sessions/'+'a'.repeat(32)+'/export-passed']);
});
test('a late response from another Task cannot replace its current view or clear its draft',async()=>{
  const first=fixture(),h=harness(first);h.choose(2);h.type('原任务的请求');
  let finish;h.handler=()=>new Promise(resolve=>finish=resolve);
  const promise=h.node('send-edit').click();await tick();
  const second=fixture(false,'b'.repeat(32));h.present(second);h.choose(2);h.type('新任务草稿');
  const image=second.data.cards[1].image_url;
  addVersion({current:first},1);finish(response({status:'SUCCEEDED'}));await promise;
  assert.match(h.node('edit-target').textContent,new RegExp('b'.repeat(32)));
  assert.equal(h.node('edit-feedback').value,'新任务草稿');assert.equal(second.data.cards[1].image_url,image);
  assert.equal(h.refreshes,0);assert.equal(h.calls.length,1);
});
