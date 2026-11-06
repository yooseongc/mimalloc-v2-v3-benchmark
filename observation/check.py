"""Small correctness checks, independent of performance observations."""
import json
import os
import pathlib
import resource
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
a = json.loads((root/'experiments/memory-behavior-v1/artifacts.json').read_text())
resource.setrlimit(resource.RLIMIT_CORE, (0,0))
env = {k:v for k,v in os.environ.items() if not k.startswith('MIMALLOC_')}
env['LD_PRELOAD'] = a['libraries']['v3.5.3']['path']
cases = {'write_without_allocation': '2 0\n',
         'double_free_rejected': '1 0\n3 1\n3 1\n',
         'live_objects_at_exit': '1 0\nquit\n',
         'complete_lifecycle': '1 0\n2 0\n6 0\n3 1\n6 0\n4 1\nquit\n'}
results = {}
for name, commands in cases.items():
    p = subprocess.run([a['binary']['path'],'8','64'], input=commands,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, env=env, timeout=20)
    assert (p.returncode==0)==(name=='complete_lifecycle'), (name,p.returncode)
    if p.returncode==0:
        rows=[json.loads(line) for line in p.stdout.splitlines()]
        expected=sum((i*37+11)%251 for i in range(8))*64
        assert rows[3]['checksum']==expected
        assert rows[-1]['live_objects']==0
    results[name] = {'passed':True,'exit_code':p.returncode}
(root/'experiments/memory-behavior-v1/correctness.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
