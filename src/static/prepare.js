(() => {
"use strict";
let state = null, dirty = false, busy = false;
let kept = [], pending = {product: [], reference: []};
const slotTypes=[['main','主图',{multiple:false,max:1}],['dimensions','尺寸图',{multiple:false,max:1}],['comparison','同类商品对比图',{multiple:false,max:1}],['selling_point','卖点图',{multiple:true,max:null}],['scene','使用场景图',{multiple:true,max:null}]];
let classifyLegacy=false;
let quickSlots=[],usedSlotIds=new Set(),nextSlotSerial=101;
const outputSizes=[['1024x1536','竖图 2:3 · 1024×1536'],['1024x1024','方图 1:1 · 1024×1024'],['1536x1024','横图 3:2 · 1536×1024']];
let operation=null,remoteBusy=false,progressPoll=null,imageBusy=false;
const feedbackDrafts=new Map();
const actionNames={understand:'AI 理解与规划',product:'AI 修正商品理解',reference:'AI 修正参考理解',plan:'AI 修改本张计划',replan:'AI 重新规划',confirm:'确认计划'};
function drawProgress(){const box=$('operation-progress');if(!operation){box.hidden=true;return;}box.hidden=false;box.className=operation.status==='RUNNING'?'waiting':'muted';const end=operation.finished_at?Date.parse(operation.finished_at):Date.now();const seconds=Math.max(0,Math.floor((end-Date.parse(operation.started_at))/1000));box.textContent=`${operation.name} · ${operation.status==='RUNNING'?'正在执行':operation.status==='SUCCEEDED'?'已完成':operation.status==='FAILED'?'失败':'执行状态待确认'} · 已等待 ${seconds} 秒${operation.status==='INTERRUPTED'?'；服务曾中断，服务端执行及费用需核对，未自动重试。':''}`;}
setInterval(drawProgress,1000);
const $ = id => document.getElementById(id);
const readOnlyWorkspace=document.body.dataset.workspaceReadOnly==='true';
const productFields = {identity:"商品识别", claims:"Listing 声称 · 待核验", appearance:"实拍外观 · 候选识别", uncertainties:"冲突与待确认"};
const referenceFields = {style:"视觉风格", composition:"构图方式", layout:"信息布局", expression:"视觉表达", applicable:"可借鉴的方法", risks:"边界与待确认"};
const planFields = {goal:"表达目标", selling_points:"主要卖点", design:"设计与构图", scene_style:"场景与风格", risks:"风险与待确认"};
const redesignDefault='提升商业设计质量、排版与信息层级、光影与背景、场景表现及原有卖点的视觉表达。';
function isQuick(){return ['quick_redesign','quick_a','quick_b'].includes($('task-mode').value);}
function isQuickV1(){return isQuick()&&(!state||state.quick_business_version==='v1');}
function usesSlots(){return isQuickV1()||(!isQuick()&&(!state||classifyLegacy||Array.isArray(state.listing_slots)));}
function hasQuickScenario(){return ['quick_a','quick_b'].includes($('task-mode').value);}
function defaultSize(){return isQuick()?state?.output_size||$('output-size').value||'1024x1536':'1024x1536';}
function sizeControl(value,change,id){
  const label=element('label','输出尺寸'),select=element('select');if(id)select.id=id;
  select.setAttribute('aria-label','输出尺寸');
  outputSizes.forEach(([value,text])=>{const option=element('option',text);option.value=value;select.append(option);});
  select.value=value;select.onchange=()=>{change(select.value);markDirty();};label.append(select);return label;
}
function makeSlot(type,original=null){
  while(usedSlotIds.has('reference_'+nextSlotSerial))nextSlotSerial++;
  const id=original?.id||'reference_'+nextSlotSerial++;usedSlotIds.add(id);
  return {id,type,enabled:original?.enabled||false,requirements:original?.requirements||'',
    dimensionSource:kept.find(image=>image.role==='product'&&image.id===original?.dimension_source_product_id)||null,dimensionConfirmed:original?.dimension_source_confirmed===true,
    outputSize:original?.output_size||state?.image_sizes?.[id]||defaultSize(),reference:kept.find(image=>image.id===original?.reference_id)||null};
}
function resetSlots(){
  quickSlots.forEach(slot=>{if(slot.reference?.localFile)URL.revokeObjectURL(slot.reference.url);});
  const saved=state?.listing_slots||(state?.quick_business_version==='v1'?state.quick_slots:[]);
  usedSlotIds=new Set(saved.map(slot=>slot.id));nextSlotSerial=101;
  quickSlots=slotTypes.slice(0,3).map(([type])=>makeSlot(type,saved.find(slot=>slot.type===type)));
  // CP2 saved all eight placeholders. Hide only its unused dynamic placeholders;
  // a newly saved empty card has an explicit size entry and remains restorable.
  saved.filter(slot=>['selling_point','scene'].includes(slot.type)&&
    (slot.enabled||slot.reference_id||slot.requirements||slot.output_size||state.image_sizes?.[slot.id])).forEach(slot=>quickSlots.push(makeSlot(slot.type,slot)));
  quickSlots.sort((a,b)=>slotTypes.findIndex(([type])=>type===a.type)-slotTypes.findIndex(([type])=>type===b.type));
}
function renderSlots(){
  const box=$('quick-slots');box.replaceChildren();
  for(const [type,label,policy] of slotTypes){
    const dynamic=policy.multiple,limit=policy.max,items=quickSlots.filter(slot=>slot.type===type);
    const atLimit=limit!==null&&items.length>=limit;
    const group=element('section',undefined,'quick-slot-group'+(dynamic?' quick-slot-dynamic':'')),grid=element('div',undefined,'quick-slot-grid');
    if(dynamic)group.append(element('h4',label+' · '+items.length+(limit===null?' 张':' / '+limit)));
    items.forEach((slot,index)=>{
      const title=label+(dynamic?' '+(index+1):''),prefix='quick-slot-'+slot.id;
      const row=element('article',undefined,'quick-slot');row.dataset.slotId=slot.id;row.dataset.slotType=type;
      const heading=element('label',undefined,'quick-slot-toggle'),enabled=element('input');enabled.type='checkbox';enabled.id=prefix+'-enabled';enabled.checked=slot.enabled;
      enabled.onchange=()=>{slot.enabled=enabled.checked;renderSlots();markDirty();};heading.append(enabled,element('strong',title));row.append(heading);
      if(dynamic){const removeCard=element('button','删除本图位','secondary');removeCard.type='button';removeCard.id=prefix+'-delete';
        removeCard.onclick=()=>{if(slot.reference?.localFile)URL.revokeObjectURL(slot.reference.url);quickSlots=quickSlots.filter(item=>item!==slot);renderSlots();markDirty();};row.append(removeCard);}
      if(slot.reference){const image=element('img');image.src=slot.reference.url;image.alt=title+'主要设计参考';row.append(image,element('small',slot.reference.name));}
      const available=kept.filter(image=>image.role==='reference');
      if(available.length){const label=element('label','绑定已有参考'),select=element('select');select.id=prefix+'-existing-reference';
        const empty=element('option','请选择');empty.value='';select.append(empty);
        available.forEach(image=>{const option=element('option',image.name);option.value=image.id;select.append(option);});select.value=slot.reference?.id||'';
        select.onchange=()=>{if(slot.reference?.localFile)URL.revokeObjectURL(slot.reference.url);slot.reference=available.find(image=>image.id===select.value)||null;slot.enabled=Boolean(slot.reference);if(classifyLegacy&&state?.image_sizes?.[slot.reference?.id])slot.outputSize=state.image_sizes[slot.reference.id];renderSlots();markDirty();};label.append(select);row.append(label);}
      const upload=element('label',slot.reference?'替换主要参考':'添加一张主要参考','upload'),file=element('input');file.type='file';file.id=prefix+'-file';file.accept='image/jpeg,image/png,image/webp';file.setAttribute('aria-label',title+'主要参考');
      file.onchange=()=>{
        const selected=Array.from(file.files||[]);if(!selected.length)return;
        if(selected.length!==1||!['image/jpeg','image/png','image/webp'].includes(selected[0].type)||selected[0].size>20*1024*1024){notify('每个图位只允许一张 JPG、PNG 或 WebP 参考，最大 20 MB。',true);file.value='';return;}
        if(slot.reference?.localFile)URL.revokeObjectURL(slot.reference.url);
        slot.reference={localFile:selected[0],name:selected[0].name,url:URL.createObjectURL(selected[0]),role:'reference'};slot.enabled=true;renderSlots();markDirty();
      };upload.append(file);row.append(upload);
      const remove=element('button','移除参考','secondary');remove.type='button';remove.id=prefix+'-remove';remove.disabled=!slot.reference;remove.dataset.emptyReference=String(!slot.reference);
      remove.onclick=()=>{if(slot.reference?.localFile)URL.revokeObjectURL(slot.reference.url);slot.reference=null;slot.enabled=false;renderSlots();markDirty();};row.append(remove);
      if(type==='dimensions'){
        const products=[...kept.filter(image=>image.role==='product'),...pending.product];
        if(!products.includes(slot.dimensionSource)){slot.dimensionSource=null;slot.dimensionConfirmed=false;}
        const label=element('label','尺寸专项白底商品素材'),select=element('select');select.id=prefix+'-dimension-source';
        const empty=element('option','未提供 · 本次不制作尺寸图');empty.value='';select.append(empty);
        products.forEach((image,index)=>{const option=element('option',image.name);option.value=String(index);select.append(option);});
        select.value=slot.dimensionSource?String(products.indexOf(slot.dimensionSource)):'';
        select.onchange=()=>{slot.dimensionSource=select.value===''?null:products[Number(select.value)];slot.dimensionConfirmed=false;renderSlots();markDirty();};label.append(select);row.append(label);
        const declaration=element('label','我声明：该白底素材已标注当前商品真实尺寸（不是系统独立认证）'),check=element('input');check.type='checkbox';check.id=prefix+'-dimension-confirmed';check.checked=slot.dimensionConfirmed;
        check.onchange=()=>{if(!slot.dimensionSource){check.checked=false;notify('请先选择本任务的尺寸专项商品素材。',true);return;}slot.dimensionConfirmed=check.checked;markDirty();};declaration.append(check);row.append(declaration);
      }
      row.append(sizeControl(slot.outputSize,value=>slot.outputSize=value,prefix+'-size'));
      const requirementLabel=element('label','补充制作要求（选填）'),requirements=element('textarea');requirements.id=prefix+'-requirements';requirements.rows=2;requirements.maxLength=12000;requirements.value=slot.requirements;requirements.oninput=()=>{slot.requirements=requirements.value;markDirty();};requirementLabel.append(requirements);row.append(requirementLabel);
      row.append(element('p',slot.enabled?'已启用 · 保存后建立输出项':slot.reference?'未启用 · 仅保存参考，不产生输出':'未启用 · 不产生输出','muted'));grid.append(row);
    });
    if(dynamic){const add=element('button',atLimit?'已达上限（'+limit+' 张）':'＋ 添加'+label,'quick-slot-add');add.type='button';add.id='quick-add-'+type;add.disabled=atLimit;add.dataset.slotLimit=String(add.disabled);
      add.onclick=()=>{if(limit!==null&&quickSlots.filter(slot=>slot.type===type).length>=limit)return;quickSlots.push(makeSlot(type));quickSlots.sort((a,b)=>slotTypes.findIndex(([type])=>type===a.type)-slotTypes.findIndex(([type])=>type===b.type));renderSlots();markDirty();};grid.append(add);}
    group.append(grid);box.append(group);
  }
}
function renderMode(){
  const quick=isQuick(),v1=isQuickV1(),slotted=usesSlots();
  $('output-size-field').hidden=v1;$('shared-reference-field').hidden=slotted;$('quick-slots-field').hidden=!slotted;
  for(const id of ['listing-field','description-field','understanding-section','planning-controls'])$(id).hidden=quick;
  $('redesign-fields').hidden=!quick;$('load-case').hidden=quick;
  $('mode-note').textContent=hasQuickScenario()?($('task-mode').value==='quick_a'?'Quick-A：运营声明同款同外观；实际商品图决定外观，可沿用适用参考营销信息。':'Quick-B：运营声明相关营销信息适用；参考中全部相关商品主体须替换为实际商品，不是简单风格迁移。')+'无需独立 Planning，生成结果待人工审核。尺寸图须绑定已标注真实尺寸的白底商品素材并明确声明；系统不认证尺寸真实性。':v1?'历史 Quick V1（未分类）：保留既有商品素材与图位策略；不自动归为 Quick-A/B。':quick?'历史 Quick：每张原图独立重设计；保留原有风格参考行为。':slotted?'Listing：图位分类、要求和尺寸进入原有 AI 规划；仍需逐图人工确认，分类不代表规划质量已通过。':'历史 Listing：保留原记录、审核和导出；新增生成/修改须先分类另存，再重新规划与确认。';
  $('classify-listing').hidden=quick||slotted;
  $('input-title').textContent=slotted?'同 SKU 商品素材与图位参考':quick?'待重设计图片与整体要求':'商品资料与参考图';
  $('product-label').textContent=slotted?'同 SKU 商品素材（白底、尺寸、细节等）':quick?'待重设计原图':'商品原图';
  $('reference-label').textContent=quick?'风格参考图（可选）':'设计参考图';
  $('save-inputs').textContent=state?'另存为新任务':'保存资料';
  $('input-summary').textContent=(state?.title||'新建任务')+' · '+(hasQuickScenario()?($('task-mode').value==='quick_a'?'Quick-A｜同款快速改版':'Quick-B｜换主体快速改版'):quick?'历史 Quick（未分类）':'Listing｜商品资料制图');
  $('workspace-title').textContent=state?.title||'新建商品图任务';
}
function element(tag, text, className) {const e=document.createElement(tag); if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function notify(text, error=false) {$('message').textContent=text;$('message').className=error?'error':'';$('message').hidden=false;}
async function api(url, options={}) {if(readOnlyWorkspace&&!['GET','HEAD'].includes((options.method||'GET').toUpperCase()))throw new Error('匿名只读预览不能保存或修改；请进入 8013 Live Debug 工作台。');const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查本地服务是否仍在运行。');}if(!response.ok)throw new Error(body.error||'操作失败');return body;}
function updateButtons() {
  const locked=readOnlyWorkspace||busy||remoteBusy||imageBusy;
  document.querySelectorAll('#input-panel button,#input-panel input,#input-panel textarea,#input-panel select,#planning-controls button,.ai-mutation,.feedback textarea').forEach(e=>e.disabled=locked);
  document.querySelectorAll('#quick-slots button[data-empty-reference="true"],#quick-slots button[data-slot-limit="true"]').forEach(e=>e.disabled=true);
  $('task-mode').disabled=locked||Boolean(state);
  $('understand').disabled=locked||window.Workspace?.aiAllowed?.()===false||Boolean(state?.product&&!dirty);
  $('replan').disabled=locked||window.Workspace?.aiAllowed?.()===false||!state?.product||dirty;
  document.querySelectorAll('.ai-mutation,.feedback textarea').forEach(e=>e.disabled=locked||dirty);
  $('enter-generate').hidden=!(state?.confirmed&&!dirty);
  document.body.classList.toggle('busy',busy||remoteBusy||imageBusy);
  window.Workspace?.planningChanged();
}
async function work(fn,propagate=false) {if(busy||remoteBusy||imageBusy){if(propagate)throw new Error('已有操作正在执行，请稍候。');return;}busy=true;operation={name:'读取或保存资料',started_at:new Date().toISOString(),status:'RUNNING'};drawProgress();updateButtons();try{const result=await fn();if(!remoteBusy&&!operation.fromSaved)operation.status='SUCCEEDED';return result;}catch(error){operation.status='FAILED';notify(error.message,true);if(propagate)throw error;}finally{busy=false;if(!remoteBusy&&!operation.fromSaved)operation.finished_at=new Date().toISOString();drawProgress();updateButtons();}}
function markDirty(){dirty=true;$('input-note').textContent=isQuick()?'资料有修改。保存为新任务后继续重设计，旧任务保留。':'资料有修改。保存为新任务后重新理解与规划，旧任务保留。';updateButtons();}
function releasePending(){Object.values(pending).flat().forEach(item=>URL.revokeObjectURL(item.url));pending={product:[],reference:[]};}
function renderImages(){
  for(const role of ['product','reference']){
    const container=$(role+'-images');container.replaceChildren();
    const images=[...kept.filter(i=>i.role===role).map(i=>({...i,existing:true})),...pending[role]];
    $(role+'-count').textContent=images.length+' 张';
    images.forEach(image=>{const wrap=element('div',undefined,'thumb');const source=image.existing?kept.find(item=>item.id===image.id):image;const img=element('img');img.src=image.url;img.alt=image.name;const remove=element('button','×','remove-image');remove.type='button';remove.setAttribute('aria-label','移除 '+image.name);remove.onclick=()=>{if(image.existing)kept=kept.filter(i=>i.id!==image.id);else{pending[role]=pending[role].filter(i=>i!==image);URL.revokeObjectURL(image.url);}renderImages();renderSlots();markDirty();};wrap.append(img,remove,element('small',image.name));if(role==='reference'&&!isQuick())wrap.append(sizeControl(source.outputSize||defaultSize(),value=>source.outputSize=value));container.append(wrap);});
  }
}
function describe(value, labels){const dl=element('dl',undefined,'details');for(const [key,label] of Object.entries(labels))dl.append(element('dt',label),element('dd',value[key]));return dl;}
function renderHistory(target, action){
  const events=(state?.events||[]).filter(event=>event.action===action&&event.target===target);
  const box=element('details',undefined,'history');box.append(element('summary',`修改记录（${events.length}）`));
  events.forEach(event=>{const row=element('div',undefined,'history-item');row.append(element('small',new Date(event.at).toLocaleString('zh-CN')),element('p','意见：'+event.feedback));
    if(event.before){const previous=element('details');previous.append(element('summary','查看修改前内容'));const labels=action==='plan'?planFields:action==='product'?productFields:referenceFields;previous.append(describe(event.before,labels));row.append(previous);}box.append(row);});return box;
}
function feedbackBox(action,target,label,buttonText){
  const box=element('div',undefined,'feedback');const id='feedback-'+action+'-'+(target||'product');
  const lab=element('label',label);lab.htmlFor=id;const row=element('div',undefined,'row');const input=element('textarea');input.id=id;input.value=feedbackDrafts.get(id)||'';input.oninput=()=>feedbackDrafts.set(id,input.value);input.disabled=readOnlyWorkspace||busy||remoteBusy||imageBusy||dirty;input.rows=2;input.maxLength=12000;input.placeholder=action==='plan'?'例如：不要展示配件，采用浅粉色背景。':action==='product'?'例如：这不是冲击电钻，不要强调冲击功能。':'例如：只参考信息排版，不参考产品使用场景。';
  const button=element('button',buttonText,'secondary ai-mutation');button.type='button';button.disabled=readOnlyWorkspace||busy||remoteBusy||imageBusy||dirty;button.onclick=()=>{if(!input.value.trim()){notify('请先填写修改意见。',true);return;}work(()=>runAction(action,target,input.value));};row.append(input,button);box.append(lab,row,renderHistory(target,action));return box;
}
function renderCardPlan(image,editable=true){
  const details=element('details',undefined,'card-plan');const plan=state?.plans[image.id];
  const status=state?.plan_status[image.id],stale=state?.stale_plans.includes(image.id);details.open=Boolean(plan&&!status?.confirmed);
  details.append(element('summary',plan?(stale?'当前计划 · 理解已改变，待更新':`当前计划 V${status.plan_version} · ${status.confirmed?'已确认':'待确认'}`):'制作计划 · 尚未规划'));
  if(plan){details.append(describe(plan,planFields));if(editable)details.append(feedbackBox('plan',image.id,'本张计划的修改意见','根据意见修改计划'));}
  else details.append(element('p','先保存资料并主动点击 AI 理解与规划。','muted'));
  if(state?.references[image.id]){const understanding=element('details',undefined,'history');understanding.append(element('summary','参考图理解与修正'),describe(state.references[image.id],referenceFields));if(editable)understanding.append(feedbackBox('reference',image.id,'修正这张参考图的理解','根据意见修正理解'));details.append(understanding);}
  return details;
}
function renderFactIssues(container){
  for(const issue of state.fact_issues||[]){
    const box=element('section',undefined,'feedback');
    box.append(element('h4',(issue.issue_type==='VISIBLE_CONTRADICTION'?'图文明显矛盾（模型报告）':'证据不足 · 不等于矛盾')+' · '+issue.resolution_status),
      element('p','争议宣称：'+issue.affected_claim),element('p',issue.text_evidence.source+' 原文：'+issue.text_evidence.quote),
      element('p','可见依据：'+issue.visual_evidence.observation),element('p','受影响图位：'+issue.affected_image_ids.join('、')));
    for(const id of issue.visual_evidence.product_image_ids){const image=state.images.find(i=>i.id===id);if(image){const img=element('img');img.src=image.url;img.alt=image.name;img.setAttribute('style','max-width:160px');box.append(img);}}
    if(issue.operator_resolution)box.append(element('p','已有人工决定：'+issue.operator_resolution.decision+'；'+issue.operator_resolution.note+'（仅适用有效版本，非独立认证）'));
    const decision=element('select');decision.className='ai-mutation';
    for(const [value,text] of [['RETAIN','人工决定继续使用'],['CORRECT','修正宣称和计划'],['EXCLUDE','移除宣称并修订计划']]){const option=element('option',text);option.value=value;decision.append(option);}decision.value='RETAIN';
    const note=element('textarea');note.rows=2;note.maxLength=12000;note.className='ai-mutation';note.placeholder='人工依据/修正或移除的具体宣称；不会改写原始资料';
    const editor=element('details');editor.append(element('summary','修正/移除时填写受影响图位计划（五项均需填写）'));const inputs={};
    for(const id of issue.affected_image_ids){editor.append(element('strong',id));inputs[id]={};for(const [key,label] of Object.entries(planFields)){const wrap=element('label',label),field=element('textarea');field.className='ai-mutation';field.value=state.plans[id]?.[key]||'';field.maxLength=12000;inputs[id][key]=field;wrap.append(field);editor.append(wrap);}}
    const save=element('button','保存人工处理（不调用 AI），再确认本图计划','secondary ai-mutation');save.type='button';
    save.onclick=()=>work(async()=>{if(dirty)throw new Error('资料已修改，请先另存新任务。');const payload={action:'resolve_conflict',revision:state.revision,conflict_id:issue.conflict_id,decision:decision.value,note:note.value};
      if(decision.value!=='RETAIN')payload.plans=Object.fromEntries(Object.entries(inputs).map(([id,fields])=>[id,Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.value]))]));
      const body=await api('/api/sessions/'+state.id+'/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});applyState(body.state);notify('人工处理已保存。请核对修订计划，再执行原有逐图确认。');});
    box.append(decision,note,editor,save);container.append(box);
  }
}
function renderResults(){
  renderMode();const ready=Boolean(state?.product);$('understanding-empty').hidden=ready;
  const product=$('product-understanding');product.hidden=!ready;product.replaceChildren();
  if(ready){product.append(describe(state.product,productFields),feedbackBox('product',null,'修正商品理解','根据意见修正理解'));renderFactIssues(product);}
  const plans=Object.values(state?.plan_status||{}),confirmed=plans.filter(p=>p.confirmed).length;
  $('confirmation-title').textContent=state?.product?`本图计划逐张确认 · 已确认 ${confirmed} / ${plans.length} 张`:'先保存资料，再主动执行 AI 理解与规划';
  const unresolved=(state?.fact_issues||[]).filter(issue=>issue.issue_type==='VISIBLE_CONTRADICTION'&&issue.resolution_status!=='RESOLVED');
  if(unresolved.length)$('input-panel').open=true;
  $('confirmation-note').textContent=unresolved.length?'有 '+unresolved.length+' 项图文事实争议待人工处理。请在共享资料中查看原文与商品图片依据；受影响计划不能确认或生成。':state?.stale_plans.length?'理解已修正，请更新受影响计划后逐张确认；其他有效确认和旧成图保留。':'在对应卡片点击「确认本图计划」后即可单独生成。修改本张计划只撤销本图确认，不自动批量确认。';
  updateButtons();
}
function applyState(value,activity=null){classifyLegacy=false;if(state?.id!==value.id)feedbackDrafts.clear();state=value;dirty=false;window.history.replaceState(null,'','/workspace/'+state.id);$('task-mode').value=state.quick_scenario||state.mode||'product_pack';$('task-title').value=state.title;releasePending();kept=state.images.map(i=>({...i,outputSize:state.image_sizes?.[i.id]||(state.mode==='quick_redesign'?state.output_size:'1024x1536')}));for(const key of ['listing','description','requirements','product_facts'])$(key).value=state.inputs[key]||'';$('output-size').value=state.output_size||'1024x1536';$('product-files').value='';$('reference-files').value='';$('saved-status').textContent=isQuick()?'重设计资料已保存':state.confirmed?'计划已确认':'资料与修改已保存';$('input-note').textContent=state.title+' · 当前任务已保存，刷新后可恢复。';
  resetSlots();renderSlots();
  remoteBusy=activity?.status==='RUNNING';clearTimeout(progressPoll);
  if(activity){operation={...activity,fromSaved:true,name:actionNames[activity.action]||'AI 操作',status:activity.status==='AI_RESULT_RECEIVED'?'SUCCEEDED':activity.status};drawProgress();}
  if(remoteBusy)progressPoll=setTimeout(async()=>{try{const body=await api('/api/sessions/'+state.id);const active=body.activity;if(active?.status!=='RUNNING'){operation={...active,name:actionNames[active?.action]||'AI 操作',status:active?.status==='AI_RESULT_RECEIVED'?'SUCCEEDED':active?.status||'FAILED'};drawProgress();}applyState(body.state,body.activity);}catch(error){notify('状态读取失败：'+error.message+'；未自动重试模型请求。',true);}},2000);
  renderImages();renderResults();window.dispatchEvent?.(new CustomEvent('workspace:task-changed',{detail:{task_id:state.id}}));}
async function saveInputs(){
  const data=new FormData();for(const key of ['listing','description','requirements'])data.append(key,$(key).value);
  data.append('mode',isQuick()?'quick_redesign':'product_pack');
  if(hasQuickScenario())data.append('quick_scenario',$('task-mode').value);
  if(isQuick()){data.append('product_facts',$('product_facts').value);data.append('output_size',$('output-size').value);}
  data.append('title',$('task-title').value);
  let keep=kept;const imageSizes={};
  if(usesSlots()){
    if(!quickSlots.some(slot=>slot.enabled))throw new Error('请至少启用一个图位，并绑定主要设计参考。');
    if(quickSlots.some(slot=>slot.enabled&&!slot.reference))throw new Error('已启用图位必须绑定一张主要设计参考。');
    const used=new Set(quickSlots.map(slot=>slot.reference?.id).filter(Boolean));
    keep=kept.filter(image=>image.role==='product'||used.has(image.id));
    const references=[...keep.filter(image=>image.role==='reference'),...quickSlots.map(slot=>slot.reference).filter(image=>image?.localFile)];
    const referenceId=image=>'reference_'+String(references.indexOf(image)+1).padStart(3,'0');
    const products=[...keep.filter(image=>image.role==='product'),...pending.product];
    const configuration=quickSlots.map(slot=>({...(slot.type==='dimensions'?{dimension_source_product_id:slot.dimensionSource?'product_'+String(products.indexOf(slot.dimensionSource)+1).padStart(3,'0'):null,dimension_source_confirmed:slot.dimensionConfirmed}:{}),id:slot.id,type:slot.type,enabled:slot.enabled,
      reference_id:slot.reference?referenceId(slot.reference):null,requirements:slot.requirements}));
    if(isQuickV1()){
      quickSlots.forEach(slot=>imageSizes[slot.id]=slot.outputSize);
      data.append('quick_business_version','v1');data.append('quick_slots',JSON.stringify(configuration));
    }else data.append('listing_slots',JSON.stringify(configuration.map((slot,index)=>({...slot,output_size:quickSlots[index].outputSize}))));
    references.filter(image=>image.localFile).forEach(image=>data.append('reference',image.localFile,image.localFile.name));
  }else{
    pending.reference.forEach(item=>data.append('reference',item.file,item.file.name));
    if(!isQuick())[...keep.filter(image=>image.role==='reference'),...pending.reference].forEach((image,index)=>{imageSizes['reference_'+String(index+1).padStart(3,'0')]=image.outputSize||defaultSize();});
    else if(state?.image_sizes)[...keep.filter(image=>image.role==='product'),...pending.product].forEach((image,index)=>{imageSizes['product_'+String(index+1).padStart(3,'0')]=image.outputSize||defaultSize();});
  }
  if(isQuickV1()||(!isQuick()&&!usesSlots())||(isQuick()&&state?.image_sizes))data.append('image_sizes',JSON.stringify(imageSizes));
  if(state){data.append('from_session',state.id);data.append('keep_images',JSON.stringify(keep.map(i=>i.id)));}
  pending.product.forEach(item=>data.append('product',item.file,item.file.name));
  const body=await api('/api/sessions',{method:'POST',body:data});applyState(body.state);
}
async function runAction(action,target=null,feedback='',expected=null){
  if(dirty)throw new Error('资料有修改，请先保存为新任务，再进行 AI 理解与规划。');
  if(!state)throw new Error('请先加载或保存商品资料。');
  if(expected&&(state.id!==expected.taskId||state.revision!==expected.stateRevision))throw new Error('任务或计划版本已改变，请刷新后重新提交；未调用模型。');
  const taskId=state.id,revision=state.revision;
  operation.name=actionNames[action];drawProgress();notify(action==='confirm'?'正在保存确认计划。':'AI 正在处理，请稍候。不会自动重试；连接失败时服务端执行与费用需核对。');
  const body=await api(`/api/sessions/${taskId}/action`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,target,feedback,revision,...(action==='confirm'?{plan_version:state.plan_status[target].plan_version}:{})})});
  if(state.id===taskId){
    feedbackDrafts.delete('feedback-'+action+'-'+(target||'product'));
    if(state.revision===revision)applyState(body.state);
    notify(action==='confirm'?'本图当前计划已确认，其他图片的确认和成图未改变。':action==='plan'?'本张计划已更新，请重新确认本图；其他计划保持不变。':action==='product'||action==='reference'?'理解已修正。后续规划将使用修正结果，受影响的已有计划请显式更新后再确认。':'AI 理解与规划已保存，请逐图检查并确认候选计划。');
  }
  return body;
}
$('load-case').onclick=()=>work(async()=>{const body=await api('/api/case-001',{method:'POST'});applyState(body.state);notify('case-001 已加载为独立资料副本，未调用 AI。');});
$('input-form').onsubmit=event=>{event.preventDefault();work(async()=>{await saveInputs();$('input-panel').open=false;notify('资料已保存为新任务，旧任务未覆盖；可在下方卡片继续。');});};
$('understand').onclick=()=>work(async()=>{if(dirty||!state)await saveInputs();await runAction('understand');});
$('replan').onclick=()=>work(()=>runAction('replan'));
for(const key of ['listing','description','requirements','task-title','product_facts','output-size'])$(key).addEventListener('input',markDirty);
$('task-mode').onchange=()=>{if(usesSlots()&&pending.reference.length){$('task-mode').value='product_pack';notify('请先移除商品图包的共享设计参考，再切换 Quick；新入口请在对应图位上传参考。',true);return;}if(isQuick()&&!$('requirements').value.trim())$('requirements').value=redesignDefault;renderMode();renderImages();markDirty();};
for(const role of ['product','reference'])$(role+'-files').onchange=event=>{for(const file of event.target.files)pending[role].push({file,name:file.name,url:URL.createObjectURL(file),role,outputSize:defaultSize()});event.target.value='';renderImages();renderSlots();markDirty();};
$('classify-listing').onclick=()=>{classifyLegacy=true;resetSlots();renderSlots();renderMode();markDirty();};
work(async()=>{const session=document.body.dataset.sessionId;if(session){const body=await api('/api/sessions/'+encodeURIComponent(session));$('config-note').hidden=body.ai_configured;applyState(body.state,body.activity);}else{resetSlots();renderSlots();renderResults();}});

window.PreparePlan={getState:()=>state,getStatus:()=>({dirty,busy:busy||remoteBusy}),api,applyState,renderCardPlan,
  modifyTarget(action,target,feedback,expected){if(!['plan','reference'].includes(action))throw new Error('无效的计划操作。');return work(()=>runAction(action,target,feedback,expected),true);},
  confirmPlan(target){return work(()=>runAction('confirm',target));},
  setImageBusy(value){if(imageBusy!==value){imageBusy=value;updateButtons();}}};
})();
