import pathlib,subprocess,shlex,json,hashlib
R=pathlib.Path('/work');O=R/'experiments/v370-code-analysis-v1';O.mkdir(exist_ok=True)
source='''#include <stddef.h>
#include <stdio.h>
#include "mimalloc/types.h"
int main(void) {
 printf("{\\"large_pages\\":%d,\\"small_max\\":%zu,\\"medium_max\\":%zu,\\"large_max\\":%zu,\\"page_sizeof\\":%zu,\\"xthread_free_offset\\":%zu,\\"free_offset\\":%zu,\\"local_free_offset\\":%zu,\\"page_start_offset\\":%zu,\\"secure\\":%d,\\"stats\\":%d,\\"profile\\":%d}\\n", MI_ENABLE_LARGE_PAGES,(size_t)MI_SMALL_MAX_OBJ_SIZE,(size_t)MI_MEDIUM_MAX_OBJ_SIZE,(size_t)MI_LARGE_MAX_OBJ_SIZE,sizeof(mi_page_t),offsetof(mi_page_t,xthread_free),offsetof(mi_page_t,free),offsetof(mi_page_t,local_free),offsetof(mi_page_t,page_start),MI_SECURE,MI_STATS,MI_PROFILE);
 return 0;
}'''
(O/'layout.c').write_text(source)
results={}
for v in ('v3.6.1','v3.7.0'):
 flags=R/'build/release-v370-v1/lifecycle'/v/'CMakeFiles/mimalloc.dir/flags.make'
 kv=dict(l.split(' = ',1) for l in flags.read_text().splitlines() if ' = ' in l)
 base=['cc']+shlex.split(kv['C_DEFINES'])+shlex.split(kv['C_INCLUDES'])+shlex.split(kv['C_FLAGS'])
 cmd=base+[str(O/'layout.c'),'-o',str(O/(v+'-layout'))]
 subprocess.run(cmd,check=True)
 out=subprocess.check_output([str(O/(v+'-layout'))],universal_newlines=True)
 macros=subprocess.check_output(base+['-dM','-E',str(O/'layout.c')],universal_newlines=True)
 (O/(v+'-macros.txt')).write_text(macros)
 lib=R/'build/release-v370-v1/lifecycle'/v/'libmimalloc.so'
 asm=subprocess.check_output(['objdump','-d','-C',str(lib)],universal_newlines=True)
 (O/(v+'-assembly.txt')).write_text(asm)
 results[v]={'layout':json.loads(out),'command':cmd,'library_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),'flags_sha256':hashlib.sha256(flags.read_bytes()).hexdigest()}
 print(v,out.strip())
(O/'evidence.json').write_text(json.dumps(results,indent=2)+'\n')
