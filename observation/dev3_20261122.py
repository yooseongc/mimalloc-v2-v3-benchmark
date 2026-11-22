"""Pinned dev3 / release factorial. Run inside the Rocky benchmark image."""
import itertools
import json
import math
import os
import random
import shlex
import subprocess
from pathlib import Path

import run as life
import run_concurrent as con

ROOT = con.ROOT
NS = 'dev3-20261122-v1'
EXP = ROOT / 'experiments' / NS
BUILD = ROOT / 'build' / NS
OUT = ROOT / 'results' / NS
SOURCES = {
    'release': ('mimalloc-v3.7.0', '1ed67b5156a763441d2ec3c20221a7b3cd866129'),
    'dev3': ('mimalloc-dev3-15d1247d', '15d1247d63b94fef02e508a8feffead8d7ac300c'),
}
SIZES = [4096, 65536, 262144]
GIB = 2**30
for module, name in [(con, 'concurrent'), (life, 'lifecycle')]:
    module.EXP = EXP / name
    module.BUILD = BUILD


def prepare():
    libraries = {}
    environment = dict(cpu=con.cmd(['lscpu']), kernel=con.cmd(['uname', '-a']),
                       compiler=con.cmd(['cc', '--version']), glibc=con.cmd(['ldd', '--version']),
                       rocky=con.read('/etc/rocky-release'), cgroup=con.cg(),
                       thp=con.read('/sys/kernel/mm/transparent_hugepage/enabled'), image=life.IMAGE)
    for version, (directory, commit) in SOURCES.items():
        src = ROOT / 'extern' / directory
        git = ['git', '-c', 'safe.directory='+str(src), '-C', str(src)]
        assert con.cmd(git+['rev-parse', 'HEAD']) == commit
        assert not con.cmd(git+['status', '--porcelain', '--untracked-files=no'])
        for secure, large in itertools.product(['OFF', 'ON'], [0, 1]):
            profile = '{}-{}-{}'.format(version, secure, large)
            dest = BUILD / profile
            args = ['cmake', '-S', str(src), '-B', str(dest), '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG', '-DMI_OVERRIDE=ON', '-DMI_BUILD_SHARED=ON',
                    '-DMI_BUILD_STATIC=OFF', '-DMI_BUILD_OBJECT=OFF', '-DMI_BUILD_TESTS=OFF',
                    '-DMI_MTE=OFF', '-DMI_PAC=OFF', '-DMI_SECURE='+secure,
                    '-DCMAKE_C_FLAGS=-DMI_ENABLE_LARGE_PAGES='+str(large)]
            with (BUILD/(profile+'.log')).open('w') as log:
                subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
                subprocess.run(['cmake', '--build', str(dest), '-j', '4'], stdout=log, stderr=subprocess.STDOUT, check=True)
            flags = (dest/'CMakeFiles/mimalloc.dir/flags.make').read_text()
            fields = dict(line.split(' = ', 1) for line in flags.splitlines() if ' = ' in line)
            cc = ['cc'] + sum((shlex.split(fields[k]) for k in ['C_DEFINES','C_INCLUDES','C_FLAGS']), [])
            macros = con.cmd(cc+['-dM','-E','-include','mimalloc/types.h','-x','c','/dev/null']).splitlines()
            for key, value in [('MI_ENABLE_LARGE_PAGES', large), ('MI_SECURE', 4 if secure=='ON' else 0)]:
                assert '#define {} {}'.format(key, value) in macros
            lib, = dest.glob('libmimalloc*.so')
            libraries[profile] = dict(commit=commit, path=str(lib.resolve()), sha256=con.sha(lib),
                                      mi_version=30700, flags=flags, cmake_command=args)
            print('built', profile, flush=True)
    for module, name in [(con,'concurrent'), (life,'lifecycle')]:
        source = ROOT/'observation'/(name+'.cpp')
        if name == 'concurrent':
            # Same size sweep adaptation as the allocation-size experiment, with default runtime policy.
            code = source.read_text().replace('constexpr size_t batch=256;', 'static size_t batch;')
            code = code.replace('  if((pair_count', '  batch=object_bytes ? 262144/object_bytes : 0;\n  if((pair_count')
            code = code.replace('object_bytes<64||object_bytes>4096', '(object_bytes!=4096&&object_bytes!=65536&&object_bytes!=262144)')
            source = BUILD/'concurrent.cpp'
            source.write_text(code)
        binary = BUILD/name
        args = ['g++','-std=c++17','-O3','-DNDEBUG','-fno-builtin-malloc','-fno-builtin-free',
                str(source),'-pthread','-ldl','-o',str(binary)]
        subprocess.run(args, check=True)
        con.save(module.EXP/'artifacts.json', dict(environment=environment, libraries=libraries,
                 binary=dict(path=str(binary), sha256=con.sha(binary), command=args), source_sha256=con.sha(source)))
    return list(libraries)


def execute(stage, entries, totals):
    rates = {size: [] for size in SIZES}
    for i, (rep, profile, case) in enumerate(entries):
        if case in SIZES:
            cfg = dict(version=profile, size=case, pairs=2, retained=False, rep=rep,
                       cap=128*2**20, objects=totals[case]//case)
            row = con.run(cfg, 1 if stage=='measured' else .01, stage=='smoke')
        else:
            row = life.run_one(profile, case, 64 if stage=='smoke' else 32768, 1)
        row['entry'] = [rep, profile, case]
        path = OUT/stage/('{:03d}.json'.format(i))
        con.save(path, row)
        assert row['valid'], (path, row.get('error'), row.get('stderr'))
        if case in SIZES:
            rates[case].append(totals[case]*1e9/row['final']['elapsed_ns'])
    return rates


def main():
    assert sorted(os.sched_getaffinity(0)) == [0,2,4,6,8,10]
    assert not (EXP/'plan.json').exists()
    BUILD.mkdir(parents=True, exist_ok=True)
    profiles = prepare()
    os.sched_setaffinity(0, {10})
    cells = list(itertools.product(profiles, SIZES+['same','remote']))
    execute('smoke', [(0,p,c) for p,c in cells], dict.fromkeys(SIZES,GIB//4))
    rates = execute('pilot', [(0,p,c) for p,c in cells if c in SIZES], dict.fromkeys(SIZES,GIB))
    totals = {s: math.ceil(2*max(rates[s])/GIB)*GIB for s in SIZES}
    order = []
    rng = random.Random(20261122)
    for rep in range(3):
        block = cells[:]
        rng.shuffle(block)
        order.extend((rep,p,c) for p,c in block)
    inputs = [Path(__file__), Path(con.__file__), Path(life.__file__), ROOT/'docs/dev3-20261122-plan.md',
              ROOT/'observation/concurrent.cpp', ROOT/'observation/lifecycle.cpp']
    inputs += list(EXP.glob('*/artifacts.json')) + list(OUT.glob('pilot/*.json'))
    con.save(EXP/'plan.json', dict(status='Frozen', frozen_at=con.stamp(), seed=20261122, bytes_by_size=totals,
             order=order, hashes={str(p.relative_to(ROOT)): con.sha(p) for p in inputs}))
    execute('measured', order, totals)


if __name__ == '__main__':
    main()
