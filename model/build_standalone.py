"""Build EthaneCracker_V07.html: one file that holds the simulator screen, the process model and its data.

Parts:
  - screen: index.html of ~/EthaneCracker-site after patch_index_v07.py;
  - process model: ethane_cracker_model.js (one module, chemical-engineering names, no other file);
  - data blocks: GP parameters and GP validation (multiscale/surrogate.json, validation.json of the model repository),
    and the two literature-case files of the screen (benchmarks/literature.json, results.json).
The page opens with no other file and no network call.
usage: python3 build_standalone.py  -> EthaneCracker_V07.html
"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = Path.home() / 'EthaneCracker-site'
REPO = Path.home() / 'TEA-EthaneCracking'
show = lambda f: subprocess.run(['git', '-C', str(REPO), 'show', '30df335:' + f], capture_output=True, text=True, check=True).stdout


def sub(t, a, b):
    assert t.count(a) == 1, (a[:70], t.count(a))
    return t.replace(a, b)


page = (SITE / 'index.html').read_text()
model = (HERE / 'ethane_cracker_model.js').read_text()
data = {'gp-parameters': show('multiscale/surrogate.json'), 'gp-validation': show('multiscale/validation.json'),
        'literature-cases': (SITE / 'benchmarks/literature.json').read_text(),
        'literature-results': (SITE / 'benchmarks/results.json').read_text()}
for k, v in data.items():
    assert '</script' not in v, k

page = sub(page, '<iframe class="engine" id="engineFrame" src="engine.html" title="Calculation engine"></iframe>', '')
page = sub(page, 'const frame=$("engineFrame");', '')
blocks = ''.join(f'<script type="application/json" id="{k}">{v}</script>\n' for k, v in data.items())
page = sub(page, '<script>', blocks + '<script>\n' + model + '\n</script>\n<script>', ) if page.count('<script>') == 1 else None
assert page, 'expected one inline script in the screen'

old_wait = page[page.index('async function waitApi(){'):page.index('function bind(){')]
page = page.replace(old_wait, '''async function waitApi(){
  // The process model is in this file. Load the GP parameters from the data block in this file.
  const read = id => JSON.parse(document.getElementById(id).textContent);
  try { EthaneCrackerModel.loadGP(read("gp-parameters"), read("gp-validation")); }
  catch (e) { throw new Error("FAILED: GP parameters did not load: " + e.message); }
  return EthaneCrackerModel;
}
''')
page = sub(page, '      fetch("benchmarks/literature.json",{cache:"no-store"}).then(r=>r.json()),\n      fetch("benchmarks/results.json",{cache:"no-store"}).then(r=>r.json())',
           '      Promise.resolve(JSON.parse(document.getElementById("literature-cases").textContent)),\n      Promise.resolve(JSON.parse(document.getElementById("literature-results").textContent))')
page = sub(page, '<p><a href="uncertainty/">Literature calibration &amp; uncertainty →</a></p>',
           '<p class="small">The literature calibration and the uncertainty analysis are not part of this file.</p>')
page = page.replace('<title>Ethane Cracker Model</title>', '<title>Ethane Cracker Simulator</title>')
for bad in ('src="engine.html"', 'fetch(', 'engineFrame', 'contentWindow'):
    assert bad not in page, bad
out = HERE / 'EthaneCracker_V07.html'
out.write_text(page)
print('wrote', out.name, len(page) // 1024, 'kB; external calls:', page.count('fetch('), 'iframes:', page.count('<iframe'))
