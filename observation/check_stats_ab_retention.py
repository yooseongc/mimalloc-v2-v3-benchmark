"""Source-predicted attribution control; same upstream v3.5.3 binary, no patch."""
import hashlib
import json
import os
import pathlib
import subprocess

root = pathlib.Path('/work')
out = root / 'experiments/thread-stats-ab-retention-v353'
build = root / 'build/thread-stats-ab-retention-v353'
out.mkdir(parents=True, exist_ok=True)
build.mkdir(parents=True, exist_ok=True)
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
lib = json.loads((root / 'experiments/memory-behavior-v1/artifacts.json').read_text())['libraries']['v3.5.3']
assert sha(lib['path']) == lib['sha256']
base = root / 'observation/thread_stats_ab.cpp'
source = build / 'probe.cpp'
# Preserve the original probe. The only addition logs the actual option value.
needle = '  heap=API(mi_heap_new)();'
addition = r'  std::printf("{\"page_full_retain\":%ld}\n",API(mi_option_get)(mi_option_page_full_retain));'
assert base.read_text().count(needle) == 1
source.write_text(base.read_text().replace(needle, addition + '\n' + needle))
binary = build / 'probe'
command = ['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
           '-I/work/extern/mimalloc-v3.5.3/include', str(source), '-pthread', '-ldl', '-o', str(binary)]
subprocess.run(command, check=True)
runs = []
for retain in (-1, 0, 1, 2, 4):
    for size in (64, 4096):
        env = {k: v for k, v in os.environ.items() if not k.startswith('MIMALLOC_') and k != 'LD_PRELOAD'}
        env.update(MIMALLOC_COLLECT_MERGES_STATS='0', MIMALLOC_PAGE_FULL_RETAIN=str(retain))
        run = subprocess.run([str(binary), lib['path'], str(size)], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=20)
        name = 'retain-{}-{}'.format(retain, size)
        (out / (name + '.jsonl')).write_text(run.stdout)
        (out / (name + '.stderr')).write_text(run.stderr)
        assert run.returncode == 0, (name, run.returncode, run.stderr)
        lines = [json.loads(s) for s in run.stdout.splitlines()]
        option, config, stages = lines[0], lines[1], lines[2:]
        assert option['page_full_retain'] == retain
        assert config['collect_merges_stats'] == 0 and config['purge_delay'] == 1000
        assert len(stages) == 8
        expected_a = 1000 if size == 64 or retain == -1 else 10 + 15 * retain
        final = next(s for s in stages if s['stage'] == 'both_collected_again')
        for s in stages:
            assert s['A_free_calls'] == 0 and s['B_alloc_calls'] == 0
        assert final['A_alloc_calls'] == final['B_free_calls'] == 1000
        assert final['A']['derived_freed_bytes'] == expected_a * size, (name, final)
        assert final['B']['derived_freed_bytes'] == (1000 - expected_a) * size, (name, final)
        assert final['sum']['current_bytes'] == 0
        assert final['sum']['allocated_bytes'] == size * 1000
        assert final['sum']['allocated_count'] == 1000
        assert stages[-1]['parent']['derived_freed_bytes'] == size * 1000
        runs.append(dict(name=name, option=option, config=config, stages=stages, validated=True))
        print(name, 'PASS', 'freed-equivalent objects: A=', expected_a, 'B=', 1000-expected_a, flush=True)
(out / 'results.json').write_text(json.dumps(dict(
    library=lib, base_source_sha256=sha(base), generated_source=str(source),
    generated_source_sha256=sha(source), binary_sha256=sha(binary),
    runner_sha256=sha(__file__), build_command=command, results=runs), indent=2) + '\n')
