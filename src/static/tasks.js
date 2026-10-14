"use strict";
async function loadTasks(){
  try{
    const response=await fetch('/api/tasks');const body=await response.json();if(!response.ok)throw new Error(body.error||'任务列表读取失败');
    const list=document.getElementById('tasks');list.replaceChildren();
    if(!body.tasks.length){const empty=document.createElement('p');empty.textContent='尚无任务，请创建新任务；也可在准备页加载 case-001。';list.append(empty);}
    for(const task of body.tasks){
      const row=document.createElement('article');row.className='task-row';const info=document.createElement('div');const name=document.createElement('h2');name.textContent=task.title;
      const date=document.createElement('p');date.className='muted';date.textContent='创建于 '+new Date(task.created_at).toLocaleString();
      const status=document.createElement('p');status.textContent=`${task.status} · 已生成 ${task.generated} / ${task.total} 张 · 已 Pass ${task.passed} 张`;
      const link=document.createElement('a');link.className='secondary button-link';link.href=task.url;link.textContent='打开 / 继续任务';info.append(name,date,status);row.append(info,link);list.append(row);
    }
  }catch(error){const message=document.getElementById('message');message.hidden=false;message.className='error';message.textContent=error.message;}
}
loadTasks();
