/* Sequential browser loop over the existing single-image API. No background queue. */
(function(root,factory){
  const runner=factory();
  if(typeof module==='object'&&module.exports)module.exports=runner;
  else root.ImageBatchRunner=runner;
})(globalThis,()=>{
  'use strict';
  const unresolved=batch=>batch?.items.some(i=>['SUBMITTING','UNCERTAIN'].includes(i.status));
  function restore(text){
    if(!text)return null;
    const batch=JSON.parse(text);
    if(!Array.isArray(batch.items))throw new Error('批次记录不可读取，请人工核对。');
    if(batch.status==='RUNNING'){
      batch.status='PAUSED';
      batch.reason='页面曾刷新或离开，批次已暂停；只查询已提交请求，不会续跑或重发。';
    }
    return batch;
  }
  function apply(item,result){
    item.run_id=result.run_id||null;
    item.error=result.error||'';
    if(result.status==='SUCCEEDED'&&!result.uncertain)item.status='SUCCEEDED';
    else if(result.status==='FAILED'&&!result.uncertain)item.status='FAILED';
    else item.status='UNCERTAIN';
  }
  async function inspect(batch,ports){
    for(const item of batch.items.filter(i=>['SUBMITTING','UNCERTAIN'].includes(i.status))){
      try{apply(item,await ports.query(item));}catch(error){item.status='UNCERTAIN';item.error=error.message;}
    }
    batch.status='PAUSED';
    batch.reason=unresolved(batch)?'请求状态或费用仍不确定，请人工核对 Run / 服务端；禁止自动重发。':'已核对提交结果。批次保持暂停；剩余图片须重新点击并确认新的批次。';
    ports.persist(batch);ports.update(batch);
  }
  async function run(batch,ports){
    if(batch.status!=='NEW')throw new Error('只允许执行新确认的批次；暂停或刷新后的批次不得自动续跑。');
    batch.status='RUNNING';ports.persist(batch);ports.update(batch);
    for(const item of batch.items){
      if(batch.status!=='RUNNING')return;
      item.status='SUBMITTING';
      // Persist the operation ID before a paid request can leave this page.
      ports.persist(batch);ports.update(batch);
      try{await ports.execute(item);}catch(error){item.error=error.message;}
      try{apply(item,await ports.query(item));}catch(error){item.status='UNCERTAIN';item.error=error.message;}
      if(batch.status!=='RUNNING'){ports.persist(batch);ports.update(batch);return;}
      if(item.status==='UNCERTAIN'){
        batch.status='PAUSED';batch.reason='连接或请求结果不确定，已暂停；请核对运行记录与费用，未重发请求。';
        ports.persist(batch);ports.update(batch);return;
      }
      ports.persist(batch);ports.update(batch);
    }
    batch.status='FINISHED';batch.reason='本批次已结束，失败图片未自动重试。';
    ports.persist(batch);ports.update(batch);
  }
  return {restore,run,inspect,unresolved};
});
