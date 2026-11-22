import pathlib,subprocess,json,shlex,hashlib
R=pathlib.Path('/work');O=R/'experiments/v370-code-analysis-v1'
s='''#include <stdio.h>
#include "mimalloc.h"
#include "mimalloc/heap/page-map.h"
#include "mimalloc/alloc/page.h"
int main(void) {
 size_t sizes[]={4096,16384,65536,262144};
 for(int i=0;i<4;i++) {
  void* p=mi_malloc(sizes[i]); if(!p)return 2;
  mi_page_t* page=mi_ptr_page(p);
  printf("{\\"request\\":%zu,\\"usable\\":%zu,\\"block_size\\":%zu,\\"reserved\\":%u,\\"capacity\\":%u,\\"slice_count\\":%u,\\"block_offset\\":%zu}\\n",sizes[i],mi_usable_size(p),mi_page_block_size(page),page->reserved,page->capacity,page->memid.mem.arena.slice_count,(size_t)((char*)p-(char*)mi_page_slice_start(page)));
  mi_free(p);
 }
 return 0;
}'''
(O/'pages.c').write_text(s)
records={}
for v in ('v3.6.1','v3.7.0'):
 flags=R/'build/release-v370-v1/lifecycle'/v/'CMakeFiles/mimalloc.dir/flags.make'
 kv=dict(l.split(' = ',1) for l in flags.read_text().splitlines() if ' = ' in l)
 libdir=flags.parents[2]
 cmd=['cc']+shlex.split(kv['C_DEFINES'])+shlex.split(kv['C_INCLUDES'])+shlex.split(kv['C_FLAGS'])+[str(O/'pages.c'),'-L'+str(libdir),'-Wl,-rpath,'+str(libdir),'-lmimalloc','-o',str(O/(v+'-pages'))]
 subprocess.run(cmd,check=True)
 out=subprocess.check_output([str(O/(v+'-pages'))],universal_newlines=True)
 records[v]={'command':cmd,'observations':[json.loads(x) for x in out.splitlines()]}
 print(v,out)
(O/'pages.json').write_text(json.dumps(records,indent=2)+'\n')
