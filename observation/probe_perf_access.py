"""Verify perf access without changing host settings; retain diagnostics."""
import json
import pathlib
import subprocess
import sys

root=pathlib.Path(__file__).resolve().parents[1]
out=root/'experiments/perf-access-v1'
out.mkdir(exist_ok=False)
work=[sys.executable,'-c','sum(i*i for i in range(10000000))']
commands=[['perf','stat','-e','task-clock:u,cycles:u,instructions:u']+work,
          ['perf','record','-F','99','-e','cycles:u','--call-graph','dwarf','-o',str(out/'perf.data'),'--']+work,
          ['perf','report','--stdio','--no-children','-i',str(out/'perf.data')]]
records=[]
for i,cmd in enumerate(commands):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=30)
    (out/('probe-{}.stdout'.format(i))).write_text(p.stdout)
    (out/('probe-{}.stderr'.format(i))).write_text(p.stderr)
    records.append(dict(command=cmd,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
    print(i,p.returncode,p.stderr[:1000],p.stdout[:1200],flush=True)
result=dict(kernel=subprocess.check_output(['uname','-a'],universal_newlines=True),
    perf_event_paranoid=pathlib.Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip(),
    kptr_restrict=pathlib.Path('/proc/sys/kernel/kptr_restrict').read_text().strip(),
    container_security='seccomp=unconfined; no added capabilities; network none',records=records)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
assert all(x['exit_code']==0 for x in records)
assert 'Samples:' in records[-1]['stdout']
