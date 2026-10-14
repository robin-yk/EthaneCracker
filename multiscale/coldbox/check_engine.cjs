// Validation of the engine's cold-box thermodynamics against the Python reference.
// The engine solves the Peng-Robinson flash and the enthalpy balance in JavaScript
// (coldBox() in engine.html). The reference is the same physics computed with the thermo
// library (Peng-Robinson, ChemSep kij, its own ideal-gas heat capacities) on a 1 K cooling
// curve: coldbox-reference.csv, 1,234 feed compositions. The reference, Wang GP and Wang
// published cases are compared in full; every row is compared on the cold end and the
// cascade refrigeration work.
// Usage: node multiscale/coldbox/check_engine.cjs   (from the repository root)
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..','..');
const core=fs.readFileSync(path.join(root,'engine.html'),'utf8').split('<script>')[1]
  .split('/* ---------- process flow diagram ---------- */')[0];
const ctx={document:{getElementById:()=>null}};vm.createContext(ctx);
vm.runInContext(core+`\nconst app={gp:null};globalThis.api={S,model,coldBox,cascadeWork,set:m=>app.gp=m};`,ctx);
ctx.api.set(JSON.parse(fs.readFileSync(path.join(root,'multiscale/surrogate.json'))));

function parseCSV(text){  // minimal CSV reader with quoted fields
  const out=[];let row=[],f='',q=false;
  for(let i=0;i<text.length;i++){const c=text[i];
    if(q){if(c==='"'){if(text[i+1]==='"'){f+='"';i++;}else q=false;}else f+=c;}
    else if(c==='"')q=true;else if(c===','){row.push(f);f='';}
    else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(f);out.push(row);row=[];f='';}
    else f+=c;}
  if(f.length||row.length){row.push(f);out.push(row);}
  return out;
}
const table=parseCSV(fs.readFileSync(path.join(__dirname,'coldbox-reference.csv'),'utf8'));
const head=table[0]; const col=k=>head.indexOf(k);
const rows=table.slice(1).filter(r=>r.length>=head.length&&!r[col('error')]&&r[col('x_h2')]!=='');
const MW=[2.0159,16.0425,28.0532,30.0690,42.0797,56.1063];
// C3 and C4+ split: the reference set stores only x_c3plus; grid rows recover the split from the
// engine feeds (coldbox-feeds.json), perturbed rows use the reference-case ratio.
const feeds=JSON.parse(fs.readFileSync(path.join(__dirname,'coldbox-feeds.json'))).rows;
const splitMap=new Map(feeds.filter(f=>!f.error).map(f=>{const m=f.feed_kg_per_kg_ethylene;const c3=m.propylene/MW[4],c4=m['1-butene']/MW[5];
  return [[f.cot,f.tau,f.ramp,f.dilution,f.pressure].join(','),c3/(c3+c4)];}));
const refFeed=JSON.parse(fs.readFileSync(path.join(__dirname,'coldbox-vle-results.json'))).feeds['reference fired case (850 degC, 0.35 s)'].feed_mol_frac;
const refFrac=refFeed.propylene/(refFeed.propylene+refFeed['1-butene']);
let n=0,dTsum=0,dTmax=0,relSum=0,relMax=0,worst=null; const fails=[];
const bands={};
const t0=Date.now();
for(const r of rows){
  const z=['x_h2','x_ch4','x_c2h4','x_c2h6','x_c3plus'].map(k=>+r[col(k)]);
  const key=['cot','tau','ramp','dilution','pressure'].map(k=>+r[col(k)]).join(',');
  const frac=splitMap.has(key)?splitMap.get(key):refFrac;
  const c3=z[4]*frac, c4=z[4]-c3;
  const zz=[z[0],z[1],z[2],z[3],c3,c4];
  const nmol=1000/(z[2]*MW[2]);                         // mol per kg ethylene in the feed
  let cb; try{cb=ctx.api.coldBox(zz,nmol);}catch(e){fails.push({row:r.slice(0,7).join(','),z:zz.map(v=>+v.toFixed(5)),msg:e.message});continue;}
  const Tref=+r[col('T_cold_K')], qref=[+r[col('q40_cc')],+r[col('q100_cc')],+r[col('qcold_cc')]];
  const w=ctx.api.cascadeWork(cb.q), wref=ctx.api.cascadeWork(qref);
  const dT=cb.T_cold_K-Tref, rel=(w-wref)/wref;
  n++; dTsum+=dT*dT; dTmax=Math.max(dTmax,Math.abs(dT)); relSum+=rel*rel;
  if(Math.abs(rel)>relMax){relMax=Math.abs(rel);worst={row:r.slice(0,6).join(','),T:Tref-273.15,w,wref,q:cb.q.map(v=>v.toFixed(0)),qref:qref.map(v=>v.toFixed(0))};}
  const b=z[3]<0.5?'<0.5':z[3]<0.7?'0.5-0.7':z[3]<0.8?'0.7-0.8':z[3]<0.9?'0.8-0.9':'>0.9';
  (bands[b]=bands[b]||{n:0,dT2:0,rel2:0,relMax:0}); const B=bands[b]; B.n++;B.dT2+=dT*dT;B.rel2+=rel*rel;B.relMax=Math.max(B.relMax,Math.abs(rel));
  const label=r[col('label')];
  if(label) console.log(`${label.slice(0,44).padEnd(44)} T_cold ${(cb.T_cold_K-273.15).toFixed(2)} (ref ${(Tref-273.15).toFixed(2)}) `+
    `q ${cb.q.map(v=>v.toFixed(0)).join('/')} (ref ${qref.map(v=>v.toFixed(0)).join('/')})  w ${w.toFixed(0)} (ref ${wref.toFixed(0)}, ${(100*rel).toFixed(2)} %)`);
}
console.log(`\n${n} compositions in ${((Date.now()-t0)/1000).toFixed(1)} s: cold end rmse ${Math.sqrt(dTsum/n).toFixed(3)} K, max ${dTmax.toFixed(2)} K; `+
  `refrigeration work rmse ${(100*Math.sqrt(relSum/n)).toFixed(2)} %, max ${(100*relMax).toFixed(2)} %`);
for(const [b,B] of Object.entries(bands)) console.log(`  x_c2h6 ${b.padEnd(8)} n ${String(B.n).padStart(4)}  T rmse ${Math.sqrt(B.dT2/B.n).toFixed(3)} K  w rmse ${(100*Math.sqrt(B.rel2/B.n)).toFixed(2)} %  max ${(100*B.relMax).toFixed(2)} %`);
console.log('worst row:',JSON.stringify(worst));
console.log('flash failures:',fails.length); for(const f of fails.slice(0,8)) console.log('  ',JSON.stringify(f));
const r0=ctx.api.model({...ctx.api.S,kinetics:'gp',selMode:'calc',mode:'CH'});
console.log(`\nreference fired case: tCold ${r0.tCold.toFixed(2)} degC, q ${r0.qLevels.map(v=>v.toFixed(0)).join('/')}, wRef ${r0.wRef.toFixed(1)} kJ/kg (capital anchor), wSplit ${r0.wSplit.toFixed(0)}, coo ${r0.coo.toFixed(1)} USD/t, flags ${JSON.stringify(r0.flags)}`);
