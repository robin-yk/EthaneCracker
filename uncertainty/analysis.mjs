// Research-only inverse calibration. All process calculations use ethaneModel.
export const CONFIG = {
  seed: 20260923, draws: 512, gridPoints: 161,
  relativeDiscrepancy: [0.05, 0.10, 0.20],
  priors: {firedEfficiency:[45,85],compressionFactor:[0.5,2]},
  scenarios: {heatRecovery:[0.5,0.9],capitalFactor:[0.7,1.5],
    jouleEfficiency:[90,95,98],jouleFurnaceFactor:[0.7,1,1.3]},
  reference: {kinetics:'gp',mode:'CH',eff:60,cot:850,tau:0.35,dilution:0.35,
    pressure:1.5,ramp:1,cap:610,ethane:200,elec:0.07,gas:4,grid:0.36,
    ethaneUp:0.5,lpg:550,steam:9.8,ccf:0.10,labor:5,tle:true,tailFate:'burn',alloc:'expansion',
    compressionFactor:1,heatRecovery:0.7,capitalFactor:1,jouleFurnaceFactor:1}
};
export function rng(seed){let x=seed>>>0;return ()=>{x=(Math.imul(1664525,x)+1013904223)>>>0;return x/4294967296;};}
export function quantiles(values,weights=values.map(()=>1)){
  if(!values.length||values.some(x=>!Number.isFinite(x)))throw Error('Nonfinite or empty quantiles');
  const a=values.map((x,i)=>[x,weights[i]]).sort((a,b)=>a[0]-b[0]);
  const total=weights.reduce((a,b)=>a+b,0);
  return [0.025,0.5,0.975].map(p=>{let c=0;for(const [x,w] of a){c+=w;if(c>=p*total)return x;}return a.at(-1)[0];});
}
export function posterior(states,grid,observed,sigma,predict){
  if(!(sigma>0))throw Error('Positive discrepancy scale required');
  const cells=[];
  for(let i=0;i<grid.length;i++)for(let j=0;j<states.length;j++){
    const prediction=predict(states[j],grid[i]);
    // Trapezoidal quadrature for a uniform continuous prior; equal state weights.
    cells.push({parameter:grid[i],state:j,prediction,
      logWeight:-0.5*((prediction-observed)/sigma)**2+Math.log(i===0||i===grid.length-1?0.5:1)});
  }
  const max=Math.max(...cells.map(c=>c.logWeight));
  const norm=cells.reduce((s,c)=>s+Math.exp(c.logWeight-max),0);
  cells.forEach(c=>{c.weight=Math.exp(c.logWeight-max)/norm;delete c.logWeight;});
  return cells;
}
function summary(cells){return {parameter_q025_q50_q975:quantiles(cells.map(c=>c.parameter),cells.map(c=>c.weight)),
  fitted_prediction_q025_q50_q975:quantiles(cells.map(c=>c.prediction),cells.map(c=>c.weight)),
  edge_mass:cells.filter(c=>c.parameter===cells[0].parameter||c.parameter===cells.at(-1).parameter).reduce((s,c)=>s+c.weight,0)};}
const linspace=(a,b,n)=>Array.from({length:n},(_,i)=>a+(b-a)*i/(n-1));
const inverseCDF=(cells,u)=>{let s=0;for(const c of cells){s+=c.weight;if(u<s)return c;}return cells.at(-1);};
const uniform=(bounds,u)=>bounds[0]+u*(bounds[1]-bounds[0]);
const range=a=>[Math.min(...a),Math.max(...a)];
export function wilson(successes,n){
  const z=1.95996398454,p=successes/n,d=1+z*z/n;
  const m=(p+z*z/(2*n))/d,h=z*Math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;
  return [Math.max(0,m-h),Math.min(1,m+h)];
}
export function fitTau(api,base,target,selector){
  const at=tau=>{const r=api.evaluate({...base,tau});const value=selector(r);return {tau,r,value,d:value-target,error:Math.abs(value-target)/Math.abs(target)};};
  let lo=at(0.02),hi=at(1.5),best=lo.error<hi.error?lo:hi;
  if(lo.d*hi.d<0){for(let i=0;i<38;i++){const m=at(Math.sqrt(lo.tau*hi.tau));if(m.error<best.error)best=m;if(lo.d*m.d<=0)hi=m;else lo=m;}}
  else for(let i=1;i<80;i++){const m=at(0.02*75**(i/79));if(m.error<best.error)best=m;}
  return best;
}
function dry(g){const specs=[['C2H4','c2h4',28.05],['C2H6','c2h6',30.07],['H2','h2',2.016],['CH4','ch4',16.04],['C2H2','c2h2',26.038],['C3','c3',42.08],['C4+','c4plus',56.11]];
  const m=specs.map(([n,k,w])=>[n,g['y_'+k+'_kg_per_kg_ethane']/w]);const sum=m.reduce((s,a)=>s+a[1],0);return Object.fromEntries(m.map(([n,v])=>[n,v/sum]));}
export function buildEvidence(api,literature){
  const chen=literature.cases.find(c=>c.id==='chen-2024').evidence;
  const shin=literature.cases.find(c=>c.id==='shin-2025').evidence;
  const chenStates=chen.pressure_candidates_bar.map(pressure=>{
    const p={...CONFIG.reference,cot:chen.temperature_c,pressure,dilution:18.015/30.07/chen.reactor_ethane_to_steam_vol_ratio,
      cap:chen.ethylene_tph*8000/1000};
    const fit=fitTau(api,p,chen.outlet_c2h6_molfrac,r=>dry(r.gp_mean).C2H6);
    if(fit.error>0.005)throw Error('Chen composition constraint failed');
    return {inputs:{...p,tau:fit.tau},result:fit.r,dry:dry(fit.r.gp_mean)};
  });
  const fresh=shin.ethane_kgh/shin.ethylene_kgh,shinStates=[];
  for(let cot=800;cot<=900;cot+=5)for(let pressure=1;pressure<=5;pressure+=0.5){
    const p={...CONFIG.reference,cot,pressure,dilution:shin.steam_hc_kgkg,cap:shin.capacity_tpy/1000,
      gas:shin.gas_usd_per_gj,elec:shin.electricity_usd_per_kwh,lpg:shin.c3plus_price_usd_per_t,
      grid:shin.grid_kgco2e_per_kwh,ethaneUp:shin.ethane_upstream_kgco2e_per_t/1000/fresh};
    const fit=fitTau(api,p,fresh,r=>r.fresh_ethane_kg_per_kg);
    if(fit.error<0.005)shinStates.push({inputs:{...p,tau:fit.tau},result:fit.r});
  }
  if(!shinStates.length)throw Error('No Shin feed-constrained states');
  return {chen,shin,chenStates,shinStates};
}
function heldout(api,e,heatCells,compCells){
  const w=heatCells.map(c=>c.weight);
  const scope=heatCells.map(c=>api.evaluate({...e.shinStates[c.state].inputs,eff:c.parameter}).carbon_scopes_kgco2e_per_t.scope1);
  const c3=heatCells.map(c=>{const r=e.shinStates[c.state].result;return r.c3_kg_per_kg+r.c4plus_kg_per_kg;});
  const cw=compCells.map(c=>c.weight);
  const item=(name,observed,v,weights)=>{const q=quantiles(v,weights);return {name,observed,prediction_q025_q50_q975:q,inside_parameter_interval:observed>=q[0]&&observed<=q[2]};};
  return [item('Shin on-site GHG (kgCO2e/t)',e.shin.onsite_ghg_kgco2e_per_t,scope,w),
    item('Shin C3+ (kg/kg ethylene)',e.shin.c3plus_kgh/e.shin.ethylene_kgh,c3,w),
    ...['C2H4','H2','CH4'].map(k=>item('Chen dry '+k+' (mol/mol)',e.chen['outlet_'+k.toLowerCase()+'_molfrac'],compCells.map(c=>e.chenStates[c.state].dry[k]),cw)),
    item('Chen fresh ethane (kg/kg ethylene)',e.chen.ethane_tph/e.chen.ethylene_tph,compCells.map(c=>e.chenStates[c.state].result.fresh_ethane_kg_per_kg),cw),
    item('Chen reactor duty: boundary differs (GJ/t)',e.chen.reactor_heat_gjh/e.chen.ethylene_tph,compCells.map(c=>e.chenStates[c.state].result.mechanism_zone_heat_gj_per_t),cw)];
}
// Endpoints are sufficient because this engine is affine in electricity price.
export function pair(api,p,effF,effJ,furnaceFactor){
  const f0=api.evaluate({...p,mode:'CH',eff:effF,elec:0});
  const f1=api.evaluate({...p,mode:'CH',eff:effF,elec:0.1});
  const j0=api.evaluate({...p,mode:'JH',eff:effJ,jouleFurnaceFactor:furnaceFactor,elec:0});
  const j1=api.evaluate({...p,mode:'JH',eff:effJ,jouleFurnaceFactor:furnaceFactor,elec:0.1});
  if([f0,f1,j0,j1].some(r=>!r.economically_operable))throw Error('Non-operable uncertainty sample');
  const intercept=j0.cost_usd_per_t-f0.cost_usd_per_t;
  const slope=((j1.cost_usd_per_t-f1.cost_usd_per_t)-intercept)/0.1;
  if(!(slope>0))throw Error('Expected positive differential electricity demand');
  const threshold=-intercept/slope;
  return {threshold,delta:intercept+slope*p.elec,
    fired:f0.cost_usd_per_t+(f1.cost_usd_per_t-f0.cost_usd_per_t)*p.elec/0.1,
    joule:j0.cost_usd_per_t+(j1.cost_usd_per_t-j0.cost_usd_per_t)*p.elec/0.1};
}
export async function runAnalysis(api,literature,progress=()=>{},config=CONFIG){
  progress('Inferring literature reactor states');await new Promise(r=>setTimeout(r,0));
  const e=buildEvidence(api,literature),report={schema:'ethane-inverse-calibration-v1',config,
    interpretation:'Conditional model calibration against published process simulations. Priors and discrepancy scales are analyst assumptions; intervals are not experimental confidence intervals.',
    data_roles:{conditioning:['Chen residual ethane','Shin fresh ethane demand'],calibration:['Chen compressor power','Shin total combustion energy'],
      held_out:'Other outputs from the same studies, not independent-study validation',
      excluded:['MSP versus screening cost: different financial boundaries','Equipment cost versus installed TOC: different capital boundaries','Wang: reactor-inlet and kinetic-model mismatch']},
    identifiability:{firedEfficiency:'effective heat-demand-to-combustion ratio conditional on reconstructed states',compressionFactor:'effective compressor-duty multiplier; not a measured isentropic efficiency',heatRecovery:'not updated by these observations',capitalFactor:'not updated by these observations',jouleFurnaceFactor:'scenario only; no Joule equipment cost observation'},
    evidence:{chen_pressure_scenarios:e.chenStates.map(s=>s.inputs.pressure),chen_tau_range:range(e.chenStates.map(s=>s.inputs.tau)),
      shin_accepted_states:e.shinStates.length,shin_tau_range:range(e.shinStates.map(s=>s.inputs.tau)),
      compressor_kwh_per_t:e.chen.compressor_mw*1000/e.chen.ethylene_tph,combustion_gj_per_t:e.shin.combustion_energy_gj_per_t},
    analyses:[]};
  for(const relativeSigma of config.relativeDiscrepancy){
    const compObs=report.evidence.compressor_kwh_per_t,heatObs=report.evidence.combustion_gj_per_t;
    const comp=posterior(e.chenStates,linspace(...config.priors.compressionFactor,config.gridPoints),compObs,relativeSigma*compObs,(s,x)=>s.result.compressor_kwh_per_t*x);
    const heat=posterior(e.shinStates,linspace(...config.priors.firedEfficiency,config.gridPoints),heatObs,relativeSigma*heatObs,(s,x)=>s.result.heater_input_gj_per_t*60/x);
    const a={relative_discrepancy_sigma:relativeSigma,compression:summary(comp),fired_efficiency:summary(heat),
      heldout:heldout(api,e,heat,comp),scenarios:[]};
    for(const effJ of config.scenarios.jouleEfficiency)for(const furnaceFactor of config.scenarios.jouleFurnaceFactor){
      const random=rng(config.seed),samples=[];
      progress('Paired economics: discrepancy '+relativeSigma+', Joule '+effJ+'%, furnace factor '+furnaceFactor);
      await new Promise(r=>setTimeout(r,0));
      for(let i=0;i<config.draws;i++){
        const cf=inverseCDF(comp,random()).parameter,ef=inverseCDF(heat,random()).parameter;
        const p={...config.reference,compressionFactor:cf,heatRecovery:uniform(config.scenarios.heatRecovery,random()),capitalFactor:uniform(config.scenarios.capitalFactor,random())};
        samples.push(pair(api,p,ef,effJ,furnaceFactor));
      }
      const share=samples.filter(s=>s.delta<0).length/samples.length;
      a.scenarios.push({joule_efficiency_percent:effJ,joule_furnace_factor:furnaceFactor,
        fired_cost_q025_q50_q975:quantiles(samples.map(s=>s.fired)),joule_cost_q025_q50_q975:quantiles(samples.map(s=>s.joule)),
        delta_cost_q025_q50_q975:quantiles(samples.map(s=>s.delta)),
        breakeven_electricity_q025_q50_q975:quantiles(samples.map(s=>s.threshold)),
        conditional_joule_cheaper_fraction:share,monte_carlo_standard_error:Math.sqrt(share*(1-share)/samples.length),
        monte_carlo_wilson95:wilson(Math.round(share*samples.length),samples.length),
        electricity_sweep:Array.from({length:21},(_,i)=>{const price=i*0.005;const count=samples.filter(s=>price<s.threshold).length;return {usd_per_kwh:price,conditional_fraction:count/samples.length,monte_carlo_wilson95:wilson(count,samples.length)};})});
    }
    report.analyses.push(a);
  }
  return report;
}
