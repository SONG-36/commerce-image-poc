"use strict";
let state = null, dirty = false, busy = false;
let kept = [], pending = {product: [], reference: []};
const $ = id => document.getElementById(id);
const productFields = {identity:"商品识别", claims:"Listing 声称 · 待核验", appearance:"实拍外观 · 候选识别", uncertainties:"冲突与待确认"};
const referenceFields = {style:"视觉风格", composition:"构图方式", layout:"信息布局", expression:"视觉表达", applicable:"可借鉴的方法", risks:"边界与待确认"};
const planFields = {goal:"表达目标", selling_points:"主要卖点", design:"设计与构图", scene_style:"场景与风格", risks:"风险与待确认"};
function element(tag, text, className) {const e=document.createElement(tag); if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function notify(text, error=false) {$('message').textContent=text;$('message').className=error?'error':'';$('message').hidden=false;}
async function api(url, options={}) {const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查本地服务是否仍在运行。');}if(!response.ok)throw new Error(body.error||'操作失败');return body;}
function updateButtons() {
  document.querySelectorAll('button,input[type=file],#input-form textarea').forEach(e=>e.disabled=busy);
  $('understand').disabled=busy||Boolean(state?.product&&!dirty);
  $('replan').disabled=busy||!state?.product||dirty;
  $('confirm').disabled=busy||!state?.product||dirty||Boolean(state?.stale_plans.length)||state?.confirmed;
  document.querySelectorAll('.ai-mutation').forEach(e=>e.disabled=busy||dirty);
  document.body.classList.toggle('busy',busy);
}
async function work(fn) {if(busy)return;busy=true;updateButtons();try{await fn();}catch(error){notify(error.message,true);}finally{busy=false;updateButtons();}}
function markDirty(){dirty=true;$('input-note').textContent='资料有修改。保存为新任务后重新理解与规划，旧任务保留。';updateButtons();}
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
function history(target, action){
  const events=(state?.events||[]).filter(event=>event.action===action&&event.target===target);
  const box=element('details',undefined,'history');box.append(element('summary',`修改记录（${events.length}）`));
  events.forEach(event=>{const row=element('div',undefined,'history-item');row.append(element('small',new Date(event.at).toLocaleString('zh-CN')),element('p','意见：'+event.feedback));
    if(event.before){const previous=element('details');previous.append(element('summary','查看修改前内容'));const labels=action==='plan'?planFields:action==='product'?productFields:referenceFields;previous.append(describe(event.before,labels));row.append(previous);}box.append(row);});return box;
}
function feedbackBox(action,target,label,buttonText){
  const box=element('div',undefined,'feedback');const id='feedback-'+action+'-'+(target||'product');
  const lab=element('label',label);lab.htmlFor=id;const row=element('div',undefined,'row');const input=element('textarea');input.id=id;input.rows=2;input.maxLength=12000;input.placeholder=action==='plan'?'例如：不要展示配件，采用浅粉色背景。':action==='product'?'例如：这不是冲击电钻，不要强调冲击功能。':'例如：只参考信息排版，不参考产品使用场景。';
  const button=element('button',buttonText,'secondary ai-mutation');button.type='button';button.onclick=()=>{if(!input.value.trim()){notify('请先填写修改意见。',true);return;}work(()=>runAction(action,target,input.value));};row.append(input,button);box.append(lab,row,history(target,action));return box;
}
function renderResults(){
  const ready=Boolean(state?.product);$('understanding-empty').hidden=ready;$('understanding-content').hidden=!ready;
  const products=$('product-understanding'),refs=$('reference-understandings'),plans=$('plans');products.replaceChildren();refs.replaceChildren();plans.replaceChildren();
  if(ready){
    products.append(element('h3','商品理解'),describe(state.product,productFields),feedbackBox('product',null,'修正商品理解','根据意见修正理解'));
    state.images.filter(i=>i.role==='reference').forEach((image,index)=>{
      const article=element('article',undefined,'understanding-card');const top=element('div',undefined,'reference-top');const thumbnail=element('img');thumbnail.src=image.url;thumbnail.alt=image.name;const text=element('div');text.append(element('h3',`参考图 ${index+1} · ${image.name}`),describe(state.references[image.id],referenceFields));top.append(thumbnail,text);article.append(top,feedbackBox('reference',image.id,'修正这张参考图的理解','根据意见修正理解'));refs.append(article);
      const plan=state.plans[image.id];if(!plan)return;const card=element('article',undefined,'plan-card');card.dataset.planId=image.id;const heading=element('div',undefined,'plan-heading');const img=element('img');img.src=image.url;img.alt=`计划 ${index+1} 的参考图`;const label=element('div');label.append(element('h3',`图片 ${index+1} 的制作计划`));label.append(element('span',state.stale_plans.includes(image.id)?'理解已修正，计划待更新':'候选计划',state.stale_plans.includes(image.id)?'stale':'muted'));heading.append(img,label);card.append(heading,describe(plan,planFields),feedbackBox('plan',image.id,'本张计划的修改意见','根据意见修改计划'));plans.append(card);
    });
  }
  const count=Object.keys(state?.plans||{}).length;$('plan-count').textContent=count?count+' 张':'';$('plans-empty').hidden=count>0;
  $('confirmation-title').textContent=state?.confirmed?'出图计划已保存，可进入图片生成阶段。':'确认整套当前计划';$('confirmation-title').className=state?.confirmed?'confirmed':'';
  $('confirmation-note').textContent=state?.confirmed?'本次已保存计划。图片生成阶段尚未开发，未生成任何新图片。':state?.stale_plans.length?'请先让计划采用修正后的理解，再确认整套计划。':'计划确认后保存在本地，刷新页面可继续查看。';
  updateButtons();
}
function applyState(value){state=value;dirty=false;releasePending();kept=state.images.map(i=>({...i}));for(const key of ['listing','description','requirements'])$(key).value=state.inputs[key];$('product-files').value='';$('reference-files').value='';$('saved-status').textContent=state.confirmed?'计划已确认':'资料与修改已保存';$('input-note').textContent=state.title+' · 当前任务已保存，刷新后可恢复。';renderImages();renderResults();}
async function saveInputs(){
  const data=new FormData();for(const key of ['listing','description','requirements'])data.append(key,$(key).value);
  if(state){data.append('from_session',state.id);data.append('keep_images',JSON.stringify(kept.map(i=>i.id)));}
  for(const role of ['product','reference'])pending[role].forEach(item=>data.append(role,item.file,item.file.name));
  const body=await api('/api/sessions',{method:'POST',body:data});applyState(body.state);
}
async function runAction(action,target=null,feedback=''){
  if(dirty)throw new Error('资料有修改，请先保存为新任务，再进行 AI 理解与规划。');
  if(!state)throw new Error('请先加载或保存商品资料。');
  notify('AI 正在处理，请稍候。不会自动重试。');
  const body=await api(`/api/sessions/${state.id}/action`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,target,feedback,revision:state.revision})});
  const drafts=[...document.querySelectorAll('.feedback textarea')].map(input=>({id:input.id,value:input.value}));
  applyState(body.state);
  const cleared='feedback-'+action+'-'+(target||'product');
  drafts.forEach(draft=>{if(draft.id!==cleared&&$(draft.id))$(draft.id).value=draft.value;});
  notify(action==='confirm'?'出图计划已保存，可进入图片生成阶段。':action==='plan'?'本张计划已更新，其他计划保持不变。':action==='product'||action==='reference'?'理解已修正。后续规划将使用修正结果，已有计划请显式更新后再确认。':'AI 理解与规划已保存，请检查候选结果。');
}
$('load-case').onclick=()=>work(async()=>{const body=await api('/api/case-001',{method:'POST'});applyState(body.state);notify('case-001 已加载为独立资料副本，未调用 AI。');});
$('input-form').onsubmit=event=>{event.preventDefault();work(async()=>{await saveInputs();notify('资料已保存为新任务，旧任务未覆盖。');});};
$('understand').onclick=()=>work(async()=>{if(dirty||!state)await saveInputs();await runAction('understand');});
$('replan').onclick=()=>work(()=>runAction('replan'));
$('confirm').onclick=()=>work(()=>runAction('confirm'));
for(const key of ['listing','description','requirements'])$(key).addEventListener('input',markDirty);
for(const role of ['product','reference'])$(role+'-files').onchange=event=>{for(const file of event.target.files)pending[role].push({file,name:file.name,url:URL.createObjectURL(file),role});event.target.value='';renderImages();markDirty();};
work(async()=>{const body=await api('/api/current');$('config-note').hidden=body.ai_configured;if(body.state)applyState(body.state);else renderResults();});
