(() => {
"use strict";
let state = null, dirty = false, busy = false;
let kept = [], pending = {product: [], reference: []};
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
function isQuick(){return $('task-mode').value==='quick_redesign';}
function renderMode(){
  const quick=isQuick();
  for(const id of ['listing-field','description-field','understanding-section','planning-controls'])$(id).hidden=quick;
  $('redesign-fields').hidden=!quick;$('load-case').hidden=quick;
  $('mode-note').textContent=quick?'每张原图独立重设计；风格参考可选。Amazon 商业信息图是视觉偏好，不代表平台合规。':'商品实拍是外观依据；设计参考只提供设计方法。保存不调用 AI。';
  $('input-title').textContent=quick?'待重设计图片与整体要求':'商品资料与参考图';
  $('product-label').textContent=quick?'待重设计原图':'商品原图';
  $('reference-label').textContent=quick?'风格参考图（可选）':'设计参考图';
  $('save-inputs').textContent=state?'另存为新任务':'保存资料';
  $('input-summary').textContent=(state?.title||'新建任务')+' · '+(quick?'快速重设计':'商品图包制作');
  $('workspace-title').textContent=state?.title||'新建商品图任务';
}
function element(tag, text, className) {const e=document.createElement(tag); if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function notify(text, error=false) {$('message').textContent=text;$('message').className=error?'error':'';$('message').hidden=false;}
async function api(url, options={}) {if(readOnlyWorkspace&&!['GET','HEAD'].includes((options.method||'GET').toUpperCase()))throw new Error('匿名只读预览不能保存或修改；请进入 8013 Live Debug 工作台。');const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查本地服务是否仍在运行。');}if(!response.ok)throw new Error(body.error||'操作失败');return body;}
function updateButtons() {
  const locked=readOnlyWorkspace||busy||remoteBusy||imageBusy;
  document.querySelectorAll('#input-panel button,#input-panel input,#input-panel textarea,#input-panel select,#planning-controls button,.ai-mutation,.feedback textarea').forEach(e=>e.disabled=locked);
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
    images.forEach(image=>{const wrap=element('div',undefined,'thumb');const img=element('img');img.src=image.url;img.alt=image.name;const remove=element('button','×','remove-image');remove.type='button';remove.setAttribute('aria-label','移除 '+image.name);remove.onclick=()=>{if(image.existing)kept=kept.filter(i=>i.id!==image.id);else{pending[role]=pending[role].filter(i=>i!==image);URL.revokeObjectURL(image.url);}renderImages();markDirty();};wrap.append(img,remove,element('small',image.name));container.append(wrap);});
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
function renderResults(){
  renderMode();const ready=Boolean(state?.product);$('understanding-empty').hidden=ready;
  const product=$('product-understanding');product.hidden=!ready;product.replaceChildren();
  if(ready)product.append(describe(state.product,productFields),feedbackBox('product',null,'修正商品理解','根据意见修正理解'));
  const plans=Object.values(state?.plan_status||{}),confirmed=plans.filter(p=>p.confirmed).length;
  $('confirmation-title').textContent=state?.product?`本图计划逐张确认 · 已确认 ${confirmed} / ${plans.length} 张`:'先保存资料，再主动执行 AI 理解与规划';
  $('confirmation-note').textContent=state?.stale_plans.length?'理解已修正，请更新受影响计划后逐张确认；其他有效确认和旧成图保留。':'在对应卡片点击「确认本图计划」后即可单独生成。修改本张计划只撤销本图确认，不自动批量确认。';
  updateButtons();
}
function applyState(value,activity=null){if(state?.id!==value.id)feedbackDrafts.clear();state=value;dirty=false;window.history.replaceState(null,'','/workspace/'+state.id);$('task-mode').value=state.mode||'product_pack';$('task-title').value=state.title;releasePending();kept=state.images.map(i=>({...i}));for(const key of ['listing','description','requirements','product_facts'])$(key).value=state.inputs[key]||'';$('output-size').value=state.output_size||'1024x1536';$('product-files').value='';$('reference-files').value='';$('saved-status').textContent=isQuick()?'重设计资料已保存':state.confirmed?'计划已确认':'资料与修改已保存';$('input-note').textContent=state.title+' · 当前任务已保存，刷新后可恢复。';
  remoteBusy=activity?.status==='RUNNING';clearTimeout(progressPoll);
  if(activity){operation={...activity,fromSaved:true,name:actionNames[activity.action]||'AI 操作',status:activity.status==='AI_RESULT_RECEIVED'?'SUCCEEDED':activity.status};drawProgress();}
  if(remoteBusy)progressPoll=setTimeout(async()=>{try{const body=await api('/api/sessions/'+state.id);const active=body.activity;if(active?.status!=='RUNNING'){operation={...active,name:actionNames[active?.action]||'AI 操作',status:active?.status==='AI_RESULT_RECEIVED'?'SUCCEEDED':active?.status||'FAILED'};drawProgress();}applyState(body.state,body.activity);}catch(error){notify('状态读取失败：'+error.message+'；未自动重试模型请求。',true);}},2000);
  renderImages();renderResults();window.dispatchEvent?.(new CustomEvent('workspace:task-changed',{detail:{task_id:state.id}}));}
async function saveInputs(){
  const data=new FormData();for(const key of ['listing','description','requirements'])data.append(key,$(key).value);
  data.append('mode',$('task-mode').value);
  if(isQuick()){data.append('product_facts',$('product_facts').value);data.append('output_size',$('output-size').value);}
  data.append('title',$('task-title').value);
  if(state){data.append('from_session',state.id);data.append('keep_images',JSON.stringify(kept.map(i=>i.id)));}
  for(const role of ['product','reference'])pending[role].forEach(item=>data.append(role,item.file,item.file.name));
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
$('task-mode').onchange=()=>{if(isQuick()&&!$('requirements').value.trim())$('requirements').value=redesignDefault;renderMode();markDirty();};
for(const role of ['product','reference'])$(role+'-files').onchange=event=>{for(const file of event.target.files)pending[role].push({file,name:file.name,url:URL.createObjectURL(file),role});event.target.value='';renderImages();markDirty();};
work(async()=>{const session=document.body.dataset.sessionId;if(session){const body=await api('/api/sessions/'+encodeURIComponent(session));$('config-note').hidden=body.ai_configured;applyState(body.state,body.activity);}else renderResults();});

window.PreparePlan={getState:()=>state,getStatus:()=>({dirty,busy:busy||remoteBusy}),api,applyState,renderCardPlan,
  modifyTarget(action,target,feedback,expected){if(!['plan','reference'].includes(action))throw new Error('无效的计划操作。');return work(()=>runAction(action,target,feedback,expected),true);},
  confirmPlan(target){return work(()=>runAction('confirm',target));},
  setImageBusy(value){if(imageBusy!==value){imageBusy=value;updateButtons();}}};
})();
