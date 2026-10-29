"use strict";
(() => {
  let snapshot=null,loadingFor=null,sequence=0,syncing=false,failed=false;
  const prepare=window.PreparePlan,images=window.ImageGeneration;
  const readOnly=document.body.dataset.workspaceReadOnly==='true';
  const key=state=>state?`${state.id}:${state.revision}:${state.quality_revision||0}`:'';
  function aiAllowed(){
    if(readOnly)return false;
    const element=document.getElementById('local-debug-config');if(!element)return true;
    try{const config=JSON.parse(element.textContent);return config.mode!=='LIVE DEBUG'||Boolean(config.key_configured&&config.paid_actions_enabled);}
    catch{return false;}
  }
  function show(){
    const state=prepare.getState(),status=prepare.getStatus();
    if(!state){images.clear();return;}
    if(!snapshot||key(snapshot.state)!==key(state)){images.lock();return;}
    const blocked=readOnly||status.dirty||status.busy||failed;
    images.present(snapshot.generation,{key:key(state),allowed:snapshot.generation_allowed,blocked,historical:snapshot.historical_generation});
    const note=document.getElementById('workspace-note');
    note.textContent=readOnly?'匿名只读预览：可切换图片与历史版本查看，不保存选择、不调用模型；新建和制作请进入 8013 Live Debug。':status.dirty?'共享资料有未保存修改。另存为新任务后继续，旧任务和图片保留；当前禁止模型操作。':!snapshot.generation_allowed?'保存资料并完成理解与规划，在每张卡片确认本图计划后即可生成。刷新、查看历史、保存和确认不产生模型费用。':'各图独立确认与生成；修改本图计划不改变其他有效确认。历史成图保留，批量只处理从未尝试的图片；连接或结果不确定时暂停，不自动付费重试。';
    if(!readOnly&&!status.dirty&&state.mode==='product_pack'&&!state.listing_slots)note.textContent='历史 Listing 可查看、审核和导出；新增生成或修改须先在共享资料中分类并另存新任务，再重新规划和确认。原 Task、Run 和 Pass 保留。';
    if(!readOnly&&!status.dirty&&state.mode==='quick_redesign')note.textContent=state.quick_scenario?'Quick-A/B 场景请求策略已启用，无需独立 Planning；尺寸图须专项白底商品素材与运营声明；系统不认证尺寸数字。仅主动生成或修改才调用模型，不自动重试；执行成功不代表商品事实、主体替换或业务审核通过。':'Quick 无需 AI Planning 或计划确认。仅主动点击生成或修改才调用模型；保留历史版本和 Pass，连接或结果不确定时暂停，不自动重试。';
  }
  async function refresh(){
    const state=prepare.getState();if(!state){images.clear();return;}
    const expectedId=state.id,ticket=++sequence;
    loadingFor=key(state);
    try{
      const body=await prepare.api(`/api/sessions/${expectedId}/workspace`);
      if(ticket!==sequence||prepare.getState()?.id!==expectedId)return;
      const current=prepare.getState(),status=prepare.getStatus();
      if(body.state.revision!==current.revision||(body.state.quality_revision||0)!==(current.quality_revision||0)){
        if(status.dirty||status.busy)throw new Error('任务状态已在其他操作中改变；保留当前草稿，请检查后刷新。');
        syncing=true;try{prepare.applyState(body.state,body.activity);}finally{syncing=false;}
      }
      snapshot=body;failed=false;document.getElementById('config-note').hidden=body.ai_configured;show();
    }catch(error){failed=true;images.lock();throw error;}
    finally{if(ticket===sequence)loadingFor=null;}
  }
  window.Workspace={refresh,aiAllowed,planningChanged(){
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
