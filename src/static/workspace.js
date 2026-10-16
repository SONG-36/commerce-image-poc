"use strict";
(() => {
  let snapshot=null,loadingFor=null,sequence=0,syncing=false,failed=false;
  const prepare=window.PreparePlan,images=window.ImageGeneration;
  const key=state=>state?`${state.id}:${state.revision}`:'';
  function show(){
    const state=prepare.getState(),status=prepare.getStatus();
    if(!state){images.clear();return;}
    if(!snapshot||key(snapshot.state)!==key(state)){images.lock();return;}
    const blocked=status.dirty||status.busy||failed;
    images.present(snapshot.generation,{key:key(state),allowed:snapshot.generation_allowed,blocked,historical:snapshot.historical_generation});
    const note=document.getElementById('workspace-note');
    note.textContent=status.dirty?'共享资料有未保存修改。另存为新任务后继续，旧任务和图片保留；当前禁止模型操作。':snapshot.historical_generation?'当前计划尚未确认；卡片显示旧确认版本的历史成图供查看。检查并重新确认后，按新计划独立生成，不覆盖旧图。':!snapshot.generation_allowed?'保存资料并完成理解与规划；确认当前整套计划后才可生成。刷新、查看历史、保存和确认不产生模型费用。':'在同一卡片查看参考、计划、结果并修改或 Pass。只有主动点击 AI 操作才产生费用，不自动重试；连接中断时远端执行和计费需核对。';
  }
  async function refresh(){
    const state=prepare.getState();if(!state){images.clear();return;}
    const expectedId=state.id,ticket=++sequence;
    loadingFor=key(state);
    try{
      const body=await prepare.api(`/api/sessions/${expectedId}/workspace`);
      if(ticket!==sequence||prepare.getState()?.id!==expectedId)return;
      const current=prepare.getState(),status=prepare.getStatus();
      if(body.state.revision!==current.revision){
        if(status.dirty||status.busy)throw new Error('任务状态已在其他操作中改变；保留当前草稿，请检查后刷新。');
        syncing=true;try{prepare.applyState(body.state,body.activity);}finally{syncing=false;}
      }
      snapshot=body;failed=false;document.getElementById('config-note').hidden=body.ai_configured;show();
    }catch(error){failed=true;images.lock();throw error;}
    finally{if(ticket===sequence)loadingFor=null;}
  }
  window.Workspace={refresh,planningChanged(){
    if(syncing)return;
    const state=prepare.getState();
    if(!state){images.clear();return;}
    if(key(snapshot?.state)!==key(state)){
      images.lock();
      if(loadingFor!==key(state))refresh().catch(error=>{const box=document.getElementById('generation-message');box.hidden=false;box.className='error';box.textContent='工作台读取失败：'+error.message+'；未调用或自动重试模型。';});
    }else show();
  }};
  window.Workspace.planningChanged();
})();
