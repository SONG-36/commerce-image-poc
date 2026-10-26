/* Saved Evidence only: GET requests, no workflow commands or model dispatch. */
(()=>{
  'use strict';
  const node=id=>document.getElementById(id);
  const labels={OBSERVED:'已观察',INFERRED:'推断关联',MISSING:'缺失数据',UNKNOWN:'来源未知',NOT_APPLICABLE:'不适用','N/A':'不适用'};
  let view=null,selectedNode='generation',ticket=0,controller=null;
  let parentSelection=null,openedCards=new Set();
  const embedded=document.body.dataset.embedded==='true';
  // An already-running Flask process may still serve its cached V0.6 template.
  const graphEnabled=Boolean(node('flow-canvas')&&node('flow-summary'));
  let expanded=!embedded,graphSelection=null,detailLevel=1,allRelations=false,viewport={x:20,y:20,k:1},pan=null;
  const positions={N01:[0,35],N02:[0,165],N03:[0,295],N04:[0,425],N05:[0,565],N13:[0,695],N14:[220,695],
    N07:[220,35],P01:[220,295],N06:[440,105],N08:[440,365],N09:[660,105],P02:[660,365],N10:[880,105],N11:[880,365],P03:[880,565],N12:[660,695]};
  const relationNames={USED_AS:'用作',INCLUDED_IN:'包含于',ASSEMBLED_INTO:'组装成',SUBMITTED_WITH:'随请求提交',PRODUCED:'产出'};
  const mainEdges=new Set(['E01','E02','E06','E07','E08','E09','E10','E13','E14','E15','E16','E17']);
  function el(tag,text,className){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(className)item.className=className;return item;}
  function status(item,value){item.textContent=labels[value]||value;item.className='badge '+String(value).toLowerCase();}
  async function get(url,signal){const response=await fetch(url,{method:'GET',cache:'no-store',credentials:'same-origin',signal});const body=await response.json();if(!response.ok)throw new Error(body.error||'证据不可读取。');return body;}
  function options(id,items,value){const select=node(id);select.replaceChildren();for(const item of items){const option=el('option',item.label);option.value=String(item.value);select.append(option);}select.disabled=!items.length;select.value=String(value??'');}
  function query(selection){const q=new URLSearchParams();for(const key of ['image_id','revision','run_id'])if(selection[key]!==null&&selection[key]!==undefined&&selection[key]!=='')q.set(key,selection[key]);return q.toString();}
  function assetUrl(asset){return '/api/inspector/tasks/'+view.selection.task_id+'/assets/'+encodeURIComponent(asset.key)+'?'+query(view.selection);}
  function expand(){expanded=true;layoutGraph();if(embedded&&view)window.parent.postMessage({type:'inspector:expand',selection:parentSelection||view.selection},window.location.origin);}
  function sourceLinks(sources){
    const row=el('div',undefined,'source-links');
    for(const source of sources||[]){
      const button=el('button',source.file+(source.pointer?' #'+source.pointer:''),'source-ref');button.type='button';
      button.title='原文件 SHA-256 '+(source.sha256||'UNKNOWN');
      button.onclick=()=>{
        const item=view.nodes.find(item=>item.id===source.node_id),doc=item?.documents.find(doc=>doc.key===source.document_key);
        if(source.asset_key){const asset=view.assets.find(a=>a.key===source.asset_key);if(asset?.status==='OBSERVED'){node('large-image').src=assetUrl(asset);node('large-caption').textContent=asset.label+' · '+asset.sha256;node('image-dialog').showModal();}return;}
        node('advanced-evidence').open=true;selectNode(source.node_id);if(doc){selectDocument(doc);node('file-meta').textContent+=' · JSON Pointer '+(source.pointer||'/');}
        if(node('context-dialog').open)node('context-dialog').close();
        node('advanced-evidence').scrollIntoView?.({block:'start',behavior:'smooth'});
      };row.append(button);
    }return row;
  }
  function imageTile(input,label){
    const tile=el('figure',undefined,'context-image'),asset=view.assets.find(asset=>asset.key===input?.asset_key);
    const roleNames={original:'商品原图',product:'商品原图',design_reference:'设计参考',reference:'参考图',current_image:'当前选中版本',auxiliary_reference:'新增辅助图',output:'生成结果'};
    const title=label||`${input.position?'#'+input.position+' · ':''}${roleNames[input.role]||input.role||'角色 UNKNOWN'}`;
    if(asset?.status==='OBSERVED'){
      const button=el('button',undefined,'image-button');button.type='button';const image=el('img');image.alt=title;image.src=assetUrl(asset);image.loading='lazy';
      image.onerror=()=>{button.replaceChildren(el('span','图片不可读取'));};button.append(image);
      button.onclick=()=>{expand();node('large-image').src=image.src;node('large-caption').textContent=title+(view.graph_view?.supported?'':' · SHA-256 '+asset.sha256);node('image-dialog').showModal();};tile.append(button);
    }else tile.append(el('div','图片缺失 / UNKNOWN','image-placeholder'));
    tile.append(el('figcaption',title),el('small',input.id||asset?.label||''));return tile;
  }
  function showPrompt(focusRef){
    const context=view.context_view,body=node('context-dialog-body');body.replaceChildren();
    node('context-dialog-title').textContent='最终 Prompt · 已保存请求全文';
    const prompt=context.prompt?.status==='OBSERVED'?context.prompt:context.prompt_file;
    body.append(el('p',context.prompt?.status==='OBSERVED'?'来自 request.json /prompt；展示已脱敏，不代表模型内部行为。':'实际 request.prompt UNKNOWN；以下仅为 prompt.txt 留存。','muted'));
    const pre=el('pre',undefined,'prompt-full'),text=typeof prompt?.value==='string'?prompt.value:'UNKNOWN · 未保存 Prompt，未使用当前代码重建。';
    if(focusRef?.text_span&&context.prompt?.status==='OBSERVED'){const chars=Array.from(text),{start,end}=focusRef.text_span;pre.append(el('span',chars.slice(0,start).join('')),el('mark',chars.slice(start,end).join('')),el('span',chars.slice(end).join('')));}else pre.textContent=text;
    body.append(pre,sourceLinks(prompt?.sources));
    if(context.prompt?.status==='OBSERVED'&&context.prompt_file?.status==='OBSERVED'&&context.prompt.value!==context.prompt_file.value){
      body.append(el('p','MISMATCH · 两份 Prompt 留存不同，不能静默选成同一份。','missing'),el('pre',context.prompt_file.value,'prompt-full'),sourceLinks(context.prompt_file.sources));
    }expand();node('context-dialog').showModal();
  }
  function showComparison(){
    const body=node('context-dialog-body'),comparison=view.context_view.comparison;
    body.replaceChildren();node('context-dialog-title').textContent='原始商品 / 本次输出';
    const pair=el('div',undefined,'comparison-pair');
    for(const [key,label] of [[comparison.before,'原始商品'],[comparison.after,'本次输出']])pair.append(imageTile({asset_key:key},label));
    body.append(el('p','只展示文件对照；不自动判断外观准确性或人工通过。','muted'),pair);expand();node('context-dialog').showModal();
  }
  function renderContext(){
    if(graphEnabled&&view.graph_view?.supported){renderFlow();return;}
    if(graphEnabled&&view.graph_view?.awaiting_run){node('flow-summary').replaceChildren();node('flow-workbench').hidden=true;node('context-cards').replaceChildren();node('expand-context').hidden=true;node('context-note').textContent=view.graph_view.note;node('flow-caption').textContent='等待本图 Run 留存';node('context-warnings').replaceChildren();return;}
    if(graphEnabled){node('flow-summary').replaceChildren();node('flow-workbench').hidden=true;}node('context-cards').hidden=false;
    const context=view.context_view,container=node('context-cards');container.replaceChildren();
    node('context-note').textContent=context?.note||'历史实例没有 Context 投影；请查看执行节点和高级证据。';
    node('context-warnings').replaceChildren(...(context?.warnings||[]).map(text=>el('p',text,'missing')));
    node('expand-context').hidden=!embedded;
    for(const item of context?.cards||[]){
      const card=el('article',undefined,'context-card'),toggle=el('button',undefined,'context-toggle');toggle.type='button';
      toggle.append(el('h3',item.title));const badge=el('span');status(badge,item.status);toggle.append(badge);
      card.append(toggle,el('p',item.summary,'context-summary'));
      const images=el('div',undefined,'context-images');
      if(item.id==='output'){
        for(const [key,label] of [[context.comparison.before,'原始商品'],[context.comparison.after,'本次输出']])images.append(imageTile({asset_key:key},label));
      }else for(const input of item.images)images.append(imageTile(input));
      if(images.children.length)card.append(images);
      if(item.id==='requirements'){
        const requirement=item.fields.find(field=>field.label==='本次整体设计要求');
        card.append(el('p',requirement?.value||'本次要求 UNKNOWN','requirement-preview'));
      }
      if(item.id==='request'){const button=el('button','查看完整 Prompt','context-primary');button.type='button';button.onclick=showPrompt;card.append(button);}
      if(item.id==='output'){const button=el('button','原图 / 成图对照','context-primary');button.type='button';button.onclick=showComparison;card.append(button);}
      const body=el('div',undefined,'context-content');body.hidden=!openedCards.has(item.id);
      toggle.setAttribute('aria-expanded',String(!body.hidden));
      toggle.onclick=()=>{body.hidden=!body.hidden;toggle.setAttribute('aria-expanded',String(!body.hidden));if(body.hidden)openedCards.delete(item.id);else openedCards.add(item.id);};
      if(item.note)body.append(el('p',item.note,'muted'));
      for(const field of item.fields){
        const entry=el('div',undefined,'context-field');entry.append(el('strong',field.label));
        entry.append(el('p',field.status==='UNKNOWN'?'UNKNOWN · 原始证据不能确认':field.value===''?'（已保存空值）':String(field.value),'context-value'));
        if(field.note)entry.append(el('small',field.note));entry.append(sourceLinks(field.sources));body.append(entry);
      }
      for(const check of item.checks){
        const entry=el('div',undefined,'context-check '+check.result.toLowerCase());entry.append(el('strong',check.result+' · '+check.label));
        if(check.note)entry.append(el('p',check.note,'muted'));entry.append(sourceLinks(check.sources));body.append(entry);
      }
      for(const input of item.images){
        const entry=el('div',undefined,'context-field');entry.append(el('strong',`${input.position?'位置 '+input.position+' / slot '+(input.slot??'UNKNOWN')+' · ':''}${input.id||'图片'} · ${input.role}`),
          el('small','文件 '+input.file),el('small','实际 SHA-256 '+(input.sha256||'UNKNOWN')),
          el('small',input.hash_matches===true?'MATCH · 与记录哈希一致':input.hash_matches===false?'MISMATCH · 与记录哈希不同':'UNKNOWN · 无法核对记录哈希'));
        if(input.note)entry.append(el('p',input.note,'muted'));entry.append(sourceLinks(input.sources));body.append(entry);
      }
      card.append(body);container.append(card);
    }
  }
  function svg(tag,attrs={},text){const item=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))item.setAttribute(key,String(value));if(text!==undefined)item.textContent=text;return item;}
  function action(label,fn,cls){const button=el('button',label,cls);button.type='button';button.onclick=fn;return button;}
  function layoutGraph(){
    if(!graphEnabled||!view?.graph_view?.supported)return;
    node('flow-workbench').hidden=!expanded;document.body.classList.toggle('flow-expanded',expanded);
    node('expand-context').textContent=expanded?'完整调试图已展开':'展开完整调试图';
    if(expanded)setTimeout(fitGraph,0);
  }
  function renderFlow(){
    const graph=view.graph_view;node('context-cards').replaceChildren();node('context-cards').hidden=true;
    node('expand-context').hidden=false;
    node('flow-caption').textContent='Quick Redesign · '+graph.nodes.length+' 个节点 · '+graph.edges.length+' 条证据关系';
    node('context-note').textContent='Quick 无独立 Planning。箭头表示证据关联，不是模型内部因果或质量通过。';
    node('context-warnings').replaceChildren(...graph.warnings.map(text=>el('p',text,'missing')));
    const summary=node('flow-summary');summary.replaceChildren();
    for(const stage of graph.stages){
      const members=graph.nodes.filter(n=>stage.node_ids.includes(n.id)),counts={};for(const n of members)counts[n.evidence_status]=(counts[n.evidence_status]||0)+1;
      const button=action('',()=>{expand();chooseGraph(members[0].id);},'flow-stage');
      button.append(el('strong',stage.label),el('span',Object.entries(counts).map(([key,n])=>(labels[key]||key)+' '+n).join(' · ')));
      const mismatch=members.some(n=>n.consistency_checks.some(c=>c.result==='MISMATCH'))||graph.edges.some(e=>stage.node_ids.includes(e.source)&&e.consistency_checks.some(c=>c.result==='MISMATCH'));
      const warning=mismatch?'MISMATCH · 证据不一致':members.some(n=>n.evidence_status==='MISSING')?'存在缺失证据':members.some(n=>n.evidence_status==='INFERRED')?'包含逻辑推断':null;
      if(warning)button.append(el('small',warning));summary.append(button);
    }
    if(!graph.nodes.some(n=>n.id===graphSelection)&&!graph.edges.some(e=>e.id===graphSelection)){graphSelection=graph.nodes.find(n=>n.key==='P01').id;detailLevel=1;}
    node('flow-relation-count').textContent='全部 '+graph.edges.length+' 条传递关系 · 按需选择';
    node('flow-relation-list').replaceChildren(...graph.edges.map(edge=>action(edge.key+' · '+graph.nodes.find(n=>n.id===edge.source).label+' → '+graph.nodes.find(n=>n.id===edge.target).label+' · '+relationNames[edge.relation_type],()=>chooseGraph(edge.id),'relation-item')));
    drawGraph();renderGraphDetail();layoutGraph();
  }
  function chooseGraph(id){
    const visibleCount=()=>[...node('flow-canvas').children[1].children].filter(e=>e.getAttribute('data-node')).length,oldCount=visibleCount();
    graphSelection=id;detailLevel=1;drawGraph();renderGraphDetail();
    if(visibleCount()>oldCount)fitGraph();
    const graph=view.graph_view,item=graph.nodes.find(n=>n.id===id)||graph.edges.find(e=>e.id===id);
    const match=[...node('flow-canvas').children[1].children].find(e=>e.getAttribute('data-node')===item.key||e.getAttribute('data-edge')===item.key);match?.focus();
  }
  function drawGraph(){
    const graph=view?.graph_view;if(!graph?.supported)return;
    const canvas=node('flow-canvas');canvas.replaceChildren();
    const defs=svg('defs'),marker=svg('marker',{id:'flow-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});
    marker.append(svg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#8ea9c7'}));defs.append(marker);canvas.append(defs);
    const group=svg('g',{id:'flow-transform'});canvas.append(group);
    const picked=graph.edges.find(e=>e.id===graphSelection),chosen=graph.nodes.find(n=>n.id===graphSelection);
    const visibleNodes=graph.nodes.filter(n=>allRelations||n.default_visible||picked&&(picked.source===n.id||picked.target===n.id));
    const visibleEdges=graph.edges.filter(e=>(allRelations||mainEdges.has(e.key)||e===picked)&&visibleNodes.some(n=>n.id===e.source)&&visibleNodes.some(n=>n.id===e.target));
    // Directed reachability highlights upstream/downstream without changing workflow.
    const related=new Set(chosen?[chosen.id]:picked?[picked.source,picked.target]:[]);
    if(chosen)for(const direction of ['source','target']){const reachable=new Set([chosen.id]);let changed=true;while(changed){changed=false;for(const e of graph.edges){const other=direction==='source'?'target':'source';if(reachable.has(e[direction])&&!reachable.has(e[other])){reachable.add(e[other]);changed=true;}}}for(const id of reachable)related.add(id);}
    const bind=(element,id)=>{element.onclick=()=>chooseGraph(id);element.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();chooseGraph(id);}};};
    for(const edge of visibleEdges){
      const from=graph.nodes.find(n=>n.id===edge.source),to=graph.nodes.find(n=>n.id===edge.target),[sx,sy]=positions[from.key],[tx,ty]=positions[to.key];
      const same=sx===tx,x1=same?sx+90:sx+180,y1=same?sy+82:sy+41,x2=same?tx+90:tx,y2=same?ty:ty+41;
      const d=same?`M ${x1} ${y1} L ${x2} ${y2}`:`M ${x1} ${y1} C ${x1+45} ${y1}, ${x2-45} ${y2}, ${x2} ${y2}`;
      const item=svg('g',{'class':'flow-edge '+(edge.evidence_status==='OBSERVED'?'certain':'uncertain')+(edge.id===graphSelection?' selected':'')+(chosen&&!related.has(edge.source)&&!related.has(edge.target)?' dimmed':''),role:'button',tabindex:0,'aria-label':edge.key+' '+from.label+' '+relationNames[edge.relation_type]+' '+to.label+' '+labels[edge.evidence_status],'data-edge':edge.key});
      item.append(svg('path',{d,'class':'edge-hit'}),svg('path',{d,'class':'edge-line','marker-end':'url(#flow-arrow)'}));
      item.append(svg('text',{x:(x1+x2)/2,y:(y1+y2)/2-7,'class':'edge-label','text-anchor':'middle'},edge.key+' '+relationNames[edge.relation_type]));bind(item,edge.id);group.append(item);
    }
    for(const item of visibleNodes){
      const [x,y]=positions[item.key],g=svg('g',{transform:`translate(${x},${y})`,role:'button',tabindex:0,'aria-label':item.label+' '+(labels[item.evidence_status]||item.evidence_status),'data-node':item.key,
        'class':'flow-node '+(item.kind==='ACTIVITY'?'activity':'artifact')+(item.id===graphSelection?' selected':'')+(chosen&&!related.has(item.id)?' dimmed':'')});
      g.append(svg('rect',{width:180,height:82,rx:item.kind==='ACTIVITY'?25:5}));
      g.append(svg('text',{x:12,y:21,'class':'node-kind'},item.kind==='ACTIVITY'?'ACTIVITY / 活动':'ARTIFACT / 数据'),svg('text',{x:12,y:45,'class':'node-label'},item.label),svg('text',{x:12,y:66,'class':'node-status'},labels[item.evidence_status]||item.evidence_status));bind(g,item.id);group.append(g);
    }
    node('flow-more').textContent=allRelations?'收起补充关系':'展开补充关系';node('flow-more').setAttribute('aria-pressed',String(allRelations));transformGraph();
  }
  function transformGraph(){const group=node('flow-canvas').children[1];if(group)group.setAttribute('transform',`translate(${viewport.x},${viewport.y}) scale(${viewport.k})`);node('flow-scale').textContent=Math.round(viewport.k*100)+'%';}
  function fitGraph(){if(!view?.graph_view?.supported||!expanded)return;const box=node('flow-canvas').getBoundingClientRect(),keys=[...node('flow-canvas').children[1].children].map(e=>e.getAttribute('data-node')).filter(Boolean);const width=Math.max(...keys.map(key=>positions[key][0]+180)),height=Math.max(...keys.map(key=>positions[key][1]+82));const k=Math.min(1.25,Math.max(.25,Math.min((box.width-40)/width,(box.height-40)/height)));viewport={k,x:(box.width-width*k)/2,y:(box.height-height*k)/2};transformGraph();}
  function zoomGraph(factor){const box=node('flow-canvas').getBoundingClientRect(),next=Math.min(2.5,Math.max(.25,viewport.k*factor)),ratio=next/viewport.k;viewport={k:next,x:box.width/2-(box.width/2-viewport.x)*ratio,y:box.height/2-(box.height/2-viewport.y)*ratio};transformGraph();}
  function renderGraphDetail(){
    const graph=view.graph_view,item=graph.nodes.find(n=>n.id===graphSelection)||graph.edges.find(e=>e.id===graphSelection),body=node('flow-detail');body.replaceChildren();if(!item)return;
    const edge=!!item.relation_type,title=edge?item.key+' · '+relationNames[item.relation_type]:item.label;
    body.append(el('p',edge?'传递关系':'所选'+(item.kind==='ACTIVITY'?'活动':'数据'),'eyebrow'),el('h2',title));const badge=el('p');status(badge,item.evidence_status);body.append(badge);
    const tabs=el('div',undefined,'detail-levels');for(const [level,label] of [[1,'1 · 业务含义'],[2,'2 · 实际内容'],[3,'3 · 来源证据']])tabs.append(action(label,()=>{detailLevel=level;renderGraphDetail();},detailLevel===level?'selected':''));body.append(tabs);
    body.append(el('p',edge?item.claim:item.summary,'detail-summary'));
    const mismatches=item.consistency_checks.filter(check=>check.result==='MISMATCH');if(mismatches.length)body.append(el('p','MISMATCH · '+mismatches.map(check=>check.label).join('；'),'missing'));
    if(edge){const source=graph.nodes.find(n=>n.id===item.source),target=graph.nodes.find(n=>n.id===item.target);body.append(el('p',source.label+' → '+target.label,'flow-transfer'),el('p',item.uncertainty_reason,'muted'));
      if(detailLevel<=2)for(const ref of item.evidence_refs){if(ref.text_span){const doc=view.nodes.find(n=>n.id===ref.node_id)?.documents.find(d=>d.key===ref.document_key),text=doc?.data?.prompt;if(typeof text==='string'){body.append(el('h3','保存 Prompt 中的对应原文'),el('blockquote',Array.from(text).slice(ref.text_span.start,ref.text_span.end).join('')),el('small','来自已保存请求 /prompt · 第 '+ref.line_range.join('–')+' 行'));body.append(action('定位 Prompt 全文',()=>showPrompt(ref),'context-primary'));}}}
      if(detailLevel===2){
        for(const endpoint of [source,target]){body.append(el('h3',endpoint.label));
          for(const field of endpoint.fields||[]){if(field.status==='OBSERVED'&&typeof field.value==='string')body.append(el('p',field.label+'：'+field.value.slice(0,400),'context-value'));}
          const images=el('div',undefined,'context-images');for(const image of endpoint.images||[])images.append(imageTile(image));if(images.children.length)body.append(images);
        }
      }
    }else{
      if(item.execution_status!=='UNKNOWN')body.append(el('p','本地执行状态：'+item.execution_status+'（不等于质量通过）'));
      const images=el('div',undefined,'context-images');for(const image of (item.images||[]).slice(0,detailLevel===1?2:undefined))images.append(imageTile(image));if(images.children.length)body.append(images);
      if(item.key==='N08'||item.key==='N09')body.append(action('查看完整 Prompt',showPrompt,'context-primary'));
      if(item.key==='N11')body.append(action('原图 / 成图对照',showComparison,'context-primary'));
      const fields=(item.fields||[]).filter(field=>detailLevel!==1||!['Run ID','Operation ID','Context Task','Context Image','父版本 Run','OpenAI request_id'].includes(field.label));
      for(const field of fields){const entry=el('div',undefined,'context-field');entry.append(el('strong',field.label));let value=field.status==='UNKNOWN'?'UNKNOWN · 原始证据不能确认':typeof field.value==='object'?JSON.stringify(field.value,null,2):String(field.value??'UNKNOWN');
        if(detailLevel===1)value=value.length>150?value.slice(0,150)+'…':value;entry.append(el('p',value,'context-value'));if(detailLevel>=2&&field.note)entry.append(el('small',field.note));body.append(entry);}
      if(detailLevel>=2)for(const image of item.images||[])body.append(el('p','位置 '+(image.position??'未知')+' / slot '+(image.slot??'未知')+' · '+image.role+' · '+(image.id||''),'image-order'));
      if(item.key==='P01'&&detailLevel===1)body.append(el('p','核对文字、Context 身份与图片哈希。MATCH 只表示留存一致，不能证明模型遵守。','muted'));
    }
    if(detailLevel>=2&&item.uncertainty_reason)body.append(el('p',item.uncertainty_reason,'muted'));
    if(detailLevel===3){
      for(const check of item.consistency_checks){const entry=el('div',undefined,'context-check '+check.result.toLowerCase());entry.append(el('strong',check.result+' · '+check.label),el('p',check.note||'只核对证据一致性。','muted'),sourceLinks(check.sources));body.append(entry);}
      body.append(sourceLinks(item.evidence_refs),el('pre',JSON.stringify({identity:graph.selection,evidence_refs:item.evidence_refs,consistency_checks:item.consistency_checks,event_id:item.event_id??null,code_refs:item.code_refs||[]},null,2),'graph-raw'));
    }
  }
  if(graphEnabled){
  node('flow-zoom-in').onclick=()=>zoomGraph(1.2);node('flow-zoom-out').onclick=()=>zoomGraph(1/1.2);node('flow-fit').onclick=fitGraph;
  node('flow-more').onclick=()=>{allRelations=!allRelations;drawGraph();fitGraph();};
  const canvas=node('flow-canvas');
  canvas.onkeydown=event=>{if(['+','=','-','0','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();if(event.key==='0')fitGraph();else if(['+','=','-'].includes(event.key))zoomGraph(event.key==='-'?1/1.2:1.2);else{viewport.x+=event.key==='ArrowLeft'?30:event.key==='ArrowRight'?-30:0;viewport.y+=event.key==='ArrowUp'?30:event.key==='ArrowDown'?-30:0;transformGraph();}}};
  canvas.onpointerdown=event=>{if(event.target!==canvas)return;pan={x:event.clientX,y:event.clientY,originX:viewport.x,originY:viewport.y};canvas.setPointerCapture(event.pointerId);};
  canvas.onpointermove=event=>{if(!pan)return;viewport.x=pan.originX+event.clientX-pan.x;viewport.y=pan.originY+event.clientY-pan.y;transformGraph();};
  canvas.onpointerup=canvas.onpointercancel=()=>{pan=null;};
  canvas.onwheel=event=>{event.preventDefault();zoomGraph(event.deltaY<0?1.1:1/1.1);};
  window.addEventListener('resize',()=>{if(expanded)fitGraph();});
  }
  function selectDocument(doc){
    const digest=doc.sha256?'SHA-256 '+doc.sha256:'无文件哈希';
    node('file-meta').textContent=doc.file+' · '+(labels[doc.status]||doc.status)+' · '+digest+(doc.bytes!==undefined?' · '+doc.bytes+' bytes':'');
    node('document').textContent=doc.status==='OBSERVED'?(typeof doc.data==='string'?doc.data:JSON.stringify(doc.data,null,2)):(doc.note||'此证据未保存。');
    for(const button of node('file-list').children)button.classList.toggle('selected',button.dataset.key===doc.key);
  }
  function selectNode(id){
    selectedNode=id;const item=view.nodes.find(item=>item.id===id);if(!item)return;
    node('node-title').textContent=item.label+(item.applicable===false?' · 不适用':'');status(node('node-status'),item.status);
    node('node-note').textContent=(item.execution_status?'本次执行状态：'+item.execution_status+'。':'')+item.note+(item.call_id?' Call ID: '+item.call_id:'');node('file-list').replaceChildren();
    for(const doc of item.documents){const button=el('button',doc.file+' · '+labels[doc.status]);button.type='button';button.dataset.key=doc.key;button.onclick=()=>selectDocument(doc);node('file-list').append(button);}
    node('file-meta').textContent='';node('document').textContent='没有可用的原始记录；未伪造或补写。';
    if(item.documents.length)selectDocument(item.documents.find(doc=>doc.status==='OBSERVED')||item.documents[0]);
    for(const button of node('graph').children){const active=button.dataset.node===id;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));}
  }
  function render(){
    const s=view.selection;node('identity').textContent='Task '+s.task_id+' / '+s.image_id+' / revision '+s.revision+' / Run '+(s.run_id||'未保存');
    if(node('selection-summary'))node('selection-summary').textContent=node('identity').textContent+(s.run_id?'':' · 尚无 Run；未创建模型 Context 或请求。原始资料及输入快照可在高级证据查看。');
    options('image-select',view.images.map(i=>({label:i.id,value:i.id})),s.image_id);
    options('revision-select',view.revisions.map(i=>({label:'revision '+i,value:i})),s.revision);
    options('run-select',view.runs.map(i=>({label:i,value:i})),s.run_id);
    renderContext();
    node('graph').replaceChildren();for(const item of view.nodes){const button=el('button',undefined,'graph-node');button.type='button';button.dataset.node=item.id;button.append(el('strong',item.label));const badge=el('span');status(badge,item.status);button.append(badge);button.onclick=()=>{node('advanced-evidence').open=true;selectNode(item.id);};node('graph').append(button);}
    node('edges').replaceChildren();for(const edge of view.edges){const names=id=>view.nodes.find(n=>n.id===id)?.label||id;node('edges').append(el('p',names(edge.source)+' → '+names(edge.target)+' · '+labels[edge.status]+'：'+edge.basis,edge.status.toLowerCase()));}
    node('assets').replaceChildren();for(const asset of view.assets){
      const card=el('article',undefined,'asset');card.append(el('h3',asset.label),el('p',asset.role||'未记录角色','muted'));
      if(asset.status==='OBSERVED'){
        const button=el('button',undefined,'image-button');button.type='button';const image=el('img');image.alt=asset.label;image.src=assetUrl(asset);image.loading='lazy';
        image.onerror=()=>{button.replaceChildren(el('span','图片不可预览；请核对证据字节或访问限制。'));};
        button.append(image);button.onclick=()=>{node('large-image').src=image.src;node('large-caption').textContent=asset.label+' · '+asset.role;node('image-dialog').showModal();};card.append(button);
      }else card.append(el('p','原始文件缺失','missing'));
      if(asset.source)card.append(el('p',asset.source,'muted'));
      card.append(el('small','SHA-256 '+(asset.sha256||'未获取'),'digest'));
      card.append(el('p',asset.hash_matches===false?'哈希不一致：记录与文件不同':asset.hash_matches===true?'已记录哈希与文件一致':'没有可对照的已记录哈希',asset.hash_matches===false?'missing':'muted'));
      node('assets').append(card);
    }
    node('limitations').replaceChildren(...view.limitations.map(text=>el('li',text)));selectNode(selectedNode);node('evidence').hidden=false;
  }
  async function load(selection={},task=node('task-select').value){
    const changed=!view||task!==view.selection.task_id||Object.entries(selection).some(([key,value])=>value!==view.selection[key]);
    const current=++ticket;node('message').textContent='正在读取历史证据…';
    if(changed){node('evidence').hidden=true;openedCards=new Set();graphSelection=null;detailLevel=1;allRelations=false;pan=null;node('flow-detail')?.replaceChildren();node('flow-canvas')?.replaceChildren();if(node('image-dialog').open)node('image-dialog').close();if(node('context-dialog').open)node('context-dialog').close();node('large-image').removeAttribute('src');}
    controller?.abort();controller=new AbortController();
    const active=controller,timeout=setTimeout(()=>active.abort(),10000);
    let ok=false;
    try{const result=await get('/api/inspector/tasks/'+encodeURIComponent(task)+'?'+query(selection),active.signal);if(current!==ticket)return;const unchanged=JSON.stringify(view)===JSON.stringify(result);view=result;if(!unchanged)render();else node('evidence').hidden=false;ok=true;node('message').textContent='已读取保存的证据；没有执行 AI 或改写记录。';}
    catch(error){if(current===ticket){view=null;node('evidence').hidden=true;node('message').textContent=error.message;}}
    finally{clearTimeout(timeout);if(embedded&&current===ticket)window.parent.postMessage({type:'inspector:result',selection:{task_id:task,...selection},ok},window.location.origin);}
  }
  node('task-select').onchange=()=>load();
  node('image-select').onchange=()=>load({image_id:node('image-select').value});
  node('revision-select').onchange=()=>load({image_id:node('image-select').value,revision:node('revision-select').value});
  node('run-select').onchange=()=>load({image_id:node('image-select').value,revision:node('revision-select').value,run_id:node('run-select').value});
  node('reload').onclick=()=>load(view?.selection||{});
  node('close-image').onclick=()=>{node('image-dialog').close();node('large-image').removeAttribute('src');};
  node('close-context').onclick=()=>node('context-dialog').close();
  node('expand-context').onclick=expand;
  if(embedded){
    node('message').textContent='请选择工作台中的图片；这里只读取保存的证据。';
    window.addEventListener('message',event=>{
      if(event.source!==window.parent||event.origin!==window.location.origin)return;
      if(event.data?.type==='inspector:layout'){
        if(view&&JSON.stringify(event.data.selection)===JSON.stringify(parentSelection)){expanded=event.data.expanded===true;layoutGraph();}return;
      }
      if(event.data?.type!=='inspector:selection')return;
      const selection=event.data.selection;
      if(!selection){ticket++;controller?.abort();view=null;parentSelection=null;node('evidence').hidden=true;if(node('image-dialog').open)node('image-dialog').close();if(node('context-dialog').open)node('context-dialog').close();node('large-image').removeAttribute('src');node('message').textContent='请选择工作台中的图片。';return;}
      if(!/^[0-9a-f]{32}$/.test(selection.task_id)||!/^(product|reference)_[0-9]+$/.test(selection.image_id)||!Number.isInteger(selection.revision)||selection.revision<1||
        (selection.run_id!==null&&!/^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}$/.test(selection.run_id)))return;
      parentSelection={...selection};const {task_id,...chosen}=selection;load(chosen,task_id);
    });
  }else get('/api/inspector/tasks').then(body=>{options('task-select',body.tasks.map(t=>({value:t.id,label:t.title+' · '+t.id})),body.tasks[0]?.id);if(body.tasks.length)return load();node('message').textContent='没有获准任务。';}).catch(error=>{node('message').textContent=error.message;});
})();
