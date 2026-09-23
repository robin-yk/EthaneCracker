import test from 'node:test';
import assert from 'node:assert/strict';
import {posterior,quantiles,rng,pair,wilson} from './analysis.mjs';
test('known linear inverse problem recovers the injected parameter',()=>{
  const grid=Array.from({length:201},(_,i)=>0.5+i*0.01);
  const cells=posterior([{}],grid,12,0.5,(_,x)=>10*x);
  assert.ok(Math.abs(cells.reduce((s,c)=>s+c.weight,0)-1)<1e-12);
  const [lo,mid,hi]=quantiles(cells.map(c=>c.parameter),cells.map(c=>c.weight));
  assert.ok(Math.abs(mid-1.2)<0.011);assert.ok(lo>1.09&&lo<1.12);assert.ok(hi>1.28&&hi<1.31);
});
test('unobserved parameter retains a uniform prior; repeated nuisance alternatives add no information',()=>{
  const grid=Array.from({length:101},(_,i)=>i/100);
  const a=posterior([{}],grid,1,0.1,()=>1),b=posterior([{},{}],grid,1,0.1,()=>1);
  assert.deepEqual(quantiles(a.map(c=>c.parameter),a.map(c=>c.weight)),quantiles(b.map(c=>c.parameter),b.map(c=>c.weight)));
  assert.ok(Math.abs(a[50].weight-0.01)<1e-12);
});
test('paired root includes negative thresholds rather than clipping them to zero',()=>{
  const api={evaluate:p=>({economically_operable:true,cost_usd_per_t:100+(p.mode==='JH'?20+1000*p.elec:0)})};
  const r=pair(api,{elec:0.07},60,95,1);assert.ok(Math.abs(r.threshold+0.02)<1e-12);assert.ok(Math.abs(r.delta-90)<1e-12);
});
test('fixed seed reproduces uncertainty draws',()=>{const a=rng(42),b=rng(42);for(let i=0;i<100;i++)assert.equal(a(),b());});
test('zero successes retain nonzero Monte Carlo uncertainty',()=>{const [lo,hi]=wilson(0,512);assert.ok(lo<1e-12);assert.ok(hi>0.007&&hi<0.008);});
