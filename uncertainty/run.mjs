// npm install --no-save playwright; npx playwright install chromium
// node uncertainty/run.mjs [--check-only]
import {createRequire} from 'node:module';
import {spawn,execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const require=createRequire(import.meta.url);
let playwright;try{playwright=require('playwright');}catch(e){if(!process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES)throw e;playwright=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');}
const server=spawn('python',['-m','http.server','8127','--bind','127.0.0.1'],{cwd:root,stdio:'ignore'});
let browser;
try{
  for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:8127/engine.html')).ok)break;}catch(_){}await new Promise(r=>setTimeout(r,50));}
  browser=await playwright.chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,
    args:['--no-sandbox','--no-zygote','--single-process','--disable-dev-shm-usage','--disable-gpu']});
  const page=await browser.newPage();
  page.on('console',m=>{if(m.type()==='error')console.error(m.text());});
  await page.goto('http://127.0.0.1:8127/uncertainty/');
  await page.waitForFunction(()=>document.getElementById('engine').contentWindow.ethaneModel?.ready(),null,{timeout:60000});
  const test=await page.evaluate(async()=>{const {testEngine}=await import('./browser-tests.mjs');return testEngine(document.getElementById('engine').contentWindow.ethaneModel);});
  console.log('Engine uncertainty regressions:',test);
  if(!process.argv.includes('--check-only')){
    const report=await page.evaluate(async()=>{const {runAnalysis}=await import('./analysis.mjs');const lit=await(await fetch('../benchmarks/literature.json')).json();return runAnalysis(document.getElementById('engine').contentWindow.ethaneModel,lit);});
    const files=['engine.html','benchmarks/literature.json','multiscale/surrogate.json','uncertainty/analysis.mjs'];
    report.provenance={source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
      source_sha256:Object.fromEntries(files.map(p=>[p,createHash('sha256').update(readFileSync(root+p)).digest('hex')])),
      source_audit:'See uncertainty/README.md. Source values are process-simulation outputs; likelihood discrepancy is analyst-selected.'};
    report.regressions=test;
    writeFileSync(root+'uncertainty/results.json',JSON.stringify(report,null,2)+'\n');
    console.log('Saved uncertainty/results.json');
    await page.reload();await page.waitForFunction(()=>document.body.dataset.uncertaintyStatus==='saved');
    await page.screenshot({path:'/tmp/tea-uncertainty.png',fullPage:true});
    console.log(JSON.stringify(report.analyses.map(a=>({sigma:a.relative_discrepancy_sigma,eff:a.fired_efficiency.parameter_q025_q50_q975,compression:a.compression.parameter_q025_q50_q975,central:a.scenarios.find(s=>s.joule_efficiency_percent===95&&s.joule_furnace_factor===1)})),null,2));
  }
}finally{if(browser)await browser.close();server.kill();}
