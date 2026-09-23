import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const root=new URL('../',import.meta.url),r=JSON.parse(readFileSync(new URL('results.json',import.meta.url)));
for(const [p,sha] of Object.entries(r.provenance.source_sha256))assert.equal(createHash('sha256').update(readFileSync(new URL(p,root))).digest('hex'),sha,'Saved result is stale: '+p);
assert.equal(r.regressions.passed,true);
for(const a of r.analyses){
  assert.equal(a.scenarios.length,9);
  for(const s of a.scenarios){
    const q=s.breakeven_electricity_q025_q50_q975;
    assert.ok(q.every(Number.isFinite)&&q[0]<=q[1]&&q[1]<=q[2]);
    for(let i=1;i<s.electricity_sweep.length;i++)assert.ok(s.electricity_sweep[i].conditional_fraction<=s.electricity_sweep[i-1].conditional_fraction);
  }
}
console.log('PASS saved-result source hashes, finite quantiles and monotone crossing curves');
