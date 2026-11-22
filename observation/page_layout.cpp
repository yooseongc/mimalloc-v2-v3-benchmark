// Structural probe, not a performance measurement; does not alter frozen runs.
#include "mimalloc.h"
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>

struct Areas { mi_heap_area_t items[64]; size_t count; };
static bool visit(const mi_heap_t*, const mi_heap_area_t* area, void* block, size_t, void* arg) {
  auto out=static_cast<Areas*>(arg);
  if (!block && area->block_size==4096) {
    if(out->count==64) std::abort();
    out->items[out->count++]=*area;
  }
  return true;
}
int main(int argc,char** argv) {
  if(argc!=2) return 2;
  void* lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
  if(!lib) return 3;
  auto heap_new=reinterpret_cast<decltype(&mi_heap_new)>(dlsym(lib,"mi_heap_new"));
  auto allocate=reinterpret_cast<decltype(&mi_heap_malloc)>(dlsym(lib,"mi_heap_malloc"));
  auto walk=reinterpret_cast<decltype(&mi_heap_visit_blocks)>(dlsym(lib,"mi_heap_visit_blocks"));
  auto destroy=reinterpret_cast<decltype(&mi_heap_destroy)>(dlsym(lib,"mi_heap_destroy"));
  auto version=reinterpret_cast<decltype(&mi_version)>(dlsym(lib,"mi_version"));
  if(!heap_new||!allocate||!walk||!destroy||!version) return 4;
  auto heap=heap_new();
  if(!heap) return 5;
  for(size_t i=0;i<256;++i) {
    auto p=static_cast<unsigned char*>(allocate(heap,4096));
    if(!p) return 6;
    p[0]=19;p[4095]=27;
  }
  Areas areas{};
  if(!walk(heap,false,visit,&areas)) return 7;
  std::printf("{\"version\":%d,\"requested_blocks\":256,\"areas\":[",version());
  size_t used=0;
  for(size_t i=0;i<areas.count;++i) {
    auto a=areas.items[i];used+=a.used;
    std::printf("%s{\"reserved\":%zu,\"committed\":%zu,\"used\":%zu,\"block_size\":%zu,\"start_offset_64k\":%zu}",
      i?",":"",a.reserved,a.committed,a.used,a.block_size,static_cast<size_t>(reinterpret_cast<uintptr_t>(a.blocks)%65536));
  }
  std::printf("],\"used_total\":%zu}\n",used);
  destroy(heap);
  return used==256?0:8;
}
