// Small statistics correctness probe. Explicit API via dlopen isolates harness allocations.
#include "mimalloc.h"
#if MI_MALLOC_VERSION >= 30500
#include "mimalloc-stats.h"
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <thread>

static void* lib;
template<class T> T sym(const char* name) {
  auto p=reinterpret_cast<T>(dlsym(lib,name));if(!p)std::abort();return p;
}
#define API(name) sym<decltype(&name)>(#name)
static void* pointers[2000];
static size_t count,bytes;
static bool remote;
static void output(const char* s,void*) {std::fputs(s,stdout);}
#if MI_MALLOC_VERSION >= 30500
static void snapshot(const char* stage,mi_theap_t* t) {
  mi_stats_t s;mi_stats_init(&s);
  if(!API(mi_theap_stats_get)(t,&s))std::abort();
  std::printf("JSON {\"stage\":\"%s\",\"total\":%lld,\"current\":%lld,\"alloc_count\":%lld}\n",
    stage,(long long)s.malloc_normal.total,(long long)s.malloc_normal.current,(long long)s.malloc_normal_count.total);
}
#endif
static void worker() {
  auto heap=API(mi_heap_new)();if(!heap)std::abort();
#if MI_MALLOC_VERSION >= 30500
  auto t=API(mi_heap_theap)(heap);auto old=API(mi_theap_set_default)(t);
  snapshot("A_baseline",t);
#else
  auto old=API(mi_heap_set_default)(heap);
#endif
  for(size_t i=0;i<count;++i) {
    pointers[i]=API(mi_malloc)(bytes);if(!pointers[i])std::abort();
    std::memset(pointers[i],int(i%251),bytes);
  }
#if MI_MALLOC_VERSION >= 30500
  snapshot("A_allocated_raw",t);snapshot("A_allocated_repeat",t);
#endif
  std::puts("TEXT A_allocated_raw");API(mi_thread_stats_print_out)(output,nullptr);
  API(mi_collect)(true);
#if MI_MALLOC_VERSION >= 30500
  snapshot("A_allocated_collected",t);
#endif
  std::puts("TEXT A_allocated_collected");API(mi_thread_stats_print_out)(output,nullptr);
  auto release=[] {
    API(mi_thread_init)();
    for(size_t i=0;i<count;++i) {
      auto p=static_cast<unsigned char*>(pointers[i]);
      for(size_t j=0;j<bytes;++j)if(p[j]!=i%251)std::abort();
      API(mi_free)(p);
    }
#if MI_MALLOC_VERSION >= 30500
    if(remote) snapshot("B_after_remote_free",API(mi_theap_get_default)());
#endif
  };
  if(remote){std::thread b(release);b.join();}else release();
#if MI_MALLOC_VERSION >= 30500
  snapshot("A_freed_raw",t);
#endif
  API(mi_collect)(true);
#if MI_MALLOC_VERSION >= 30500
  snapshot("A_freed_collected",t);
  API(mi_collect)(true);snapshot("A_freed_collected_repeat",t);
  mi_stats_t s;mi_stats_init(&s);if(!API(mi_heap_stats_get)(heap,&s))std::abort();
  std::printf("JSON {\"stage\":\"heap_final\",\"total\":%lld,\"current\":%lld,\"alloc_count\":%lld}\n",
    (long long)s.malloc_normal.total,(long long)s.malloc_normal.current,(long long)s.malloc_normal_count.total);
  if(s.malloc_normal.total!=int64_t(count*bytes)||s.malloc_normal.current!=0||s.malloc_normal_count.total!=int64_t(count))std::exit(10);
  API(mi_theap_set_default)(old);
#else
  std::puts("TEXT A_freed_collected");API(mi_thread_stats_print_out)(output,nullptr);
  API(mi_heap_set_default)(old);
#endif
  API(mi_heap_delete)(heap);
}
int main(int argc,char** argv) {
  if(argc!=5)return 2;
  lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!lib)return 3;
  if(API(mi_version)()!=MI_MALLOC_VERSION)return 4;
  count=std::strtoull(argv[2],nullptr,10);bytes=std::strtoull(argv[3],nullptr,10);
  remote=std::atoi(argv[4])!=0;
  if(count==0||count>2000||bytes<16||bytes>4096)return 2;
  std::printf("CASE version=%d count=%zu bytes=%zu remote=%d\n",API(mi_version)(),count,bytes,remote);
  std::thread a(worker);a.join();std::puts("PASS payload and aggregate checks");
}
