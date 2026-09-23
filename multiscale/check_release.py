"""Verify the deployed GP artifact bundle before running numerical validation."""
import csv
import hashlib
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'multiscale/release_manifest.json').read_text())
for name, expected in manifest['artifacts'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
model = json.loads((root / 'multiscale/surrogate.json').read_text())
datasets = {}
keys = ['temperature_c', 'residence_time_s', 'steam_hc_kgkg', 'pressure_bar', 'ramp_exponent']
for name in ['train', 'holdout']:
    with (root / f'multiscale/data/aramco_{name}.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == manifest[f'{name}_points']
    datasets[name] = {tuple(float(row[k]) for k in keys) for row in rows}
    assert len(datasets[name]) == len(rows), f'duplicate {name} input'
    for point in datasets[name]:
        raw = [point[0], math.log10(point[1]), *point[2:]]
        assert all(lo - 1e-9 <= x <= hi + 1e-9 for x, lo, hi in
                   zip(raw, model['domain_min'], model['domain_max']))
assert not datasets['train'] & datasets['holdout'], 'train/holdout overlap'
assert model['training_points'] == manifest['train_points']
assert abs(10 ** model['domain_max'][1] - 1.5) < 1e-8
print('PASS GP release hashes, point counts, disjoint holdout and 1.5 s domain')
