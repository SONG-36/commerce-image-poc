/* Local developer UI only. No business commands, Evidence parsing or AI calls. */
(() => {
  'use strict';
  const node=id=>document.getElementById(id),toggle=node('toggle-inspector');
  const configuration=node('local-debug-config'),authorization=node('inspector-authorization');
  if(!configuration){
    // An old running server cannot attest its mode or the current Task scope.
    if(toggle){toggle.disabled=true;toggle.textContent='旧版调试实例：环境未核验';}
    return;
  }
  let access;try{access=JSON.parse(configuration.textContent);}catch{return;}
  const runtimeScope=access.task_scope==='runtime';
  const panel=node('debug-sidebar'),frame=node('debug-inspector-frame'),message=node('debug-sidebar-message');
  let opened=false,ready=false,timer=null,lastKey=null,lastSent=0,waiting=false;
  let checkedTask=access.task_id,accessTicket=0,accessController=null;
  const origin=window.location.origin;
  function wide(enabled){
    document.body.classList.toggle('debug-sidebar-wide',enabled);
    const button=node('expand-inspector');if(button){button.textContent=enabled?'返回摘要':'展开完整调试图';button.setAttribute('aria-pressed',String(enabled));}
    if(opened&&ready&&lastKey)frame.contentWindow.postMessage({type:'inspector:layout',expanded:enabled,selection:JSON.parse(lastKey)},origin);
  }
  const currentTask=()=>window.PreparePlan?.getState()?.id||window.ImageGeneration?.getDebugSelection()?.task_id||null;
  function unload(){
    ready=false;waiting=false;lastKey=null;
    if(frame)frame.src='about:blank';
  }
  function showAccess(){
    if(toggle)toggle.disabled=!access?.authorized;
    if(authorization)authorization.textContent=runtimeScope?
      (access?.authorized?'当前 Task 位于本地 Debug Runtime，无需逐项授权。':'保存有效任务后即可查看本地调试证据。'):
      (access?.authorized?'当前 Task 已获调试授权。':'当前 Task 未获调试授权。');
    if(!access?.authorized&&message)message.textContent=runtimeScope?
      '当前 Task 尚未保存或不在本地 Debug Runtime 内；已清空上一 Task 的证据。':
      '当前 Task 未获调试授权；已停止读取并清空上一 Task 的证据。';
  }
  async function authorize(task){
    const ticket=++accessTicket;checkedTask=task;access=null;unload();
    if(toggle)toggle.disabled=true;
    if(authorization)authorization.textContent=runtimeScope?'正在读取当前本地任务状态…':'正在核对当前 Task 的调试授权…';
    accessController?.abort();accessController=new AbortController();
    if(!/^[0-9a-f]{32}$/.test(task||'')){showAccess();return;}
    const controller=accessController,timeout=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch('/api/inspector/access?task_id='+encodeURIComponent(task),
        {method:'GET',cache:'no-store',credentials:'same-origin',signal:controller.signal});
      const result=await response.json();
      if(ticket!==accessTicket)return;
      if(!response.ok||result.task_id!==task||typeof result.authorized!=='boolean')throw new Error('授权状态不可确认');
      access=result;showAccess();
      if(opened&&access.authorized&&frame)frame.src='/inspector?embedded=1';
    }catch{
      if(ticket!==accessTicket)return;access=null;showAccess();
      if(authorization)authorization.textContent=runtimeScope?'无法读取当前本地任务状态；未读取证据。':
        '无法确认当前 Task 的调试授权；未读取证据。旧版实例需使用新启动配置。';
    }finally{clearTimeout(timeout);}
  }
  function sync(force=false){
    const task=currentTask();
    if(task!==checkedTask){authorize(task);return;}
    if(!opened||!ready||document.hidden||!access?.authorized)return;
    const selection=window.ImageGeneration.getDebugSelection(),key=JSON.stringify(selection);
    if(force||key!==lastKey||(!waiting&&selection&&Date.now()-lastSent>=5000)){
      lastKey=key;lastSent=Date.now();waiting=Boolean(selection);
      message.textContent=selection?`${selection.image_id} · revision ${selection.revision} · Run ${selection.run_id||'未保存'} · 正在读取已有证据…`:'请选择一张图片；没有调用模型。';
      frame.contentWindow.postMessage({type:'inspector:selection',selection},origin);
    }
  }
  function schedule(){
    clearTimeout(timer);
    if(opened)timer=setTimeout(()=>{sync();schedule();},500);
  }
  function close(){
    opened=false;ready=false;waiting=false;clearTimeout(timer);timer=null;
    panel.hidden=true;toggle.setAttribute('aria-expanded','false');
    document.body.classList.remove('debug-sidebar-open');
    wide(false);
    // Unload the child document: aborts its pending GET/images and removes timers.
    frame.src='about:blank';lastKey=null;
  }
  showAccess();
  window.addEventListener('workspace:task-changed',()=>{const task=currentTask();if(task!==checkedTask)authorize(task);});
  if(!toggle||!frame)return;
  toggle.onclick=()=>{
    const task=currentTask();if(task!==checkedTask){authorize(task);return;}
    if(!access?.authorized){showAccess();return;}
    if(opened){close();return;}
    opened=true;ready=false;waiting=false;panel.hidden=false;
    toggle.setAttribute('aria-expanded','true');document.body.classList.add('debug-sidebar-open');
    frame.src='/inspector?embedded=1';schedule();
  };
  node('close-inspector').onclick=close;
  const expandButton=node('expand-inspector');if(expandButton)expandButton.onclick=()=>wide(expandButton.getAttribute('aria-pressed')!=='true');
  frame.onload=()=>{if(opened){ready=true;sync(true);}};
  window.addEventListener('message',event=>{
    if(!opened||event.origin!==origin||event.source!==frame.contentWindow)return;
    if(JSON.stringify(event.data?.selection)!==lastKey)return;
    if(event.data?.type==='inspector:expand'){wide(true);return;}
    if(event.data?.type!=='inspector:result')return;
    waiting=false;
    message.textContent=event.data.ok?'已读取保存的证据 · 展开时每 5 秒刷新 · 不调用模型。':'证据暂不可读取；已有图片和操作不受影响，未重试模型。';
  });
  window.addEventListener('keydown',event=>{if(event.key==='Escape'&&opened){close();toggle.focus();}});
  window.addEventListener('pagehide',close);
  document.addEventListener('visibilitychange',()=>{if(opened&&!document.hidden)sync(true);});
})();
