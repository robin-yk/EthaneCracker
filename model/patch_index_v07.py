"""Patch the EthaneCracker simulator screen (robin-yk/EthaneCracker, index.html at commit e9bfa6f) for the V07 engine.

Changes, all in the existing design:
  - flowsheet: T-302 deethanizer between the T-201 cold box and the T-301 C2 splitter; S-303 C3+ leaves the
    deethanizer bottoms to T-401/T-402 (depropanizer, debutanizer);
  - model explorer: T-302 and T-401/T-402 blocks with results, inputs and setup;
  - R-101 block: fired radiant and overall efficiency, convection steam, tube metal temperature, duty per coil;
  - cost breakdown: steam includes the heavy-ends reboiler steam, so the rows add up to the cost;
  - Reports: break-even, plant checks (OK/FAILED at 10 %), by-product shadow prices, fired/electric waterfall.
usage: python3 patch_index_v07.py <EthaneCracker repo>   (rewrites index.html in that repo)
"""
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).expanduser()
src = subprocess.run(['git', '-C', str(repo), 'show', 'e9bfa6f:index.html'], capture_output=True, text=True, check=True).stdout


def sub(t, a, b):
    assert t.count(a) == 1, (a[:70], t.count(a))
    return t.replace(a, b)


s = src
s = sub(s, 'grid-template-columns:repeat(6,1fr);gap:28px', 'grid-template-columns:repeat(7,1fr);gap:22px')
s = sub(s, '.flowcanvas .flow{padding:84px 64px 82px;min-height:350px;gap:28px;align-items:start;grid-template-columns:repeat(6,minmax(0,1fr))}', '.flowcanvas .flow{padding:84px 48px 82px;min-height:350px;gap:20px;align-items:start;grid-template-columns:repeat(7,minmax(0,1fr))}')
s = sub(s, '  while(Date.now()-t0<30000){', '  while(Date.now()-t0<120000){   // V07: the GP is parsed from the engine file (6 MB); allow 120 s')
COL = '<svg viewBox="0 0 72 72"><rect x="24" y="4" width="24" height="62" rx="11"/><path d="M24 15 H48 M24 55 H48 M24 24 H43 V27 M29 34 H48 M24 44 H43 V47 M16 36 H24 M48 15 H60 M48 57 H60 M29 65 V70 H43 V65"/></svg>'
s = sub(s, '          <div class="unit" data-block="splitter">',
        '          <div class="unit" data-block="deethanizer">\n'
        f'            <div class="equipbox">{COL}</div>\n'
        '            <div class="equipname">T-302<br><span>DEETHANIZER</span></div>\n'
        '            <div class="u" id="uDeC2">—</div><div class="u" id="uDeC2b">—</div>\n'
        '          </div>\n'
        '          <div class="unit" data-block="splitter">')
s = sub(s, '        <div class="item" data-tree-block="splitter">Blocks / T-301 C2 Splitter</div>',
        '        <div class="item" data-tree-block="deethanizer">Blocks / T-302 Deethanizer</div>\n'
        '        <div class="item" data-tree-block="splitter">Blocks / T-301 C2 Splitter</div>\n'
        '        <div class="item" data-tree-block="heavyends">Blocks / T-401, T-402 C3, C4 Columns</div>')
s = sub(s, '<span class="streamtag st-c3" data-stream="c3">S-303 C3+</span>',
        '<span class="streamtag st-c3" data-stream="c3">S-303 C3+ TO T-401/T-402</span>')

# flowsheet connections
s = sub(s, "[['reactor',62,'compressor',8],['compressor',64,'converter',9],['converter',63,'coldbox',13],['coldbox',59,'splitter',16]].forEach(([a,x,b,y])=>line([port(a,x,36),port(b,y,36)]));",
        "[['reactor',62,'compressor',8],['compressor',64,'converter',9],['converter',63,'coldbox',13],['coldbox',59,'deethanizer',16]].forEach(([a,x,b,y])=>line([port(a,x,36),port(b,y,36)]));\n"
        "  {const a=port('deethanizer',60,15),b=port('splitter',16,36),mx=(a[0]+b[0])/2;line([a,[mx,a[1]],[mx,b[1]],b]);}")
s = sub(s, "  const c3=port('coldbox',50,62),c3x=port('splitter',0,36)[0]-16;\n  line([c3,[c3[0],c3[1]+14],[c3x,c3[1]+14],[c3x,h-72],[c3x+36,h-72]],'#9a6123','arro');",
        "  const c3=port('deethanizer',36,70),c3x=c3[0];\n  line([c3,[c3x,h-72],[c3x+36,h-72]],'#9a6123','arro');")

# results text in render()
s = sub(s, '  $("uSplit").textContent=fmt(result.splitter_kwh_per_t,0)+" kWh/t";',
        '  $("uSplit").textContent=fmt(result.splitter_kwh_per_t,0)+" kWh/t";\n'
        '  const he=result.heavy_ends||{};\n'
        '  $("uDeC2").textContent=fmt(result.deethanizer_kwh_per_t,0)+" kWh/t";\n'
        '  $("uDeC2b").textContent=fmt(he.reboiler_steam_gj_per_t,2)+" GJ/t reboiler steam";\n'
        '  const fu=result.furnace;\n'
        '  $("uFeed").textContent=fu?("radiant "+pct(fu.radiantEfficiency)+" · overall "+pct(fu.overallEfficiency)):(fmt(result.fresh_ethane_kg_per_kg,3)+" kg fresh + "+fmt(result.recycle_ethane_kg_per_kg,3)+" kg recycle");')
s = sub(s, '$("scope").textContent="The reactor outlet sets the recycle and cracked-gas load. AC-201 selectively hydrogenates acetylene before the cold box and C₂ splitter; the remaining compression, refrigeration, and fractionation duties are estimated from the resulting flows. The separation models are screening correlations.";',
        '$("scope").textContent="The reactor outlet sets the recycle and cracked-gas load. The fired furnace is a radiant and convection heat balance; the tube metal temperature is checked against 1150 °C. AC-201 selectively hydrogenates acetylene before the cold box (Peng–Robinson flash, CoolProp refrigeration cascade). T-302 sends the C₂ cut to the C₂ splitter and the C₃+ to T-401/T-402 (shortcut columns).";')
s = sub(s, '["Steam",L.dilSteam||0]', '["Steam",(L.dilSteam||0)+(L.heavyEnds||0)]')

# block properties
s = sub(s, '    ["C2H4 selectivity",pct(result.selectivity_mass)],["Useful heat",fmt(result.reactor_useful_heat_gj_per_t,3)+" GJ/t"],',
        '    ["C2H4 selectivity",pct(result.selectivity_mass)],["Useful heat",fmt(result.reactor_useful_heat_gj_per_t,3)+" GJ/t"],\n'
        '    ["Purchased heat",fmt(result.heater_input_gj_per_t,3)+" GJ/t"],\n'
        '    ["Fired radiant efficiency",result.furnace?pct(result.furnace.radiantEfficiency):"—"],\n'
        '    ["Fired overall efficiency",result.furnace?pct(result.furnace.overallEfficiency):"—"],\n'
        '    ["Convection steam",fmt(result.convection_steam_gj_per_t,2)+" GJ/t"],\n'
        '    ["Tube metal temperature, max",result.coil_heat?fmt(result.coil_heat.tubeMetalTemperatureMaxC,0)+" °C ("+result.coil_heat.tmtStatus+")":"—"],\n'
        '    ["Radiant duty per coil",result.coil_heat?fmt(result.coil_heat.dutyPerCoil_kW,1)+" kW":"—"],')
s = sub(s, '  product:()=>[\n    ["Stream","P-401 · ETHYLENE"]',
        '  deethanizer:()=>{const d=(result.heavy_ends||{});return [["Block","T-302 · DEETHANIZER"],["Pressure","25 bar"],\n'
        '    ["Condenser refrigeration",fmt(result.deethanizer_kwh_per_t,1)+" kWh/t"],["Reboiler steam (all heavy-ends columns)",fmt(d.reboiler_steam_gj_per_t,3)+" GJ/t"],\n'
        '    ["Overhead","C2 cut to T-301"],["Bottoms","C3 + C4 to T-401"],["Method","Fenske-Underwood-Gilliland shortcut"],["Status","CALCULATED"]]},\n'
        '  heavyends:()=>[["Block","T-401 DEPROPANIZER · T-402 DEBUTANIZER"],["C3 product",fmt(result.c3_kg_per_kg,5)+" kg/kg C2H4"],\n'
        '    ["C4 product",fmt(result.c4plus_kg_per_kg-result.c5plus_kg_per_kg,5)+" kg/kg C2H4"],["C5+ pyrolysis gasoline",fmt(result.c5plus_kg_per_kg,5)+" kg/kg C2H4"],\n'
        '    ["Cooling water",fmt((result.heavy_ends||{}).cooling_water_gj_per_t,3)+" GJ/t"],["Status","CALCULATED"]],\n'
        '  product:()=>[\n    ["Stream","P-401 · ETHYLENE"]')
s = sub(s, '  product:()=>[["Product","polymer-grade ethylene"],["Basis","1.000 kg"]]\n};',
        '  deethanizer:()=>[["Feed","cold-box liquid (C2, C3, C4)"],["Key recovery","99.5 %"],["Reflux","1.2 × minimum"],["Pressure","25 bar"]],\n'
        '  heavyends:()=>[["T-401 feed","T-302 bottoms (C3 + C4)"],["T-402 feed","T-401 bottoms (C4) + quench C5+"],["Pressures","16 bar / 5 bar"]],\n'
        '  product:()=>[["Product","polymer-grade ethylene"],["Basis","1.000 kg"]]\n};')
s = sub(s, '  coldbox:()=>[["Model","Carnot-based refrigeration screening"],["Second-law efficiency","35%"],["Recovery","99.5%"]],',
        '  coldbox:()=>[["Model","Peng–Robinson flash at 30 bar"],["Refrigeration","propylene / ethylene / methane cascade (CoolProp)"],["Recovery","99.5%"]],\n'
        '  deethanizer:()=>[["Relative volatility","Peng–Robinson at 25 bar"],["Condenser","propylene cycle, COP 3.49"],["Reboiler","low-pressure steam"]],\n'
        '  heavyends:()=>[["Condensers","cooling water"],["Reboilers","low-pressure steam"],["Capital","Towler & Sinnott 2022 sizing, anchor-plant basis"]],')

# Reports
s = sub(s, '  <div class="citebox"><h3>Process reference</h3>',
        '  <div class="hero"><div><h2>Break-even</h2><p>Electric and fired heating at the current reactor condition.</p></div></div>\n'
        '  <div class="tablewrap"><table><tbody id="repBreak"></tbody></table></div>\n'
        '  <div class="hero" style="padding-top:20px"><div><h2>Plant checks</h2><p>Model against published commercial furnaces. Status OK within 10 %. No parameter is fitted to these numbers except the tube metal temperature.</p></div></div>\n'
        '  <div class="tablewrap"><table><thead><tr><th>Check</th><th>Model</th><th>Published</th><th>Deviation</th><th>Status</th><th>Source</th></tr></thead><tbody id="repChecks"></tbody></table></div>\n'
        '  <div class="hero" style="padding-top:20px"><div><h2>By-product shadow prices</h2><p>Cost and carbon per kg of a product per kg ethylene at the current condition. The ethane feed for the mass balance is not included.</p></div></div>\n'
        '  <div class="tablewrap"><table><thead><tr><th>Product</th><th>USD/t per kg/kg</th><th>kg CO2e/t per kg/kg</th><th>Cost items that move</th></tr></thead><tbody id="repShadow"></tbody></table></div>\n'
        '  <div class="hero" style="padding-top:20px"><div><h2>Fired against electric heating</h2><p>(a) fired best point, (b) electric at the same point, (c) electric best point.</p></div><button id="repWfRun">Calculate (about 30 s)</button></div>\n'
        '  <div class="tablewrap"><table><thead><tr><th>Quantity</th><th>(a) fired, best</th><th>(b) electric, same point</th><th>(c) electric, best</th></tr></thead><tbody id="repWf"></tbody></table></div>\n'
        '  <div class="citebox" id="repWfItems" style="white-space:normal"></div>\n'
        '  <div class="citebox"><h3>Process reference</h3>')
s = sub(s, '  if(id==="compare")renderCompare();\n}',
        '  if(id==="compare")renderCompare();\n  if(id==="cite")renderReports();\n}\n'
        'function renderReports(){\n'
        '  const v=api&&api.analysis; if(!v)return;\n'
        '  const tr=c=>"<tr>"+c.map(x=>"<td>"+(typeof x==="number"?fmt(x,Math.abs(x)>=100?1:3):x)+"</td>").join("")+"</tr>";\n'
        '  const o={...state,kinetics:"gp"}, be=v.breakEven(o);\n'
        '  $("repBreak").innerHTML=tr(["Break-even electricity price",fmt(100*be.electricity_usd_per_kwh,3)+" ¢/kWh"])+tr(["Break-even grid emission factor",fmt(be.grid_kg_per_kwh,3)+" kg CO2e/kWh"]);\n'
        '  $("repChecks").innerHTML=v.plantChecks(o).checks.map(c=>tr([c.name,fmt(c.model_value,4)+" "+c.unit,c.published+" "+c.unit,fmt(100*c.deviation,1)+" %",\'<b class="\'+(c.status==="OK"?"good":"warn")+\'">\'+c.status+"</b>",c.source])).join("");\n'
        '  $("repShadow").innerHTML=v.shadowPrices(o).map(r=>tr([r.lump,r.cost_USD_per_t_per_kg_per_kg,r.carbon_kg_per_t_per_kg_per_kg,Object.entries(r.items).map(([k,x])=>k+" "+(x>0?"+":"")+x.toFixed(0)).join("; ")])).join("");\n'
        '  $("repWfRun").onclick=()=>{$("repWf").innerHTML=tr(["calculating","","",""]);setTimeout(()=>{const w=v.waterfall(o);\n'
        '    const items=x=>Object.entries(x).map(([k,y])=>k+" "+(y>0?"+":"")+y.toFixed(0)).join("; ");\n'
        '    $("repWf").innerHTML=Object.keys(w.fired_best).map(k=>tr([k.replace(/_/g," "),w.fired_best[k],w.electric_same_condition[k],w.electric_best[k]])).join("");\n'
        '    $("repWfItems").innerHTML="<h3>Cost change (a) → (b), USD/t</h3><p>"+items(w.step_a_to_b)+"</p><h3>Cost change (b) → (c), USD/t</h3><p>"+items(w.step_b_to_c)+"</p>";},30);};\n'
        '}')
# one place per assumption: the export-steam price comes from the engine (4.4 USD/GJ), not from the presets
assert s.count(",lpg:550,steam:9.8}")==2 and s.count(",lpg:443,steam:9.8}")==1
s = s.replace(",lpg:550,steam:9.8}", ",lpg:550}").replace(",lpg:443,steam:9.8}", ",lpg:443}")
# C3+ line leaves the deethanizer bottoms on the right side, clear of the unit labels
s = sub(s, "  const c3=port('deethanizer',36,70),c3x=c3[0];\n  line([c3,[c3x,h-72],[c3x+36,h-72]],'#9a6123','arro');",
        "  const c3=port('deethanizer',48,57),dU=canvas.querySelector('[data-block=\"deethanizer\"]').getBoundingClientRect(),sU=canvas.querySelector('[data-block=\"splitter\"]').getBoundingClientRect(),c3x=(dU.right+sU.left)/2-base.left;\n  line([c3,[c3x,c3[1]],[c3x,h-72],[c3x+36,h-72]],'#9a6123','arro');")
s = sub(s, ".flowcanvas .flow{padding:84px 48px 82px;min-height:350px;gap:20px;", ".flowcanvas .flow{padding:84px 14px 82px;min-height:350px;gap:14px;")
s = sub(s, '<dt>Cold box</dt><dd>Carnot-screening duty</dd>', '<dt>Fired furnace</dt><dd>radiant and convection heat balance; tube metal temperature check</dd><dt>Cold box</dt><dd>Peng–Robinson flash; propylene/ethylene/methane refrigeration cascade</dd>')
s = sub(s, '<dt>C₂ splitter</dt><dd>FUG shortcut</dd>', '<dt>C₂ splitter</dt><dd>FUG shortcut</dd><dt>Heavy ends</dt><dd>deethanizer, depropanizer, debutanizer (FUG shortcut)</dd>')
(repo / 'index.html').write_text(s)
print('patched index.html')
