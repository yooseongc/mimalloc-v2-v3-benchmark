#include <stdio.h>
#include "mimalloc.h"
#include "mimalloc/heap/page-map.h"
#include "mimalloc/alloc/page.h"
int main(void) {
 size_t sizes[]={4096,16384,65536,262144};
 for(int i=0;i<4;i++) {
  void* p=mi_malloc(sizes[i]); if(!p)return 2;
  mi_page_t* page=mi_ptr_page(p);
  printf("{\"request\":%zu,\"usable\":%zu,\"block_size\":%zu,\"reserved\":%u,\"capacity\":%u,\"slice_count\":%u,\"block_offset\":%zu}\n",sizes[i],mi_usable_size(p),mi_page_block_size(page),page->reserved,page->capacity,page->memid.mem.arena.slice_count,(size_t)((char*)p-(char*)mi_page_slice_start(page)));
  mi_free(p);
 }
 return 0;
}