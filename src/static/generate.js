"use strict";
const sessionId=document.body.dataset.sessionId;
const node=id=>document.getElementById(id);
const running=new Set();
const drafts=new Map();
const auxiliaryDrafts=new Map();
const jobs=new Map();
let current=null,poll=null,available=true;
const labels={goal:'表达目标',selling_points:'主要卖点',design:'设计与构图',scene_style:'场景与风格',risks:'风险与待确认'};
const statuses={NOT_STARTED:'尚未生成',RUNNING:'正在生成',SUCCEEDED:'图片已生成',FAILED:'本次生成失败',INTERRUPTED:'执行状态待确认'};
function el(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function message(text,error=false){node('generation-message').hidden=false;node('generation-message').textContent=text;node('generation-message').className=error?'error':'';}
function clearAuxiliary(target){const draft=auxiliaryDrafts.get(target);if(draft?.url)URL.revokeObjectURL(draft.url);auxiliaryDrafts.delete(target);}
window.addEventListener('pagehide',()=>{for(const target of auxiliaryDrafts.keys())clearAuxiliary(target);});
window.addEventListener('pageshow',event=>{if(event.persisted)render();});
function auxiliaryControls(card,index,disabled){
  const draft=auxiliaryDrafts.get(card.id),box=el('div',undefined,'auxiliary-controls');
  const label=el('label','辅助参考图片（可选，每次最多一张）');const input=el('input');input.type='file';input.accept='image/jpeg,image/png,image/webp';input.setAttribute('aria-label',`图片 ${index+1} 的辅助参考图片`);input.disabled=disabled;label.append(input);box.append(label);
  input.onchange=()=>{const file=input.files[0];if(!file)return;if(input.files.length>1||file.size>current.auxiliary_max_bytes||file.type&&!['image/jpeg','image/png','image/webp'].includes(file.type)){message('每次只可上传一张 JPG、PNG 或 WebP，且不超过 20 MB。',true);input.value='';return;}clearAuxiliary(card.id);auxiliaryDrafts.set(card.id,{file,url:URL.createObjectURL(file),purpose:''});render();};
  const purposeLabel=el('label','图片用途');const purpose=el('select');purpose.setAttribute('aria-label',`图片 ${index+1} 的辅助图片用途`);const empty=el('option','请选择本次图片用途');empty.value='';purpose.append(empty);
  for(const [value,name] of Object.entries(current.auxiliary_purposes)){const option=el('option',name);option.value=value;purpose.append(option);}
  purpose.value=draft?.purpose||'';purpose.disabled=disabled||!draft?.file;purpose.onchange=()=>{draft.purpose=purpose.value;};purposeLabel.append(purpose);box.append(purposeLabel);
  if(draft?.file){const preview=el('div',undefined,'auxiliary-preview');const image=el('img');image.src=draft.url;image.alt='本次辅助参考图片预览';const remove=el('button','移除辅助图','secondary');remove.type='button';remove.disabled=disabled;remove.onclick=()=>{clearAuxiliary(card.id);render();};preview.append(image,el('span',draft.file.name),remove);box.append(preview);}
  box.append(el('p','仅用于当前图片的本次修改；外观修正请提供同一 SKU 的照片。上传和用途不代表商品事实已核验；辅助图不自动加入全局资料或以后修改。','muted'));
  return box;
}
async function api(url,options={}){const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查本地服务。');}if(!response.ok)throw new Error(body.error||'操作失败');return body;}
function render(){
  const container=node('generation-cards');container.replaceChildren();
  if(!current)return;
  const quick=current.mode==='quick_redesign';
  node('prepare-nav').textContent=quick?'01 原图与要求':'01 准备与规划';
  node('prepare-link').textContent=quick?'查看原图与要求':'返回准备与规划';
  const completed=current.cards.filter(card=>card.versions.length).length,passed=current.cards.filter(card=>card.passed_run).length;
  node('task-summary').textContent=`${current.title} · 已生成 ${completed} / ${current.cards.length} 张 · 已 Pass ${passed} 张`;
  current.cards.forEach((card,index)=>{
    const article=el('article',undefined,'generation-card');article.dataset.cardId=card.id;
    const heading=el('div',undefined,'plan-heading');const reference=el('img');reference.src=card.reference.url;reference.alt=`图片 ${index+1} 的${quick?'原始图片':'设计参考图'}`;const title=el('div');title.append(el('h3',`图片 ${index+1}${quick?' · 快速重设计':''}`),el('span',(quick?'原图：':'对应参考：')+card.reference.name,'muted'));heading.append(reference,title);
    const details=el('details',undefined,'history');details.open=!quick;details.append(el('summary',quick?'查看整体要求、商品依据与风格参考':'已确认制作计划'));
    const definition=el('dl',undefined,'details');
    if(quick){definition.append(el('dt','整体设计要求'),el('dd',card.requirements),el('dt','商品事实说明'),el('dd',card.product_facts||'未提供，不补充未经确认的宣称'),el('dt','输出尺寸'),el('dd',card.output_size));details.append(definition);for(const style of card.style_references){const img=el('img');img.src=style.url;img.alt='仅设计风格参考：'+style.name;img.width=120;details.append(img);}details.append(el('p','Amazon 风格是视觉偏好，不代表平台合规认证。','muted'));}
    else{for(const [key,label] of Object.entries(labels))definition.append(el('dt',label),el('dd',card.plan[key]));details.append(definition);}
    const result=el('div',undefined,'image-result');
    const selected=card.versions.find(v=>v.run_id===card.selected_run),accepted=card.versions.find(v=>v.run_id===card.passed_run);
    if(card.image_url){const image=el('img');image.src=card.image_url;image.alt=`图片 ${index+1} 的生成结果`;result.append(image,el('p',`当前查看 V${selected?.version||1} · ${card.passed_run===card.selected_run?'已 Pass':'待审核'}${accepted&&card.passed_run!==card.selected_run?` · 导出仍使用已 Pass 的 V${accepted.version}`:''}`,'image-caption'));}
    else result.append(el('p','尚无生成图片。点击下方按钮后，这里展示实际返回的图片。'));
    const status=running.has(card.id)?'RUNNING':card.status;
    const actions=el('div',undefined,'generation-actions');const badge=el('span',jobs.get(card.id)?.name||statuses[status]||'状态待确认','generation-status'+(status==='SUCCEEDED'?' success':status==='FAILED'||status==='INTERRUPTED'?' failed':''));
    const button=el('button','生成图片','primary');button.disabled=status==='RUNNING'||!available;button.onclick=()=>generateOne(card.id);actions.append(badge,button);
    article.append(heading,details,result);
    if(card.error&&!running.has(card.id))article.append(el('div',card.error+(card.api_call_attempted?'；服务端执行或计费需核对，未自动重试。':''),'generation-error'));
    if(status==='INTERRUPTED')article.append(el('p','服务曾中断，远端调用结果未确认。现有记录保留，未自动重试。','generation-error'));
    article.append(actions);container.append(article);
    const history=el('div',undefined,'version-controls');const select=el('select');select.setAttribute('aria-label',`图片 ${index+1} 的历史版本`);
    card.versions.forEach(version=>{const option=el('option',`V${version.version} · ${version.action==='revise_image'?'修改':'生成'} · ${new Date(version.created_at).toLocaleString()}`);option.value=version.run_id;select.append(option);});
    select.value=card.selected_run||'';select.disabled=running.has(card.id)||status==='RUNNING'||!card.versions.length||!available;select.onchange=()=>reviewOne(card.id,'select',select.value);
    const pass=el('button','Pass · 接受当前版本','secondary');pass.disabled=select.disabled||card.passed_run===card.selected_run;pass.onclick=()=>reviewOne(card.id,'pass',card.selected_run);
    history.append(select,pass);article.append(history);
    if(selected?.feedback)article.append(el('p','本版修改意见：'+selected.feedback,'muted'));
    if(selected?.auxiliary_reference)article.append(el('p',`本版辅助图：${selected.auxiliary_reference.purpose_label} · ${selected.auxiliary_reference.name}`,'muted'));
    const feedback=el('textarea');feedback.placeholder='描述要修改的内容，例如保留布局，将背景改为更浅的粉色…';feedback.setAttribute('aria-label',`图片 ${index+1} 的修改意见`);feedback.value=drafts.get(card.id)||'';feedback.oninput=()=>drafts.set(card.id,feedback.value);feedback.disabled=running.has(card.id)||status==='RUNNING';
    const revise=el('button','修改图片','primary');revise.disabled=select.disabled;revise.onclick=()=>generateOne(card.id,true);
    const revision=el('div',undefined,'revision-controls');revision.append(auxiliaryControls(card,index,select.disabled),feedback,revise);article.append(revision);
    if(status==='RUNNING'){const job=jobs.get(card.id);const wait=el('p',`${job?.name||'AI 操作'}正在执行 · 已等待 0 秒`,'waiting');wait.dataset.started=job?.started_at||card.started_at||new Date().toISOString();wait.dataset.operation=job?.name||(card.operation==='revise_image'?'图片修改':'图片生成');article.append(wait);}
  });
}
async function refresh(){
  current=await api(`/api/sessions/${sessionId}/generation`);available=true;render();
  clearTimeout(poll);
  if(current.cards.some(card=>card.status==='RUNNING'))poll=setTimeout(()=>refresh().catch(error=>message(error.message,true)),4000);
}
async function generateOne(target,revise=false){
  if(running.has(target)||!current)return;
  const card=current.cards.find(card=>card.id===target),feedback=drafts.get(target)||'';
  if(revise&&!feedback.trim()){message('请先填写本次修改意见。',true);return;}
  const auxiliary=revise?auxiliaryDrafts.get(target):null;
  if(auxiliary?.file&&!current.auxiliary_purposes[auxiliary.purpose]){message('请选择本次辅助图片的用途。',true);return;}
  const revision=current.confirmed_revision;
  running.add(target);jobs.set(target,{started_at:new Date().toISOString(),name:revise?'图片修改':'图片生成'});render();
  try{
    const operation_id=crypto.randomUUID().replaceAll('-','');
    const payload={confirmed_revision:revision,card_revision:card.card_revision,operation_id,...(revise?{parent_run_id:card.selected_run,feedback}:{})};
    let options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
    if(auxiliary?.file){const data=new FormData();for(const [key,value] of Object.entries(payload))data.append(key,String(value));data.append('auxiliary_purpose',auxiliary.purpose);data.append('auxiliary',auxiliary.file,auxiliary.file.name);options={method:'POST',body:data};}
    const result=await api(`/api/sessions/${sessionId}/${revise?'revise':'generate'}/${target}`,options);
    if(revise){drafts.delete(target);clearAuxiliary(target);}
    message(revise?'本张图片的新版本已保存，等待人工审核；原图及已 Pass 版本保留。':'本张图片已生成并保存；其他图片未改动。');
    if(result.confirmed_revision!==revision)message('计划版本已改变，结果保留在原版本中。',true);
  }catch(error){message(error.message+' 若请求已发出，服务端执行与费用需核对；本页不会自动重试。',true);}
  finally{
    running.delete(target);
    jobs.delete(target);
    try{await refresh();if(current.confirmed_revision!==revision)message('计划版本已改变，本次生成记录保留在原版本中。',true);}catch(error){available=false;render();message(error.message,true);node('task-summary').textContent='当前状态无法确认，保留已显示结果；请刷新或返回第一页检查。';}
  }
}
async function reviewOne(target,action,run_id){
  if(running.has(target))return;const card=current.cards.find(card=>card.id===target);running.add(target);jobs.set(target,{started_at:new Date().toISOString(),name:action==='pass'?'记录人工审核':'选择版本'});render();
  try{await api(`/api/sessions/${sessionId}/review/${target}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_revision:current.confirmed_revision,card_revision:card.card_revision,action,run_id})});message(action==='pass'?'当前指定版本已记录为人工 Pass。':'已切换查看版本，原有 Pass 版本未替换。');}
  catch(error){message(error.message,true);}
  finally{running.delete(target);jobs.delete(target);try{await refresh();}catch(error){available=false;render();message(error.message,true);}}
}
async function downloadPackage(kind){
  const button=node('export-'+kind);if(button.disabled)return;button.disabled=true;const label=button.textContent;button.textContent='正在打包…';
  try{
    const response=await fetch(`/api/sessions/${sessionId}/export-${kind}`,{method:'POST',headers:{'X-Local-Action':'prepare-plan'}});
    if(!response.ok){const body=await response.json();throw new Error(body.error||'实验包导出失败');}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');
    const filename=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/);
    link.href=url;link.download=filename?filename[1]:'experiment.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
    message(kind==='passed'?'已通过图片包已交给浏览器下载。':'实验包已交给浏览器下载；未调用 AI。');
  }catch(error){message('导出失败：'+error.message,true);}
  finally{button.disabled=false;button.textContent=label;}
}
node('export-experiment').onclick=()=>downloadPackage('experiment');
node('export-passed').onclick=()=>downloadPackage('passed');
setInterval(()=>document.querySelectorAll('.waiting').forEach(e=>{const seconds=Math.max(0,Math.floor((Date.now()-Date.parse(e.dataset.started))/1000));e.textContent=`${e.dataset.operation}正在执行 · 已等待 ${seconds} 秒；不确定进度，未自动重试。`;}),1000);
refresh().catch(error=>{message(error.message,true);node('task-summary').textContent='请返回第一页确认整套当前计划。';});
