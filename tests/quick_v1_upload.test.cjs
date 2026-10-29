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
const all=(element,predicate)=>[...(predicate(element)?[element]:[]),...element.children.flatMap(child=>all(child,predicate))];
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
    add(type){node('quick-add-'+type).onclick();},
    rows(){return all(node('quick-slots'),e=>e.tag==='article');},
    field(index,part){const row=all(node('quick-slots'),e=>e.tag==='article')[index];return node('quick-slot-'+row.dataset.slotId+'-'+part);},
    reference(index){const row=all(node('quick-slots'),e=>e.tag==='article')[index];const e=node('quick-slot-'+row.dataset.slotId+'-file');e.files=[file('reference-'+index+'.png')];e.onchange();},
    async submit(){node('input-form').onsubmit({preventDefault(){}});await tick();},
    reject(){handler=async()=>({ok:false,json:async()=>({error:'离线保存失败'})});},
  };
}
test('new Quick starts with three fixed slots; enabled outputs stay independent of four products',async()=>{
  const h=await harness();h.mode('quick_redesign');h.products(4);assert.equal(h.rows().length,3);h.add('scene');[0,1,3].forEach(i=>h.reference(i));
  assert.equal(h.rows().length,4);assert.equal(h.node('shared-reference-field').hidden,true);
  h.field(1,'requirements').value='只采用自家尺寸';h.field(1,'requirements').oninput();
  h.reject();await h.submit();const data=h.calls.at(-1).options.body;
  assert.equal(data.get('quick_business_version'),'v1');assert.equal(data.getAll('product').length,4);assert.equal(data.getAll('reference').length,3);
  const slots=JSON.parse(data.get('quick_slots')),active=slots.filter(s=>s.enabled);
  assert.deepEqual(active.map(s=>s.type),['main','dimensions','scene']);
  assert.deepEqual(active.map(s=>s.reference_id),['reference_001','reference_002','reference_003']);
  assert.equal(active[1].requirements,'只采用自家尺寸');assert.equal(active[0].requirements,'');assert.equal(new Set(slots.map(s=>s.id)).size,4);
  // A server failure preserves the real local files and entered requirements.
  assert.match(h.node('message').textContent,/离线保存失败/);assert.match(h.node('quick-slots').textContent,/reference-3.png/);
  assert.equal(h.field(1,'requirements').value,'只采用自家尺寸');await h.submit();assert.equal(h.calls.at(-1).options.body.getAll('product').length,4);
});
test('remove/replace/disable reference changes only that slot and rejects an enabled empty slot',async()=>{
  const h=await harness();h.mode('quick_redesign');h.reference(0);h.reference(1);
  h.field(0,'remove').onclick();assert.equal(h.field(0,'enabled').checked,false);assert.match(h.node('quick-slots').textContent,/reference-1.png/);
  h.reference(1);h.field(0,'enabled').checked=true;h.field(0,'enabled').onchange();await h.submit();
  assert.equal(h.calls.length,0);assert.match(h.node('message').textContent,/必须绑定/);
  h.field(0,'enabled').checked=false;h.field(0,'enabled').onchange();h.reject();await h.submit();
  assert.equal(h.calls.at(-1).options.body.getAll('reference').length,1);
});
test('saved V1 restores slot identity and remaps kept reference ids when saving a separate task',async()=>{
  const state={id:'a'.repeat(32),title:'匿名',mode:'quick_redesign',quick_business_version:'v1',revision:1,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_001',role:'reference',name:'unused.png',file:'inputs/reference_001.png',url:'/unused'},
    {id:'reference_002',role:'reference',name:'bound.png',file:'inputs/reference_002.png',url:'/bound'}],
    quick_slots:[{id:'reference_908',type:'scene',enabled:true,reference_id:'reference_002',requirements:'原要求'}],plans:{},plan_status:{},stale_plans:[]};
  const h=await harness(state);assert.equal(h.field(3,'requirements').value,'原要求');assert.match(h.node('quick-slots').textContent,/bound.png/);
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
test('all three new entries share slot drafts without discarding references, requirements or size',async()=>{
  const h=await harness();h.mode('quick_a');h.reference(0);
  h.field(0,'requirements').value='保留当前文字';h.field(0,'requirements').oninput();
  h.field(0,'size').value='1024x1024';h.field(0,'size').onchange();
  const identity=h.rows()[0].dataset.slotId;
  for(const mode of ['product_pack','quick_b','quick_a']){
    h.mode(mode);assert.equal(h.node('task-mode').value,mode);assert.equal(h.node('quick-slots-field').hidden,false);
    assert.match(h.node('quick-slots').textContent,/reference-0.png/);assert.equal(h.rows()[0].dataset.slotId,identity);
    assert.equal(h.field(0,'requirements').value,'保留当前文字');assert.equal(h.field(0,'size').value,'1024x1024');
  }
});

test('selling and scene add/delete/re-add keep identities, references and sizes isolated without the old caps',async()=>{
  const h=await harness();h.mode('quick_redesign');
  for(let i=0;i<3;i++){h.add('selling_point');h.reference(3+i);h.field(3+i,'requirements').value='selling '+i;h.field(3+i,'requirements').oninput();}
  const initial=h.rows().slice(3).map(e=>e.dataset.slotId);assert.equal(h.node('quick-add-selling_point').disabled,false);
  h.field(4,'delete').onclick();h.add('selling_point');const after=h.rows().slice(3).map(e=>e.dataset.slotId);
  assert.deepEqual(after.slice(0,2),[initial[0],initial[2]]);assert.ok(!initial.includes(after[2]));
  h.field(4,'size').value='1536x1024';h.field(4,'size').onchange();
  h.add('scene');h.reference(6);h.add('scene');h.reference(7);assert.equal(h.node('quick-add-scene').disabled,false);
  const scene=h.rows()[7].dataset.slotId;h.field(6,'delete').onclick();h.add('scene');assert.equal(h.rows()[6].dataset.slotId,scene);
  h.reject();await h.submit();const body=h.calls.at(-1).options.body,slots=JSON.parse(body.get('quick_slots')),sizes=JSON.parse(body.get('image_sizes'));
  assert.equal(slots.length,8);assert.equal(slots.find(s=>s.id===initial[1]),undefined);
  assert.equal(slots.find(s=>s.id===initial[2]).requirements,'selling 2');assert.equal(sizes[initial[2]],'1536x1024');
  assert.equal(body.getAll('reference').length,3);assert.deepEqual(body.getAll('reference').map(f=>f.name),['reference-3.png','reference-5.png','reference-7.png']);
});
test('Listing reference dimensions are serialized and restored with remapped kept asset ids',async()=>{
  const state={id:'c'.repeat(32),title:'pack',mode:'product_pack',revision:1,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_002',role:'reference',name:'reference.png',url:'/ref',file:'inputs/reference_002.png'}],
    image_sizes:{reference_002:'1024x1024'},plans:{},plan_status:{},stale_plans:[]};
  const h=await harness(state),select=all(h.node('reference-images'),e=>e.tag==='select')[0];assert.equal(select.value,'1024x1024');
  select.value='1536x1024';select.onchange();h.reject();await h.submit();
  assert.deepEqual(JSON.parse(h.calls.at(-1).options.body.get('image_sizes')),{reference_001:'1536x1024'});
});
test('saved empty dynamic cards restore; legacy unused placeholders stay collapsed without mutating the task',async()=>{
  const types=['main','dimensions','comparison','selling_point','selling_point','selling_point','scene','scene'];
  const state={id:'d'.repeat(32),title:'slots',mode:'quick_redesign',quick_business_version:'v1',revision:1,
    inputs:{},images:[],plans:{},plan_status:{},stale_plans:[],quick_slots:types.map((type,index)=>({id:'reference_'+(101+index),type,enabled:false,reference_id:null,requirements:''}))};
  const original=JSON.stringify(state),legacy=await harness(state);assert.equal(legacy.rows().length,3);assert.equal(JSON.stringify(state),original);
  const configured={...state,image_sizes:{reference_104:'1024x1024',reference_107:'1536x1024'}};
  const restored=await harness(configured);assert.equal(restored.rows().length,5);
  assert.deepEqual(restored.rows().slice(3).map(row=>row.dataset.slotId),['reference_104','reference_107']);
  assert.equal(restored.field(3,'size').value,'1024x1024');assert.equal(restored.field(4,'size').value,'1536x1024');
});

test('three visible choices persist two backend modes and disclose dimension prerequisites',async()=>{
  const choices=[...template.matchAll(/<option value="(product_pack|quick_a|quick_b|quick_redesign)"([^>]*)>([^<]+)/g)];
  assert.deepEqual(choices.filter(m=>!m[2].includes('hidden')).map(m=>m[1]),['product_pack','quick_a','quick_b']);
  for(const scenario of ['quick_a','quick_b']){
    const h=await harness();h.mode(scenario);h.products(3);h.reference(1);h.reject();await h.submit();
    const data=h.calls.at(-1).options.body;
    assert.equal(data.get('mode'),'quick_redesign');assert.equal(data.get('quick_scenario'),scenario);
    assert.equal(data.get('quick_business_version'),'v1');assert.equal(data.get('listing_slots'),null);
    assert.equal(JSON.parse(data.get('quick_slots')).filter(row=>row.enabled)[0].type,'dimensions');
    assert.match(h.node('mode-note').textContent,/尺寸图须绑定.*真实尺寸.*明确声明/);
    assert.match(h.node('mode-note').textContent,scenario==='quick_a'?/同款同外观.*可沿用适用参考营销信息/:/全部相关商品主体须替换.*不是简单风格迁移/);
    assert.equal(h.node('planning-controls').hidden,true);
  }
});

test('new Listing shares slot upload and keeps text, row ids and per-reference classification on save-as',async()=>{
  const h=await harness();assert.equal(h.node('quick-slots-field').hidden,false);h.products(3);h.reference(1);h.add('scene');h.reference(3);
  h.node('listing').value='手动 Listing';h.node('description').value='手动商品描述';h.node('requirements').value='整体风格';
  h.field(1,'size').value='1536x1024';h.field(1,'size').onchange();
  h.field(1,'requirements').value='仅展示真实尺寸';h.field(1,'requirements').oninput();h.reject();await h.submit();
  const body=h.calls.at(-1).options.body,rows=JSON.parse(body.get('listing_slots'));
  assert.equal(body.get('mode'),'product_pack');assert.equal(body.get('quick_scenario'),null);assert.equal(body.get('quick_slots'),null);
  assert.equal(body.get('image_sizes'),null);assert.equal(body.get('listing'),'手动 Listing');assert.equal(body.get('description'),'手动商品描述');
  assert.deepEqual(rows.filter(s=>s.enabled).map(s=>[s.type,s.reference_id]),[['dimensions','reference_001'],['scene','reference_002']]);
  const state={id:'e'.repeat(32),title:'Listing saved',mode:'product_pack',revision:1,inputs:{listing:'手动 Listing',description:'手动商品描述',requirements:'整体风格'},
    images:[{id:'product_001',role:'product',name:'own.png',url:'/own'},
      {id:'reference_001',role:'reference',name:'dimensions.png',url:'/dimensions'},
      {id:'reference_002',role:'reference',name:'scene.png',url:'/scene'}],listing_slots:rows,plans:{},plan_status:{},stale_plans:[]};
  const saved=JSON.stringify(state),restored=await harness(state);
  assert.equal(restored.rows().length,4);assert.equal(restored.field(1,'size').value,'1536x1024');
  assert.equal(restored.field(1,'requirements').value,'仅展示真实尺寸');assert.equal(restored.node('listing-field').hidden,false);
  restored.field(1,'remove').onclick();restored.reject();await restored.submit();
  const cloned=restored.calls.at(-1).options.body,active=JSON.parse(cloned.get('listing_slots')).filter(s=>s.enabled);
  assert.equal(active[0].id,rows[3].id);assert.equal(active[0].reference_id,'reference_001');
  assert.deepEqual(JSON.parse(cloned.get('keep_images')),['product_001','reference_002']);
  assert.equal(cloned.get('from_session'),state.id);assert.equal(JSON.stringify(state),saved);
});

test('saved Quick scene restores without reclassification or changing stable output identities',async()=>{
  for(const scenario of ['quick_a','quick_b',undefined]){
    const state={id:'f'.repeat(32),title:'scene saved',mode:'quick_redesign',quick_scenario:scenario,quick_business_version:'v1',revision:1,
      inputs:{},images:[{id:'product_001',role:'product',name:'own.png',url:'/own'},
        {id:'reference_002',role:'reference',name:'bound.png',url:'/bound'}],
      quick_slots:[{id:'reference_988',type:'main',enabled:true,reference_id:'reference_002',requirements:''}],plans:{},plan_status:{},stale_plans:[]};
    const h=await harness(state);assert.equal(h.node('task-mode').value,scenario||'quick_redesign');h.reject();await h.submit();
    const data=h.calls.at(-1).options.body;
    assert.equal(data.get('quick_scenario'),scenario||null);assert.equal(JSON.parse(data.get('quick_slots'))[0].id,'reference_988');
    assert.equal(JSON.parse(data.get('quick_slots'))[0].reference_id,'reference_001');
  }
});

test('dynamic N crosses 3/2/8 in all new entries, preserves bindings after middle deletion, refresh and save-as',async()=>{
  assert.doesNotMatch(template,/最多\s*8\s*张|卖点\s*3\s*张|场景\s*2\s*张/);
  for(const mode of ['quick_a','quick_b','product_pack']){
    const h=await harness();h.mode(mode);h.products(3);
    [0,1,2].forEach(index=>h.reference(index));
    for(let i=0;i<4;i++){h.add('selling_point');h.reference(3+i);}
    for(let i=0;i<3;i++){h.add('scene');h.reference(7+i);}
    const sizes=['1024x1024','1024x1536','1536x1024'];
    h.rows().forEach((row,index)=>{
      h.field(index,'requirements').value='要求 '+row.dataset.slotId;h.field(index,'requirements').oninput();
      h.field(index,'size').value=sizes[index%3];h.field(index,'size').onchange();
    });
    const initial=h.rows().map(row=>row.dataset.slotId),removed=[initial[4],initial[8]];
    h.field(4,'delete').onclick();h.add('selling_point');h.reference(6);
    h.field(8,'delete').onclick();h.add('scene');h.reference(9);
    assert.equal(h.rows().length,10);assert.equal(h.node('quick-add-selling_point').disabled,false);
    assert.equal(h.node('quick-add-scene').disabled,false);
    assert.equal(h.node('quick-add-main'),undefined);assert.equal(h.node('quick-add-dimensions'),undefined);assert.equal(h.node('quick-add-comparison'),undefined);
    const identities=h.rows().map(row=>row.dataset.slotId);
    assert.equal(new Set(identities).size,10);removed.forEach(id=>assert.ok(!identities.includes(id)));
    assert.ok(!initial.includes(identities[6]));assert.ok(!initial.includes(identities[9]));
    // Replacing a surviving card's reference must not reset its identity/text/size.
    h.reference(5);assert.equal(h.rows()[5].dataset.slotId,initial[6]);
    h.reject();await h.submit();const data=h.calls.at(-1).options.body;
    const key=mode==='product_pack'?'listing_slots':'quick_slots',config=JSON.parse(data.get(key));
    assert.deepEqual(config.map(row=>row.id),identities);assert.equal(config.filter(row=>row.enabled).length,10);
    assert.equal(config.filter(row=>row.type==='selling_point').length,4);assert.equal(config.filter(row=>row.type==='scene').length,3);
    assert.equal(data.getAll('reference').length,10);assert.equal(data.getAll('product').length,3);
    assert.deepEqual(config.map(row=>row.reference_id),Array.from({length:10},(_,i)=>'reference_'+String(i+1).padStart(3,'0')));
    const imageSizes=mode==='product_pack'?Object.fromEntries(config.map(row=>[row.id,row.output_size])):JSON.parse(data.get('image_sizes'));
    config.forEach(row=>{
      const originalIndex=initial.indexOf(row.id);if(originalIndex<0)return;
      assert.equal(row.requirements,'要求 '+row.id);assert.equal(imageSizes[row.id],sizes[originalIndex%3]);
    });
    const state={id:'9'.repeat(32),title:'dynamic N saved',mode:mode==='product_pack'?'product_pack':'quick_redesign',revision:1,
      inputs:{listing:'原 Listing',description:'原描述',requirements:'整体要求'},images:[
        ...Array.from({length:3},(_,i)=>({id:'product_'+String(i+1).padStart(3,'0'),role:'product',name:'product-'+i+'.png',url:'/product/'+i})),
        ...data.getAll('reference').map((file,i)=>({id:'reference_'+String(i+1).padStart(3,'0'),role:'reference',name:file.name,url:'/reference/'+i}))],
      [key]:config,plans:{},plan_status:{},stale_plans:[]};
    if(mode!=='product_pack'){state.quick_business_version='v1';state.quick_scenario=mode;state.image_sizes=imageSizes;}
    const before=JSON.stringify(state),restored=await harness(state);
    assert.deepEqual(restored.rows().map(row=>row.dataset.slotId),identities);
    config.forEach((row,i)=>{assert.equal(restored.field(i,'requirements').value,row.requirements);assert.equal(restored.field(i,'size').value,imageSizes[row.id]);});
    restored.reject();await restored.submit();const copy=restored.calls.at(-1).options.body;
    assert.deepEqual(JSON.parse(copy.get(key)),config);assert.equal(copy.get('from_session'),state.id);
    assert.equal(copy.getAll('reference').length,0);assert.equal(JSON.parse(copy.get('keep_images')).length,13);
    assert.equal(JSON.stringify(state),before);
    restored.add('selling_point');assert.equal(restored.rows().length,11);
    assert.equal(new Set(restored.rows().map(row=>row.dataset.slotId)).size,11);
  }
});

test('restored dynamic rows use the same type grouping for display and serialization',async()=>{
  const config=[{id:'reference_901',type:'scene'},{id:'reference_902',type:'selling_point'},
    {id:'reference_903',type:'scene'},{id:'reference_904',type:'selling_point'}].map((row,i)=>({...row,
      enabled:true,reference_id:'reference_'+String(i+1).padStart(3,'0'),requirements:'要求 '+i,output_size:'1024x1536'}));
  const state={id:'8'.repeat(32),title:'group order',mode:'product_pack',revision:1,inputs:{},
    images:[{id:'product_001',role:'product',name:'own.png',url:'/own'},...config.map(row=>({id:row.reference_id,role:'reference',name:row.id+'.png',url:'/ref/'+row.id}))],
    listing_slots:config,plans:{},plan_status:{},stale_plans:[]};
  const before=JSON.stringify(state),h=await harness(state);h.reject();await h.submit();
  const order=h.rows().map(row=>row.dataset.slotId),saved=JSON.parse(h.calls.at(-1).options.body.get('listing_slots'));
  assert.deepEqual(order.slice(3),['reference_902','reference_904','reference_901','reference_903']);
  assert.deepEqual(saved.map(row=>row.id),order);assert.equal(JSON.stringify(state),before);
});

test('dimension material is an explicit product choice; changing or deleting it clears declaration',async()=>{
  const h=await harness();h.mode('quick_b');h.products(3);h.reference(1);
  const source=h.field(1,'dimension-source');source.value='1';source.onchange();
  const check=h.field(1,'dimension-confirmed');check.checked=true;check.onchange();
  h.reject();await h.submit();let slot=JSON.parse(h.calls.at(-1).options.body.get('quick_slots'))[1];
  assert.equal(slot.dimension_source_product_id,'product_002');assert.equal(slot.dimension_source_confirmed,true);
  const buttons=all(h.node('product-images'),e=>e.tag==='button');buttons[1].onclick();
  assert.equal(h.field(1,'dimension-source').value,'');assert.equal(h.field(1,'dimension-confirmed').checked,false);
  await h.submit();slot=JSON.parse(h.calls.at(-1).options.body.get('quick_slots'))[1];
  assert.equal(slot.dimension_source_product_id,null);assert.equal(slot.dimension_source_confirmed,false);
});
test('dimension source restores and remaps product identity when saving as a separate Listing',async()=>{
  const state={id:'f'.repeat(32),title:'sizes',mode:'product_pack',revision:3,inputs:{},images:[
    {id:'product_001',role:'product',name:'old.png',url:'/old'},
    {id:'product_002',role:'product',name:'annotated.png',url:'/annotated'},
    {id:'reference_001',role:'reference',name:'layout.png',url:'/layout'}],
    listing_slots:[{id:'reference_102',type:'dimensions',enabled:true,reference_id:'reference_001',requirements:'',
      output_size:'1024x1024',dimension_source_product_id:'product_002',dimension_source_confirmed:true}],
    plans:{},plan_status:{},stale_plans:[]};
  const h=await harness(state);assert.equal(h.field(1,'dimension-source').value,'1');assert.equal(h.field(1,'dimension-confirmed').checked,true);
  all(h.node('product-images'),e=>e.tag==='button')[0].onclick();
  assert.equal(h.field(1,'dimension-source').value,'0');assert.equal(h.field(1,'dimension-confirmed').checked,true);
  h.reject();await h.submit();const slots=JSON.parse(h.calls.at(-1).options.body.get('listing_slots'));
  assert.equal(slots[1].dimension_source_product_id,'product_001');assert.equal(slots[1].dimension_source_confirmed,true);
  assert.equal(state.listing_slots[0].dimension_source_product_id,'product_002');
});
test('legacy Listing can explicitly classify a new copy using existing references, without rewriting its plan',async()=>{
  const state={id:'e'.repeat(32),title:'legacy',mode:'product_pack',revision:3,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_004',role:'reference',name:'saved-layout.png',url:'/layout'}],plans:{},plan_status:{},stale_plans:[]};
  const h=await harness(state);assert.equal(h.node('classify-listing').hidden,false);h.node('classify-listing').onclick();
  assert.equal(h.node('quick-slots-field').hidden,false);
  h.field(0,'existing-reference').value='reference_004';h.field(0,'existing-reference').onchange();
  h.reject();await h.submit();const body=h.calls.at(-1).options.body;
  assert.equal(JSON.parse(body.get('listing_slots'))[0].reference_id,'reference_001');assert.equal(body.get('from_session'),state.id);
  assert.equal(body.getAll('reference').length,0);assert.equal(state.listing_slots,undefined);
});
test('fact dispute shows sources and takes an explicit operator decision through the existing action route',async()=>{
  const state={id:'9'.repeat(32),title:'review',mode:'product_pack',revision:3,inputs:{},images:[],
    product:{identity:'own',claims:'claim',appearance:'visible',uncertainties:'unknown'},plans:{reference_001:{goal:'goal',selling_points:'claim',design:'layout',scene_style:'style',risks:'risk'}},plan_status:{},stale_plans:[],
    fact_issues:[{conflict_id:'call_issue',issue_type:'VISIBLE_CONTRADICTION',affected_claim:'USB-C',resolution_status:'UNRESOLVED',
      text_evidence:{source:'listing',quote:'USB-C'},visual_evidence:{product_image_ids:[],observation:'Mock visible connector differs'},affected_image_ids:['reference_001']}]};
  const h=await harness(state),box=h.node('product-understanding');
  assert.match(box.textContent,/图文明显矛盾（模型报告）/);assert.match(box.textContent,/listing 原文：USB-C/);
  const fields=all(box,e=>e.tag==='textarea');fields.find(e=>e.placeholder?.startsWith('人工依据')).value='运营确认应移除此宣称';
  const decision=all(box,e=>e.tag==='select')[0];decision.value='EXCLUDE';
  for(const field of fields.filter(e=>e.value&&['goal','claim','layout','style','risk'].includes(e.value)))field.value='移除后的计划';
  h.handler=async()=>({ok:true,json:async()=>({state:{...state,revision:4,fact_issues:[]}})});
  all(box,e=>e.tag==='button').find(e=>e.textContent.startsWith('保存人工处理')).onclick();await tick();
  const call=h.calls.at(-1),payload=JSON.parse(call.options.body);
  assert.equal(call.url,'/api/sessions/'+state.id+'/action');assert.equal(payload.action,'resolve_conflict');
  assert.equal(payload.decision,'EXCLUDE');assert.equal(payload.revision,3);assert.equal(payload.plans.reference_001.goal,'移除后的计划');
  assert.equal(h.calls.filter(c=>/generate|revise/.test(c.url)).length,0);
});

test('classifying a legacy Listing transfers reference sizes into slots without sending the old size map',async()=>{
  const state={id:'7'.repeat(32),title:'legacy sizes',mode:'product_pack',revision:4,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_004',role:'reference',name:'saved-layout.png',url:'/layout'}],
    image_sizes:{reference_004:'1536x1024'},plans:{},plan_status:{},stale_plans:[]};
  const before=JSON.stringify(state),h=await harness(state);h.node('classify-listing').onclick();
  h.field(0,'existing-reference').value='reference_004';h.field(0,'existing-reference').onchange();
  assert.equal(h.field(0,'size').value,'1536x1024');
  h.reject();await h.submit();const body=h.calls.at(-1).options.body;
  assert.equal(body.get('image_sizes'),null);
  assert.equal(JSON.parse(body.get('listing_slots'))[0].output_size,'1536x1024');
  assert.equal(JSON.parse(body.get('listing_slots'))[0].reference_id,'reference_001');
  assert.equal(JSON.stringify(state),before);
});

test('quality defaults and per-slot choices persist and remap on save-as without mixing references',async()=>{
  const h=await harness();h.mode('product_pack');h.products(3);h.reference(0);h.add('selling_point');h.reference(3);
  h.node('generation-quality').value='medium';h.field(0,'quality').value='low';h.field(0,'quality').onchange();h.field(3,'quality').value='high';h.field(3,'quality').onchange();
  h.reject();await h.submit();let body=h.calls.at(-1).options.body;
  assert.equal(body.get('generation_quality'),'medium');assert.deepEqual(JSON.parse(body.get('image_qualities')),{reference_001:'low',reference_002:'high'});
  const state={id:'d'.repeat(32),mode:'product_pack',title:'anonymous',revision:1,inputs:{},images:[
    {id:'product_001',role:'product',name:'own.png',url:'/own'},
    {id:'reference_001',role:'reference',name:'unused.png',url:'/unused'},
    {id:'reference_002',role:'reference',name:'used.png',url:'/used'}],
    generation_quality:'medium',image_qualities:{reference_002:'high'},listing_slots:[{id:'reference_905',type:'scene',enabled:true,reference_id:'reference_002',requirements:''}],plans:{},plan_status:{},stale_plans:[]};
  const restored=await harness(state);assert.equal(restored.node('generation-quality').value,'medium');assert.equal(restored.field(3,'quality').value,'high');restored.reject();await restored.submit();body=restored.calls.at(-1).options.body;assert.deepEqual(JSON.parse(body.get('image_qualities')),{reference_001:'high'});
});
test('manual plan editor sends exact five fields and a free version-bound operation',async()=>{
  const plan={goal:'old goal',selling_points:'old claims',design:'old design',scene_style:'old style',risks:'old risks'};
  const state={id:'e'.repeat(32),mode:'product_pack',title:'anonymous',revision:3,inputs:{},images:[],product:{identity:'fixture'},plans:{reference_001:plan},references:{},plan_status:{reference_001:{plan_version:2,confirmed:true}},stale_plans:[],events:[]};
  const h=await harness(state),view=h.window.PreparePlan.renderCardPlan({id:'reference_001'},false);
  const goal=all(view,e=>e.dataset.planField==='goal')[0];goal.value='human goal';goal.oninput();
  h.handler=async(url,options)=>({ok:true,json:async()=>({state:{...state,revision:4,plans:{reference_001:{...plan,goal:'human goal'}},plan_status:{reference_001:{plan_version:3,confirmed:false}}}})});
  const save=all(view,e=>e.dataset.action==='save-manual-plan')[0];await save.onclick();
  const posts=h.calls.filter(c=>c.options?.method==='POST');assert.equal(posts.length,1);const body=JSON.parse(posts[0].options.body);
  assert.equal(body.action,'manual_plan');assert.equal(body.plan_version,2);assert.equal(body.revision,3);assert.equal(body.target,'reference_001');assert.deepEqual(body.plan,{...plan,goal:'human goal'});assert.match(h.node('message').textContent,/模型调用 0 次/);
});
