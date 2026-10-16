const {test}=require('node:test');
const assert=require('node:assert/strict');
const runner=require('../src/static/batch_generate.js');
const fresh=()=>({session_id:'offline',status:'NEW',items:[1,2,3].map(n=>({target:String(n),operation_id:String(n).repeat(32),status:'PENDING'}))});
function ports(outcomes,execute=async()=>{}){
  const calls=[],events=[];
  return {calls,events,persist(batch){events.push(JSON.parse(JSON.stringify(batch)));},update(){},
    async execute(item){assert.equal(events.at(-1).items.find(i=>i.target===item.target).status,'SUBMITTING');calls.push(item.operation_id);await execute(item);},
    async query(item){const outcome=outcomes[Number(item.target)-1];if(outcome instanceof Error)throw outcome;return outcome;}};
}
test('sequential execution records successes and clear failure once, preserving other results',async()=>{
  const b=fresh(),p=ports([{status:'SUCCEEDED'},{status:'FAILED',uncertain:false},{status:'SUCCEEDED'}]);
  await runner.run(b,p);assert.equal(b.status,'FINISHED');assert.deepEqual(b.items.map(i=>i.status),['SUCCEEDED','FAILED','SUCCEEDED']);assert.equal(p.calls.length,3);
});
test('uncertain connection stops before the next paid request and never retries',async()=>{
  const b=fresh(),p=ports([{status:'FAILED',uncertain:true}],async()=>{throw new Error('connection dropped');});
  await runner.run(b,p);assert.equal(b.status,'PAUSED');assert.equal(p.calls.length,1);assert.equal(b.items[1].status,'PENDING');assert.ok(runner.unresolved(b));
  await assert.rejects(()=>runner.run(b,p));assert.equal(p.calls.length,1);
});
test('lost HTTP response may be resolved by the exact saved operation, without resending',async()=>{
  const b=fresh(),p=ports([{status:'SUCCEEDED'},{status:'SUCCEEDED'},{status:'SUCCEEDED'}],async()=>{throw new Error('HTTP response lost');});
  await runner.run(b,p);assert.equal(b.status,'FINISHED');assert.equal(new Set(p.calls).size,3);assert.equal(p.calls.length,3);
});
test('missing operation or failed status query pauses rather than assuming no charge',async()=>{
  for(const result of [{status:'NOT_FOUND',uncertain:true},new Error('status lookup failed')]){
    const b=fresh(),p=ports([result]);await runner.run(b,p);assert.equal(b.status,'PAUSED');assert.equal(p.calls.length,1);
  }
});
test('reload only restores paused metadata, and explicit inspection is read only',async()=>{
  const old=fresh();old.status='RUNNING';old.items[0].status='SUBMITTING';
  const b=runner.restore(JSON.stringify(old)),p=ports([{status:'SUCCEEDED'}]);
  assert.equal(b.status,'PAUSED');assert.equal(p.calls.length,0);
  await runner.inspect(b,p);assert.equal(p.calls.length,0);assert.equal(b.items[0].status,'SUCCEEDED');assert.equal(b.status,'PAUSED');assert.equal(b.items[1].status,'PENDING');
});
test('storage failure prevents submission',async()=>{
  const b=fresh(),p=ports([]);p.persist=()=>{throw new Error('storage unavailable');};
  await assert.rejects(()=>runner.run(b,p));assert.equal(p.calls.length,0);
});
test('leaving a page stops the old loop even if the response later arrives',async()=>{
  const b=fresh(),p=ports([{status:'SUCCEEDED'}],async()=>{b.status='PAUSED';b.reason='page left';});
  await runner.run(b,p);assert.equal(p.calls.length,1);assert.equal(b.status,'PAUSED');assert.equal(b.items[1].status,'PENDING');
});
