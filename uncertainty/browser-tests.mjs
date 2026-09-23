import {pair,CONFIG} from './analysis.mjs';
export function testEngine(api){
  let checks=0;
  const check=(ok,message)=>{checks++;if(!ok)throw Error(message);};
  const near=(a,b)=>Math.abs(a-b)<1e-8*Math.max(1,Math.abs(a),Math.abs(b));
  const p=CONFIG.reference,base=api.evaluate(p);
  const omitted={...p};for(const k of ['compressionFactor','capitalFactor','jouleFurnaceFactor','heatRecovery'])delete omitted[k];
  const defaults=api.evaluate(omitted);
  for(const k of ['cost_usd_per_t','carbon_kgco2e_per_t','compressor_kwh_per_t','toc_musd'])check(near(defaults[k],base[k]),'optional defaults changed '+k);
  for(const name of ['compressionFactor','capitalFactor','jouleFurnaceFactor','heatRecovery']){
    for(const x of [NaN,Infinity,-1,...(name==='heatRecovery'?[1.01]:[0])]){
      let caught=false;try{api.evaluate({...p,[name]:x});}catch(e){caught=e.name==='RangeError';}
      check(caught,name+' invalid override accepted');
    }
  }
  const twice=api.evaluate({...p,compressionFactor:2});
  check(near(twice.compressor_kwh_per_t,2*base.compressor_kwh_per_t),'compressor multiplier does not scale duty');
  check(near(twice.conversion,base.conversion),'process calibration changed chemistry');
  const capital=api.evaluate({...p,capitalFactor:1.5});
  check(near(capital.toc_musd,1.5*base.toc_musd),'capital scale not applied');
  check(near(capital.cost_breakdown_usd_per_t.heat,base.cost_breakdown_usd_per_t.heat),'capital changed fuel cost');
  const noRecovery=api.evaluate({...p,heatRecovery:0});
  check(noRecovery.cost_breakdown_usd_per_t.steamCr===0,'zero recovery still earns steam credit');
  const ordinary=pair(api,p,63,95,1),shared=pair(api,{...p,compressionFactor:1.9,heatRecovery:0.9,capitalFactor:1.5},63,95,1);
  const fired=api.evaluate({...p,mode:'CH',eff:63}),joule=api.evaluate({...p,mode:'JH',eff:95});
  check(near(ordinary.threshold,0.0036*p.gas*fired.purchased_natural_gas_gj_per_t/joule.heater_input_gj_per_t),'burn-surplus threshold disagrees with purchased-fuel balance');
  const sold=pair(api,{...p,tailFate:'sell'},63,95,1);
  check(near(sold.threshold,0.0036*p.gas*95/63),'sold-surplus threshold disagrees with energy-price ratio');
  check(near(ordinary.delta,shared.delta),'shared process costs did not cancel');
  check(near(ordinary.threshold,shared.threshold),'shared uncertainty changed paired break-even');
  check(!near(ordinary.fired,shared.fired),'shared uncertainty did not change absolute cost');
  for(const factor of [0.7,1,1.3]){
    const a=pair(api,p,63,95,factor);
    const f=api.evaluate({...p,mode:'CH',eff:63,elec:a.threshold});
    const j=api.evaluate({...p,mode:'JH',eff:95,jouleFurnaceFactor:factor,elec:a.threshold});
    check(near(f.cost_usd_per_t,j.cost_usd_per_t),'predicted break-even is not a direct API root');
    const f2=api.evaluate({...p,mode:'CH',eff:63}),j2=api.evaluate({...p,mode:'JH',eff:95,jouleFurnaceFactor:factor});
    check(near(a.delta,j2.cost_usd_per_t-f2.cost_usd_per_t),'affine endpoint prediction differs from API');
  }
  const expensive=pair(api,p,63,95,1.3),cheap=pair(api,p,63,95,0.7);
  check(expensive.threshold<cheap.threshold,'higher Joule capital should lower its electricity break-even');
  return {checks,passed:true};
}
