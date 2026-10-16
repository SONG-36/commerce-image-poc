(() => {
"use strict";
let sessionId=document.body.dataset.sessionId,current=null,poll=null,available=true;
let presentation={blocked:true},selectedTarget=null,localPlanning=false,rendering=false,renderAgain=false;
let batch=null,batchTask=null,batchStorageError=false,pageActive=true,lastOperation=null;
const node=id=>document.getElementById(id),batchRunner=window.ImageBatchRunner;
const running=new Set(),jobs=new Map(),drafts=new Map(),choices=new Map(),selections=new Map();
const statuses={NOT_STARTED:'尚未生成',RUNNING:'正在执行',SUCCEEDED:'图片已生成',FAILED:'本次操作失败',INTERRUPTED:'执行状态待确认'};
const actionNames={image:'修改图片',plan:'修改计划',reference:'修正参考理解',generate:'生成图片',select:'选择版本',pass:'人工 Pass'};
const key=(task,target)=>JSON.stringify([task,target]);
const draftKey=(task,target,action)=>JSON.stringify([task,target,action]);
const batchKey=id=>'commerce:image-batch:'+id;
const el=(tag,text,className)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
const imageNumber=target=>'#'+String((current?.cards.findIndex(c=>c.id===target)??-1)+1).padStart(2,'0');
const selectedCard=()=>current?.cards.find(c=>c.id===selectedTarget);
const displayStatus=card=>running.has(key(sessionId,card.id))?'RUNNING':card.status;
const imageBusy=()=>running.size>0||Boolean(current?.cards.some(c=>c.status==='RUNNING'))||batch?.status==='RUNNING';
const mutationBusy=()=>imageBusy()||localPlanning||window.PreparePlan.getStatus().busy;
function message(text,error=false,task=sessionId){if(task!==sessionId)return;node('generation-message').hidden=false;node('generation-message').textContent=text;node('generation-message').className=error?'error':'';}
async function api(url,options={}){
  const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});
  let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查连接并查询原请求，不要直接重发。');}
  if(!response.ok)throw new Error(body.error||'操作失败');return body;
}
async function refreshFor(task){if(task===sessionId&&window.PreparePlan.getState()?.id===task)return window.Workspace.refresh();}
function selectedVersion(card){return card.versions.find(v=>v.run_id===card.selected_run);}
function versionLabel(card){const v=selectedVersion(card);return v?'V'+v.version:'未生成';}
function actionFor(card){
  const saved=choices.get(key(sessionId,card.id));
  if(current.mode==='quick_redesign')return 'image';
  return saved|| (card.image_url?'image':'plan');
}
function baseFor(card,action){
  const state=window.PreparePlan.getState();
  return action==='image'?{revision:card.generation_revision,run:card.selected_run||null}:
    {plan:state.plan_status?.[card.id]?.plan_version||0,product:state.product_version,
      reference:state.reference_versions[card.id]||0};
}
function hasContent(draft){return Boolean(draft.text||draft.file);}
function draftFor(card,action){
  const id=draftKey(sessionId,card.id,action),base=baseFor(card,action);
  let draft=drafts.get(id);
  if(!draft){draft={text:'',file:null,url:null,purpose:'',serial:0,base};drafts.set(id,draft);}
  if(!hasContent(draft))draft.base=base;
  return draft;
}
function matchesBase(card,action,draft){return JSON.stringify(draft.base)===JSON.stringify(baseFor(card,action));}
function releaseFile(draft){if(draft.url)URL.revokeObjectURL(draft.url);draft.file=null;draft.url=null;draft.purpose='';}
function clearSubmitted(op){
  if(!op.draftKey)return;
  const draft=drafts.get(op.draftKey);
  if(draft?.serial===op.draftSerial){releaseFile(draft);drafts.delete(op.draftKey);}
}
function chooseImage(target){
  if(!current?.cards.some(c=>c.id===target))return;
  selectedTarget=target;selections.set(sessionId,target);
  try{sessionStorage.setItem('commerce:selected-image:'+sessionId,target);}catch{}
  render();
}
function chooseAction(action){const card=selectedCard();if(!card)return;choices.set(key(sessionId,card.id),action);render();}
function showLarge(url,label){
  node('viewer-image').src=url;node('viewer-image').alt=label;
  node('image-viewer').showModal();
}
node('close-image-viewer').onclick=()=>node('image-viewer').close();
function persistBatch(value){sessionStorage.setItem(batchKey(value.session_id),JSON.stringify(value));}
function loadBatch(id){
  if(batchTask===id)return;batchTask=id;batchStorageError=false;
  try{batch=batchRunner.restore(sessionStorage.getItem(batchKey(id)));if(batch)persistBatch(batch);}
  catch{batch=null;batchStorageError=true;}
}
function renderBatch(processing=false){
  const eligible=current?.cards.filter(c=>c.batch_eligible)||[],quick=current?.mode==='quick_redesign';
  const button=node('batch-generate');button.textContent=(quick?'一键生成尚未生成图片':'一键生成已确认图片')+'（'+eligible.length+' 张）';
  button.disabled=!eligible.length||processing||presentation.blocked||!available||batchStorageError||batchRunner.unresolved(batch);
  node('batch-count').textContent=batchStorageError?'浏览器无法读取批次记录，已禁用批量；请先人工核对。':'跳过已生成、已 Pass、曾尝试或状态待确认的图片；顺序执行，不自动重试。';
  const progress=node('batch-progress');progress.hidden=!batch;
  if(batch){
    const done=batch.items.filter(i=>['SUCCEEDED','FAILED'].includes(i.status)).length,success=batch.items.filter(i=>i.status==='SUCCEEDED').length;
    progress.textContent=(batch.status==='RUNNING'?'批量生成中':batch.status==='FINISHED'?'批次已结束':'批次已暂停')+' · 已完成 '+done+' / '+batch.items.length+' 张 · 成功 '+success+' · 失败 '+(done-success)+'。'+(batch.reason||'');
  }
  node('check-batch').hidden=!batchRunner.unresolved(batch);node('check-batch').disabled=processing||presentation.blocked;
}
function renderChoices(){
  const grid=node('generation-cards');grid.replaceChildren();
  current.cards.forEach((card,index)=>{
    const button=el('button',undefined,'image-choice'+(card.id===selectedTarget?' selected':''));
    button.type='button';button.dataset.cardId=card.id;button.dataset.passed=String(card.has_passed_history);button.dataset.status=displayStatus(card);button.setAttribute('aria-pressed',String(card.id===selectedTarget));
    button.setAttribute('aria-label','选择图片 #'+String(index+1).padStart(2,'0'));
    const image=el('img');image.src=card.image_url||card.reference.url;image.alt=card.image_url?'已保存的生成图缩略图':'尚未生成，显示参考或原图';
    const badge=card.has_passed_history?'已有 Pass':'待审核';
    button.append(image,el('strong','#'+String(index+1).padStart(2,'0')+' · '+versionLabel(card)),
      el('span',statuses[displayStatus(card)]||'状态待确认'),el('small',badge+(card.passed_run&&card.passed_run!==card.selected_run?' · 查看其他版本':'')));
    button.onclick=()=>chooseImage(card.id);grid.append(button);
  });
}
function renderHistory(card){
  const records=node('interaction-records');records.replaceChildren();
  const state=window.PreparePlan.getState(),rows=[];
  for(const event of state.events||[]){
    if(event.target!==card.id||!['plan','reference','confirm'].includes(event.action))continue;
    rows.push({at:event.at,label:event.action==='confirm'?'确认本图计划':actionNames[event.action],text:event.feedback||'已保存对应计划确认。'});
  }
  for(const version of card.versions){
    const parent=card.versions.find(v=>v.run_id===version.parent_run_id);
    rows.push({at:version.created_at,label:(version.action==='revise_image'?'图片修改':'图片生成')+' → V'+version.version,
      text:(parent?'基于 V'+parent.version+'。':'')+(version.feedback||'已保存图片。')+
        (version.auxiliary_reference?' 辅助图：'+version.auxiliary_reference.purpose_label+' · '+version.auxiliary_reference.name:'')});
  }
  rows.sort((a,b)=>String(a.at).localeCompare(String(b.at)));
  for(const row of rows){const item=el('div',undefined,'history-item');item.append(el('strong',row.label),el('small',row.at?new Date(row.at).toLocaleString():''),el('p',row.text));records.append(item);}
  const accepted=card.versions.find(v=>v.run_id===card.passed_run);
  if(accepted)records.append(el('p','当前已 Pass：V'+accepted.version+'；查看其他版本不会改变该审核结果。','muted'));
  else if(card.accepted_result)records.append(el('p','另一个确认计划版本已有 Pass，最终导出继续保留该版本。','muted'));
  if(card.error)records.append(el('p','最近一次错误：'+card.error+'；失败的完整历史未通过此列表提供。','generation-error'));
  if(!rows.length&&!card.error)records.append(el('p','当前没有可展示的已保存操作记录。','muted'));
}
function renderDetail(card){
  node('selected-image-title').textContent='当前图片 '+imageNumber(card.id);
  const box=node('selected-image-detail');box.replaceChildren();
  const image=el('img');image.src=card.image_url||card.reference.url;image.alt=card.image_url?'当前选中的生成图片':'尚未生成，显示对应参考或原图';image.className='selected-result';
  const large=el('button','查看大图','secondary');large.type='button';large.onclick=()=>showLarge(image.src,image.alt);
  box.append(image,large,el('p','当前版本：'+versionLabel(card)+' · '+(statuses[displayStatus(card)]||'状态待确认')+
    (card.passed_run===card.selected_run&&card.selected_run?' · 已 Pass':' · 当前版本未 Pass'),'image-caption'));
  const source=el('details',undefined,'history');source.append(el('summary',current.mode==='quick_redesign'?'查看原始待重设计图片':'查看对应设计参考图'));
  const reference=el('img');reference.src=card.reference.url;reference.alt=card.reference.name;reference.className='reference-preview';
  const sourceLarge=el('button','查看参考大图','secondary');sourceLarge.onclick=()=>showLarge(reference.src,reference.alt);
  source.append(reference,el('p',card.reference.name,'muted'),sourceLarge);box.append(source);
  const state=window.PreparePlan.getState(),quick=current.mode==='quick_redesign';
  if(!quick){
    const plan=state.plans[card.id];if(plan)box.append(el('p','计划摘要：'+plan.goal,'plan-summary'));
    const details=window.PreparePlan.renderCardPlan(card,false);details.open=false;box.append(details);
    if(state.references[card.id]){const correction=el('button','修正本图参考理解','secondary');correction.onclick=()=>chooseAction('reference');box.append(correction);}
  }else{
    const details=el('details',undefined,'history');details.append(el('summary','查看整体要求和商品依据'),el('p',card.requirements),
      el('p',card.product_facts||'未提供额外商品事实说明。'),el('p','Amazon 风格仅为设计偏好，不代表平台合规认证。','muted'));
    for(const style of card.style_references){const img=el('img');img.src=style.url;img.alt='仅设计风格参考：'+style.name;img.width=120;details.append(img);}box.append(details);
  }
  if(card.historical_generation)box.append(el('p','旧确认计划的成图仅供查看；请确认本图最新计划后再生成。','notice'));
  if(card.previous_result){const old=el('details',undefined,'history');old.append(el('summary','上一确认计划的历史成图（只读）'));const img=el('img');img.src=card.previous_result.image_url;img.alt='上一确认计划的成图';img.className='previous-image';old.append(img);box.append(old);}
  if(card.accepted_result&&card.accepted_result.revision!==card.confirmed_revision)box.append(el('p','最终导出继续使用先前明确 Pass 的版本，不被当前未通过图片替换。','muted'));
  if(card.error)box.append(el('p',card.error+(card.request_uncertain?'；执行或计费仍不确定，请人工核对，未自动重试。':''),'generation-error'));
  if(card.status==='INTERRUPTED')box.append(el('p','服务曾中断，远端执行结果待核对；现有成图保留，不自动重发。','generation-error'));
  const controls=el('div',undefined,'generation-actions'),busy=mutationBusy(),blocked=presentation.blocked||!available;
  if(!quick){
    const confirm=el('button',card.plan_status?.confirmed?'本图计划已确认':'确认本图计划','secondary');
    confirm.disabled=busy||blocked||card.plan_status?.confirmed||!state.plans[card.id]||state.stale_plans.includes(card.id);
    confirm.onclick=()=>window.PreparePlan.confirmPlan(card.id);controls.append(confirm);
  }
  const generate=el('button','生成图片','primary');
  generate.disabled=busy||blocked||!card.generation_allowed||card.request_uncertain;
  generate.onclick=()=>generateOne(card.id);controls.append(generate);box.append(controls);
  const history=el('div',undefined,'version-controls'),select=el('select');select.setAttribute('aria-label','当前图片的历史版本');
  card.versions.forEach(version=>{const option=el('option','V'+version.version+' · '+(version.action==='revise_image'?'修改':'生成'));option.value=version.run_id;select.append(option);});
  select.value=card.selected_run||'';select.disabled=!card.versions.length||busy||!available;
  const readOnly=!card.generation_allowed||card.historical_generation||blocked||card.request_uncertain;
  select.onchange=()=>{if(readOnly){card.selected_run=select.value;card.image_url=card.versions.find(v=>v.run_id===select.value).url;render();}else reviewOne(card.id,'select',select.value);};
  const pass=el('button','Pass · 接受当前版本','secondary');pass.disabled=select.disabled||readOnly||card.passed_run===card.selected_run;
  pass.onclick=()=>reviewOne(card.id,'pass',card.selected_run);history.append(select,pass);box.append(history);
  if(card.status==='RUNNING'){
    const wait=el('p','图片操作正在执行','waiting');wait.dataset.started=card.started_at;wait.dataset.operation=card.operation==='revise_image'?'图片修改':'图片生成';box.append(wait);
  }
}
function renderComposer(card){
  const action=actionFor(card),draft=draftFor(card,action),state=window.PreparePlan.getState(),select=node('edit-action');
  select.replaceChildren();
  const options=current.mode==='quick_redesign'?[['image','修改图片']]:[['plan','修改计划'],['image','修改图片'],...(state.references[card.id]?[['reference','修正参考理解']]:[])];
  for(const [value,label] of options){const option=el('option',label);option.value=value;select.append(option);}select.value=action;
  node('edit-target').textContent='Task ID: '+sessionId+'\nImage ID: '+card.id+'（'+imageNumber(card.id)+'）\nImage Version: '+versionLabel(card)+(card.selected_run?' · Run ID: '+card.selected_run:'');
  if(node('edit-feedback').value!==draft.text)node('edit-feedback').value=draft.text;
  node('edit-feedback').disabled=false;node('edit-file').value='';
  node('edit-auxiliary').hidden=action!=='image';
  const purpose=node('edit-purpose');purpose.replaceChildren();const empty=el('option','请选择本次图片用途');empty.value='';purpose.append(empty);
  for(const [value,label] of Object.entries(current.auxiliary_purposes)){const option=el('option',label);option.value=value;purpose.append(option);}
  purpose.value=draft.purpose;purpose.disabled=!draft.file;
  node('edit-preview').hidden=!draft.file;node('edit-preview-image').src=draft.url||'';node('edit-filename').textContent=draft.file?.name||'';
  const stale=hasContent(draft)&&!matchesBase(card,action,draft);
  node('rebase-draft').hidden=!stale;node('rebase-draft').disabled=mutationBusy();
  node('draft-note').textContent=stale?'草稿基于之前的版本，内容已保留。请选回原版本，或明确将草稿用于当前版本后再发送。':
    action==='image'&&!card.selected_run?'尚未生成图片，不能执行图片修改。':action==='image'?'本次只编辑所选版本；模型不能保证所有未修改区域保持不变。':'只修改本图的'+(action==='plan'?'制作计划，完成后需重新确认。':'参考理解，受影响计划需更新并重新确认。');
  node('send-edit').textContent=action==='image'?'发送图片修改':action==='plan'?'发送计划修改':'发送参考理解修正';
  updateSend(card,action,draft);renderHistory(card);
}
function updateSend(card=selectedCard(),action=card&&actionFor(card),draft=card&&draftFor(card,action)){
  node('send-edit').disabled=!card||mutationBusy()||presentation.blocked||!available||!draft.text.trim()||!matchesBase(card,action,draft)||
    (action==='image'?(!card.selected_run||!card.generation_allowed||card.historical_generation||card.request_uncertain||Boolean(draft.file&&!current.auxiliary_purposes[draft.purpose])):
      (!window.PreparePlan.getState().product||!window.PreparePlan.getState().plans[card.id]));
}
function drawOperation(){
  const box=node('image-operation'),op=lastOperation;box.hidden=!op||op.taskId!==sessionId;
  if(!op||op.taskId!==sessionId)return;
  const seconds=Math.max(0,Math.floor(((op.finished?Date.parse(op.finished):Date.now())-Date.parse(op.started))/1000));
  const status={RUNNING:'正在执行',SUCCEEDED:'已完成',FAILED:'失败',UNCERTAIN:'结果或费用待核对'}[op.status];
  box.className=op.status==='RUNNING'?'waiting':op.status==='SUCCEEDED'?'notice':'generation-error';
  box.textContent=op.name+' · 图片 '+op.number+' · 基础版本 '+op.version+' · '+status+' · 已等待 '+seconds+' 秒'+
    (op.status==='RUNNING'?'；可查看其他图片，不会转移操作对象。':op.status==='SUCCEEDED'?'；结果已保存到原图片，当前选择保持不变。':'；已有图片保留，未自动重试。');
}
function render(){
  if(rendering){renderAgain=true;return;}rendering=true;
  try{
    if(!current)return;
    if(!current.cards.some(c=>c.id===selectedTarget))selectedTarget=null;
    renderChoices();
    node('task-summary').textContent=current.title+' · 已生成 '+current.cards.filter(c=>c.has_generated_history).length+' / '+current.cards.length+' 张 · 已 Pass '+current.cards.filter(c=>c.has_passed_history).length+' 张';
    const card=selectedCard();node('image-workspace').hidden=!card;node('select-image-note').hidden=Boolean(card);
    if(card){renderDetail(card);renderComposer(card);}else{node('edit-feedback').disabled=true;node('send-edit').disabled=true;}
    const busy=mutationBusy();
    node('export-passed').disabled=presentation.blocked||busy||!available||!current.cards.some(c=>c.has_passed_history);
    node('export-experiment').disabled=presentation.blocked||busy||!available;
    window.PreparePlan.setImageBusy(imageBusy());renderBatch(busy);drawOperation();
  }finally{rendering=false;if(renderAgain){renderAgain=false;render();}}
}
function freezeOperation(card,action,draft=null,batchItem=null){
  const state=window.PreparePlan.getState();
  return Object.freeze({taskId:sessionId,imageId:card.id,number:imageNumber(card.id),version:versionLabel(card),action,
    stateRevision:state.revision,planRevision:card.generation_revision,reviewRevision:card.confirmed_revision,planVersion:state.plan_status?.[card.id]?.plan_version||null,
    parentRunId:card.selected_run,cardRevision:card.card_revision,operationId:batchItem?.operation_id||crypto.randomUUID().replaceAll('-',''),
    feedback:draft?.text||'',file:draft?.file||null,purpose:draft?.purpose||'',
    draftKey:draft?draftKey(sessionId,card.id,action):null,draftSerial:draft?.serial,batchItem});
}
function startOperation(op){
  const job={...op,name:actionNames[op.action],started:new Date().toISOString(),status:'RUNNING'};
  lastOperation=job;return job;
}
function finishOperation(job,status){job.status=status;job.finished=new Date().toISOString();drawOperation();}
async function runImage(op){
  const jobId=key(op.taskId,op.imageId),job=startOperation(op);running.add(jobId);jobs.set(jobId,job);render();
  try{
    const payload={confirmed_revision:op.planRevision,card_revision:op.cardRevision,operation_id:op.operationId,
      ...(op.batchItem?{batch_only:true}:{}),...(op.action==='image'?{parent_run_id:op.parentRunId,feedback:op.feedback}:{})};
    let options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
    if(op.file){const data=new FormData();for(const [name,value] of Object.entries(payload))data.append(name,String(value));data.append('auxiliary_purpose',op.purpose);data.append('auxiliary',op.file,op.file.name);options={method:'POST',body:data};}
    const result=await api('/api/sessions/'+op.taskId+'/'+(op.action==='image'?'revise':'generate')+'/'+op.imageId,options);
    clearSubmitted(op);finishOperation(job,'SUCCEEDED');
    message('图片 '+op.number+' 的'+actionNames[op.action]+'已保存，其他图片及既有 Pass 未替换。',false,op.taskId);
    return result;
  }catch(error){
    finishOperation(job,'FAILED');message('图片 '+op.number+'：'+error.message+' 若请求已发出，远端执行及费用需核对，未自动重试。',true,op.taskId);throw error;
  }finally{
    running.delete(jobId);jobs.delete(jobId);
    try{await refreshFor(op.taskId);const card=current?.session_id===op.taskId&&current.cards.find(c=>c.id===op.imageId);if(job.status==='FAILED'&&card?.request_uncertain)finishOperation(job,'UNCERTAIN');}
    catch(error){if(sessionId===op.taskId){available=false;message('状态无法确认：'+error.message+'；请查询原请求，不要直接重发。',true);}}
    render();
  }
}
async function generateOne(target,revise=false,batchItem=null){
  if(revise)return sendModification();
  const card=current?.cards.find(c=>c.id===target);
  if(!card||presentation.blocked||!available||running.size||localPlanning||window.PreparePlan.getStatus().busy||
    !card.generation_allowed||card.request_uncertain||batch?.status==='RUNNING'&&!batchItem){
    if(batchItem)throw new Error('本图状态已改变，未发送模型请求。');return;
  }
  if(batchItem&&(!card.batch_eligible||batchItem.confirmed_revision!==card.generation_revision||batchItem.card_revision!==card.card_revision))throw new Error('本图不再符合已确认批次条件。');
  const op=freezeOperation(card,'generate',null,batchItem);
  try{return await runImage(op);}catch(error){if(batchItem)throw error;}
}
async function sendModification(){
  const card=selectedCard();if(!card)return;
  const action=actionFor(card),draft=draftFor(card,action);updateSend(card,action,draft);if(node('send-edit').disabled)return;
  const op=freezeOperation(card,action,draft);
  if(action==='image'){try{await runImage(op);}catch{}return;}
  const job=startOperation(op);localPlanning=true;render();
  try{
    await window.PreparePlan.modifyTarget(action,op.imageId,op.feedback,op);
    clearSubmitted(op);finishOperation(job,'SUCCEEDED');message('图片 '+op.number+' 的'+actionNames[action]+'已保存，请检查本图确认状态。',false,op.taskId);
  }catch(error){finishOperation(job,'FAILED');message('图片 '+op.number+'：'+error.message+'；未自动重试。',true,op.taskId);}
  finally{localPlanning=false;try{await refreshFor(op.taskId);}catch(error){if(sessionId===op.taskId){available=false;message(error.message,true);}}render();}
}
async function reviewOne(target,action,runId){
  const card=current?.cards.find(c=>c.id===target);if(!card||mutationBusy()||presentation.blocked||!card.generation_allowed||card.historical_generation)return;
  const op=freezeOperation(card,action),jobId=key(op.taskId,op.imageId),job=startOperation(op);running.add(jobId);render();
  try{await api('/api/sessions/'+op.taskId+'/review/'+op.imageId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_revision:op.reviewRevision,card_revision:op.cardRevision,action,run_id:runId})});finishOperation(job,'SUCCEEDED');}
  catch(error){finishOperation(job,'FAILED');message(error.message,true,op.taskId);}
  finally{running.delete(jobId);try{await refreshFor(op.taskId);}catch(error){if(sessionId===op.taskId){available=false;message(error.message,true);}}render();}
}
node('edit-action').onchange=()=>chooseAction(node('edit-action').value);
node('edit-feedback').oninput=()=>{const card=selectedCard();if(!card)return;const action=actionFor(card),draft=draftFor(card,action);draft.text=node('edit-feedback').value;draft.serial++;updateSend(card,action,draft);};
node('edit-file').onchange=()=>{
  const card=selectedCard(),file=node('edit-file').files[0];if(!card||!file||actionFor(card)!=='image')return;
  if(node('edit-file').files.length>1||file.size>current.auxiliary_max_bytes||file.type&&!['image/jpeg','image/png','image/webp'].includes(file.type)){message('每次只可上传一张 JPG、PNG 或 WebP，且不超过 20 MB。',true);node('edit-file').value='';return;}
  const draft=draftFor(card,'image');releaseFile(draft);draft.file=file;draft.url=URL.createObjectURL(file);draft.serial++;render();
};
node('edit-purpose').onchange=()=>{const card=selectedCard();if(!card)return;const draft=draftFor(card,'image');draft.purpose=node('edit-purpose').value;draft.serial++;updateSend(card,'image',draft);};
node('remove-edit-file').onclick=()=>{const card=selectedCard();if(!card)return;const draft=draftFor(card,'image');releaseFile(draft);draft.serial++;render();};
node('rebase-draft').onclick=()=>{const card=selectedCard();if(!card||mutationBusy())return;const action=actionFor(card),draft=draftFor(card,action);draft.base=baseFor(card,action);draft.serial++;render();};
node('send-edit').onclick=sendModification;
function batchPorts(){
  const id=sessionId;
  return {execute(item){if(sessionId!==id||!pageActive)throw new Error('页面或任务已切换，批次暂停。');return generateOne(item.target,false,item);},
    query(item){return api('/api/sessions/'+id+'/operations/'+item.target+'/'+item.operation_id+'?confirmed_revision='+item.confirmed_revision);},
    persist:persistBatch,update(){render();}};
}
async function startBatch(){
  if(node('batch-generate').disabled)return;
  try{
    await refreshFor(sessionId);
    const cards=current.cards.filter(c=>c.batch_eligible);
    if(!cards.length||presentation.blocked||batchRunner.unresolved(batch)||mutationBusy())return;
    if(!window.confirm('将顺序生成 '+cards.length+' 张图片，会产生 API 费用。已生成、已 Pass 和曾尝试的图片会跳过；不自动重试。是否开始？'))return;
    batch={id:crypto.randomUUID(),session_id:sessionId,status:'NEW',items:cards.map(c=>({target:c.id,confirmed_revision:c.generation_revision,card_revision:c.card_revision,operation_id:crypto.randomUUID().replaceAll('-',''),status:'PENDING'}))};
    await batchRunner.run(batch,batchPorts());
  }catch(error){if(batch){batch.status='PAUSED';batch.reason=error.message;}message('批次已停止：'+error.message+'；未自动重发。',true);}
  finally{render();}
}
node('batch-generate').onclick=startBatch;
node('check-batch').onclick=async()=>{
  if(!batch||node('check-batch').disabled)return;node('check-batch').disabled=true;
  try{await batchRunner.inspect(batch,batchPorts());await refreshFor(sessionId);}catch(error){message('查询失败：'+error.message+'；未重试模型请求。',true);}finally{render();}
};
async function downloadPackage(kind){
  const button=node('export-'+kind);if(button.disabled)return;button.disabled=true;const label=button.textContent,task=sessionId;button.textContent='正在打包…';
  try{
    const response=await fetch('/api/sessions/'+task+'/export-'+kind,{method:'POST',headers:{'X-Local-Action':'prepare-plan'}});
    if(!response.ok){const body=await response.json();throw new Error(body.error||'导出失败');}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1]||'experiment.zip';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);message('图片包已交给浏览器下载。',false,task);
  }catch(error){message('导出失败：'+error.message,true,task);}finally{button.textContent=label;render();}
}
node('export-experiment').onclick=()=>downloadPackage('experiment');node('export-passed').onclick=()=>downloadPackage('passed');
window.addEventListener('pagehide',()=>{
  pageActive=false;for(const draft of drafts.values()){if(draft.file){releaseFile(draft);draft.serial++;}}
  if(batch?.status==='RUNNING'){batch.status='PAUSED';batch.reason='页面已离开，批次暂停；返回后不会自动续跑。';try{persistBatch(batch);}catch{}}
});
window.addEventListener('pageshow',event=>{pageActive=true;if(event.persisted){batchTask=null;loadBatch(sessionId);render();}});
setInterval(()=>{
  drawOperation();
  document.querySelectorAll('#selected-image-detail .waiting').forEach(e=>{const seconds=Math.max(0,Math.floor((Date.now()-Date.parse(e.dataset.started||new Date().toISOString()))/1000));e.textContent=e.dataset.operation+'正在执行 · 已等待 '+seconds+' 秒；不确定进度，未自动重试。';});
},1000);
window.ImageGeneration={
  present(data,options){
    const changed=current?.session_id!==data.session_id;current=data;sessionId=data.session_id;presentation=options;available=true;
    if(changed){let saved=selections.get(sessionId);if(!saved){try{saved=sessionStorage.getItem('commerce:selected-image:'+sessionId);}catch{}}selectedTarget=saved||null;}
    loadBatch(sessionId);render();clearTimeout(poll);
    if(current.cards.some(c=>c.status==='RUNNING'))poll=setTimeout(()=>refreshFor(sessionId).catch(error=>message(error.message,true)),4000);
  },
  lock(){presentation.blocked=true;render();},
  clear(){current=null;selectedTarget=null;node('generation-cards').replaceChildren(el('p','保存资料后，这里展示可选择的图片。','empty'));node('image-workspace').hidden=true;node('select-image-note').hidden=false;node('send-edit').disabled=true;node('export-passed').disabled=true;node('export-experiment').disabled=true;renderBatch();},
};
})();
