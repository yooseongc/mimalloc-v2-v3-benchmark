"""Mechanism checks on the existing binaries, separate from measured runs."""
import itertools
import json
import os
import random
import subprocess
import time
from unittest.mock import patch

import dev3_20261122 as base

E = base.ROOT/'experiments/dev3-20261122-mechanisms-v1'


def lifecycle(profile, thp):
    original = subprocess.Popen

    def launch(*args, **kwargs):
        kwargs['env']['MIMALLOC_ALLOW_THP'] = str(thp)
        return original(*args, **kwargs)

    with patch.object(subprocess, 'Popen', launch):
        row = base.life.run_one(profile, 'remote', 32768, .05)
    assert row['valid'], row.get('error')
    phases = [p for p in row['phases'] if p['name'] in ('free_half', 'free_rest')]
    before = next(p for p in row['checkpoints'] if p['name']=='verify_all')
    return dict(profile=profile, allow_thp=thp, before=before, phases=phases,
                ns_per_free=sum(p['wall_ns'] for p in phases)/32768)


def trace(profile, size_gib):
    artifacts = json.loads((base.con.EXP/'artifacts.json').read_text())
    lib = artifacts['libraries'][profile]
    assert base.con.sha(lib['path'])==lib['sha256']
    binary = base.BUILD/'concurrent'
    assert base.con.sha(binary)==artifacts['binary']['sha256']
    path = E/('{}-{}GiB.strace'.format(profile,size_gib))
    args = ['strace','-f','-c','-e','trace=mprotect,madvise,mmap,munmap','-E','LD_PRELOAD='+lib['path'],
            '-o',str(path),str(binary),'2','262144',str(128*2**20),str(size_gib*4096),'0','0']
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True) as child:
        ready = json.loads(child.stdout.readline())
        assert ready['library']==lib['path']
        child.stdin.write('go\n')
        child.stdin.flush()
        assert json.loads(child.stdout.readline())['started']
        while True:
            child.stdin.write('sample\n')
            child.stdin.flush()
            result = json.loads(child.stdout.readline())
            if result['done']:
                break
            time.sleep(.02)
        assert result['consumed']==size_gib*4096 and result['live_estimate_bytes']==0
        child.stdin.write('quit\n')
        child.stdin.flush()
        assert child.wait(timeout=20)==0


def main():
    E.mkdir(exist_ok=True)
    os.sched_setaffinity(0,{10})
    order = list(itertools.product(['release-ON-0','dev3-ON-0'],[0,2]))
    rng = random.Random(2026112202)
    rows = []
    for rep in range(7):
        rng.shuffle(order)
        for profile, thp in order:
            rows.append(dict(rep=rep, **lifecycle(profile,thp)))
    base.con.save(E/'thp.json',rows)
    for profile in ['dev3-ON-0','dev3-ON-1','dev3-OFF-0']:
        for gib in [1,2]:
            trace(profile,gib)


if __name__=='__main__':
    main()
