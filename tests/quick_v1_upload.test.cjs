const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {File}=require('node:buffer');
const template=fs.readFileSync(path.join(__dirname,'../src/templates/workspace.html'),'utf8');
class Element{
  constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.value='';this.files=[];this._text='';this.hidden=false;this.disabled=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(e=>e.textContent).join(' ');}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[];this._text='';this.append(...items);}
  setAttribute(){} addEventListener(name,fn){this['on'+name]=fn;}
}
const walk=(e,id)=>e.id===id?e:e.children.map(c=>walk(c,id)).find(Boolean);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const file=name=>new File(['anonymous '+name],name,{type:'image/png'});
async function harness(state=null){
  const nodes=new Map([...template.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  nodes.get('task-mode').value='product_pack';
  const document={body:{dataset:{sessionId:state?.id||''},classList:{toggle(){}}},
    getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[]};
  let handler=async()=>({ok:true,json:async()=>({state})});const calls=[];
  const window={history:{replaceState(){}},dispatchEvent(){},Workspace:{planningChanged(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/static/prepare.js'),'utf8'),{
    document,window,FormData,Map,Set,Date,JSON,URL:{createObjectURL:f=>'blob:'+f.name,revokeObjectURL(){}},
    setInterval(){},setTimeout(){},clearTimeout(){},CustomEvent:function(){},fetch:async(url,options)=>{calls.push({url,options});return handler(url,options);}});
  await tick();
  const node=id=>nodes.get(id)||walk(nodes.get('quick-slots'),id);
  return {node,calls,window,set handler(fn){handler=fn;},
    mode(value){node('task-mode').value=value;node('task-mode').onchange();},
    products(count){node('product-files').onchange({target:{files:Array.from({length:count},(_,i)=>file('product-'+i+'.png')),value:''}});},
    reference(index){const e=node('quick-slot-'+index+'-file');e.files=[file('reference-'+index+'.png')];e.onchange();},
    async submit(){node('input-form').onsubmit({preventDefault(){}});await tick();},
    reject(){handler=async()=>({ok:false,json:async()=>({error:'离线保存失败'})});},
  };
}
test('new Quick uses eight bounded slots, three enabled outputs independent of four products',async()=>{
  const h=await harness();h.mode('quick_redesign');h.products(4);[0,1,6].forEach(i=>h.reference(i));
  assert.equal(h.node('quick-slots').children.length,8);assert.equal(h.node('shared-reference-field').hidden,true);
  h.node('quick-slot-1-requirements').value='只采用自家尺寸';h.node('quick-slot-1-requirements').oninput();
  h.reject();await h.submit();const data=h.calls.at(-1).options.body;
  assert.equal(data.get('quick_business_version'),'v1');assert.equal(data.getAll('product').length,4);assert.equal(data.getAll('reference').length,3);
  const slots=JSON.parse(data.get('quick_slots')),active=slots.filter(s=>s.enabled);
  assert.deepEqual(active.map(s=>s.type),['main','dimensions','scene']);
  assert.deepEqual(active.map(s=>s.reference_id),['reference_001','reference_002','reference_003']);
  assert.equal(active[1].requirements,'只采用自家尺寸');assert.equal(active[0].requirements,'');assert.equal(new Set(slots.map(s=>s.id)).size,8);
  // A server failure preserves the real local files and entered requirements.
  assert.match(h.node('message').textContent,/离线保存失败/);assert.match(h.node('quick-slots').textContent,/reference-6.png/);
  assert.equal(h.node('quick-slot-1-requirements').value,'只采用自家尺寸');await h.submit();assert.equal(h.calls.at(-1).options.body.getAll('product').length,4);
});
test('remove/replace/disable reference changes only that slot and rejects an enabled empty slot',async()=>{
  const h=await harness();h.mode('quick_redesign');h.reference(0);h.reference(1);
  h.node('quick-slot-0-remove').onclick();assert.equal(h.node('quick-slot-0-enabled').checked,false);assert.match(h.node('quick-slots').textContent,/reference-1.png/);
  h.reference(1);h.node('quick-slot-0-enabled').checked=true;h.node('quick-slot-0-enabled').onchange();await h.submit();
  assert.equal(h.calls.length,0);assert.match(h.node('message').textContent,/必须绑定/);
  h.node('quick-slot-0-enabled').checked=false;h.node('quick-slot-0-enabled').onchange();h.reject();await h.submit();
  assert.equal(h.calls.at(-1).options.body.getAll('reference').length,1);
});
test('saved V1 restores slot identity and remaps kept reference ids when saving a separate task',async()=>{
  const state={id:'a'.repeat(32),title:'匿名',mode:'quick_redesign',quick_business_version:'v1',revision:1,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_001',role:'reference',name:'unused.png',file:'inputs/reference_001.png',url:'/unused'},
    {id:'reference_002',role:'reference',name:'bound.png',file:'inputs/reference_002.png',url:'/bound'}],
    quick_slots:[{id:'reference_908',type:'scene',enabled:true,reference_id:'reference_002',requirements:'原要求'}],plans:{},plan_status:{},stale_plans:[]};
  const h=await harness(state);assert.equal(h.node('quick-slot-6-requirements').value,'原要求');assert.match(h.node('quick-slots').textContent,/bound.png/);
  h.reject();await h.submit();const body=h.calls.at(-1).options.body,active=JSON.parse(body.get('quick_slots')).filter(s=>s.enabled);
  assert.equal(body.get('from_session'),state.id);assert.deepEqual(JSON.parse(body.get('keep_images')),['product_001','reference_002']);
  assert.equal(active[0].id,'reference_908');assert.equal(active[0].reference_id,'reference_001');assert.equal(body.getAll('reference').length,0);
  assert.equal(state.quick_slots[0].reference_id,'reference_002');
});
test('legacy Quick and product pack retain shared references and do not opt into V1',async()=>{
  for(const mode of ['quick_redesign','product_pack']){
    const state={id:'b'.repeat(32),title:'old',mode,revision:1,inputs:{},images:[],plans:{},plan_status:{},stale_plans:[]};
    const h=await harness(state);assert.equal(h.node('quick-slots-field').hidden,true);assert.equal(h.node('shared-reference-field').hidden,false);
    h.node('reference-files').onchange({target:{files:[file('legacy-style.png')],value:''}});h.reject();await h.submit();
    const body=h.calls.at(-1).options.body;assert.equal(body.get('quick_business_version'),null);assert.equal(body.get('quick_slots'),null);assert.equal(body.getAll('reference').length,1);
  }
});
test('switching to V1 never silently hides unbound product-pack references',async()=>{
  const h=await harness();h.node('reference-files').onchange({target:{files:[file('pack.png')],value:''}});h.mode('quick_redesign');
  assert.equal(h.node('task-mode').value,'product_pack');assert.match(h.node('message').textContent,/先移除/);assert.match(h.node('reference-images').textContent,/pack.png/);
});
test('switching back to product pack preserves V1 slot drafts until explicitly removed',async()=>{
  const h=await harness();h.mode('quick_redesign');h.reference(0);h.mode('product_pack');
  assert.equal(h.node('task-mode').value,'quick_redesign');assert.match(h.node('quick-slots').textContent,/reference-0.png/);
  h.node('quick-slot-0-remove').onclick();h.mode('product_pack');assert.equal(h.node('quick-slots-field').hidden,true);
});
