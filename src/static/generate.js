"use strict";
const sessionId=document.body.dataset.sessionId;
const node=id=>document.getElementById(id);
const running=new Set();
let current=null,poll=null,available=true;
const labels={goal:'表达目标',selling_points:'主要卖点',design:'设计与构图',scene_style:'场景与风格',risks:'风险与待确认'};
const statuses={NOT_STARTED:'尚未生成',RUNNING:'正在生成',SUCCEEDED:'图片已生成',FAILED:'本次生成失败',INTERRUPTED:'执行状态待确认'};
function el(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
function message(text,error=false){node('generation-message').hidden=false;node('generation-message').textContent=text;node('generation-message').className=error?'error':'';}
async function api(url,options={}){const response=await fetch(url,{...options,headers:{'X-Local-Action':'prepare-plan',...options.headers}});let body;try{body=await response.json();}catch{throw new Error('服务未返回可读结果，请检查本地服务。');}if(!response.ok)throw new Error(body.error||'操作失败');return body;}
function render(){
  const container=node('generation-cards');container.replaceChildren();
  if(!current)return;
  node('task-summary').textContent=`${current.title} · ${current.cards.length} 张已确认计划 · 每张图片独立保存`;
  current.cards.forEach((card,index)=>{
    const article=el('article',undefined,'generation-card');article.dataset.cardId=card.id;
    const heading=el('div',undefined,'plan-heading');const reference=el('img');reference.src=card.reference.url;reference.alt=`图片 ${index+1} 的设计参考图`;const title=el('div');title.append(el('h3',`图片 ${index+1}`),el('span','对应参考：'+card.reference.name,'muted'));heading.append(reference,title);
    const details=el('dl',undefined,'details');for(const [key,label] of Object.entries(labels))details.append(el('dt',label),el('dd',card.plan[key]));
    const result=el('div',undefined,'image-result');
    if(card.image_url){const image=el('img');image.src=card.image_url;image.alt=`图片 ${index+1} 的生成结果`;result.append(image,el('p',card.image_is_latest?'当前生成结果':'上次成功生成的图片 · 本次尝试未替换该结果','image-caption'));}
    else result.append(el('p','尚无生成图片。点击下方按钮后，这里展示实际返回的图片。'));
    const status=running.has(card.id)?'RUNNING':card.status;
    const actions=el('div',undefined,'generation-actions');const badge=el('span',statuses[status]||'状态待确认','generation-status'+(status==='SUCCEEDED'?' success':status==='FAILED'||status==='INTERRUPTED'?' failed':''));
    const button=el('button','生成图片','primary');button.disabled=status==='RUNNING'||!available;button.onclick=()=>generateOne(card.id);actions.append(badge,button);
    article.append(heading,details,result);
    if(card.error)article.append(el('div',card.error,'generation-error'));
    if(status==='INTERRUPTED')article.append(el('p','服务曾中断，远端调用结果未确认。现有记录保留，未自动重试。','generation-error'));
    article.append(actions);container.append(article);
  });
}
async function refresh(){
  current=await api(`/api/sessions/${sessionId}/generation`);available=true;render();
  clearTimeout(poll);
  if(current.cards.some(card=>card.status==='RUNNING'))poll=setTimeout(()=>refresh().catch(error=>message(error.message,true)),4000);
}
async function generateOne(target){
  if(running.has(target)||!current)return;
  const revision=current.confirmed_revision;
  running.add(target);render();
  try{
    const result=await api(`/api/sessions/${sessionId}/generate/${target}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_revision:revision})});
    message('本张图片已生成并保存；其他图片未改动。');
    if(result.confirmed_revision!==revision)message('计划版本已改变，结果保留在原版本中。',true);
  }catch(error){message(error.message,true);}
  finally{
    running.delete(target);
    try{await refresh();if(current.confirmed_revision!==revision)message('计划版本已改变，本次生成记录保留在原版本中。',true);}catch(error){available=false;render();message(error.message,true);node('task-summary').textContent='当前状态无法确认，保留已显示结果；请刷新或返回第一页检查。';}
  }
}
node('export-experiment').onclick=async()=>{
  const button=node('export-experiment');if(button.disabled)return;button.disabled=true;button.textContent='正在打包…';
  try{
    const response=await fetch(`/api/sessions/${sessionId}/export-experiment`,{method:'POST',headers:{'X-Local-Action':'prepare-plan'}});
    if(!response.ok){const body=await response.json();throw new Error(body.error||'实验包导出失败');}
    const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');
    const filename=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/);
    link.href=url;link.download=filename?filename[1]:'experiment.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
    message('实验包已交给浏览器下载；原始资料和运行记录未改动，未调用 AI。');
  }catch(error){message('导出失败：'+error.message,true);}
  finally{button.disabled=false;button.textContent='导出实验包';}
};
refresh().catch(error=>{message(error.message,true);node('task-summary').textContent='请返回第一页确认整套当前计划。';});
