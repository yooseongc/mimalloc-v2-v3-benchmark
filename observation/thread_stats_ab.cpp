// v3.5.3: A only allocates application objects; B only frees them.
#include "mimalloc-stats.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <thread>
#include <chrono>

static void* library;
template<class T> T symbol(const char* name) {
  auto p=reinterpret_cast<T>(dlsym(library,name));if(!p)std::abort();return p;
}
#define API(f) symbol<decltype(&f)>(#f)
struct Worker {
  std::atomic<int> command{0},done{0};
  mi_stats_t stats{};
  size_t alloc_calls=0,free_calls=0;
};
static Worker workers[2];
static mi_heap_t* heap;
static void* objects[1000];
static size_t bytes;
static void work(int id) {
  auto t=API(mi_heap_theap)(heap);auto old=API(mi_theap_set_default)(t);
  auto allocate=API(mi_malloc);auto release=API(mi_free);
  auto& w=workers[id];int previous=0;
  while(true) {
    int cmd=w.command.load(std::memory_order_acquire);
    if(cmd==previous) {std::this_thread::sleep_for(std::chrono::microseconds(100));continue;}
    int action=cmd%10;
    if(action==1) {
      if(id!=0)std::abort();
      for(size_t i=0;i<1000;++i) {
        objects[i]=allocate(bytes);if(!objects[i])std::abort();
        std::memset(objects[i],int(i%251),bytes);++w.alloc_calls;
      }
    }
    if(action==2) {
      if(id!=1)std::abort();
      for(size_t i=0;i<1000;++i) {
        auto p=static_cast<unsigned char*>(objects[i]);
        for(size_t j=0;j<bytes;++j)if(p[j]!=i%251)std::abort();
        release(p);objects[i]=nullptr;++w.free_calls;
      }
    }
    if(action==3)API(mi_collect)(true);
    if(action==4)API(mi_theap_stats_merge_to_heap)(t);
    if(action==9) {API(mi_theap_set_default)(old);w.done.store(cmd,std::memory_order_release);return;}
    mi_stats_init(&w.stats);
    if(!API(mi_theap_stats_get)(t,&w.stats))std::abort();
    previous=cmd;w.done.store(cmd,std::memory_order_release);
  }
}
static void act(int id,int action) {
  auto& w=workers[id];int cmd=(w.command.load()/10+1)*10+action;
  w.command.store(cmd,std::memory_order_release);
  while(w.done.load(std::memory_order_acquire)!=cmd)std::this_thread::sleep_for(std::chrono::microseconds(100));
}
static void print_stats(const char* name,const mi_stats_t& s) {
  auto n=s.malloc_normal;
  std::printf("\"%s\":{\"allocated_bytes\":%lld,\"current_bytes\":%lld,\"derived_freed_bytes\":%lld,\"allocated_count\":%lld}",
    name,(long long)n.total,(long long)n.current,(long long)(n.total-n.current),(long long)s.malloc_normal_count.total);
}
static void checkpoint(const char* name) {
  act(0,0);act(1,0); // getters execute on their own thread; both are then parked.
  mi_stats_t parent;mi_stats_init(&parent);
  // On this controller, heap_stats_get only merges its own empty theap.
  if(!API(mi_heap_stats_get)(heap,&parent))std::abort();
  std::printf("{\"stage\":\"%s\",\"A_alloc_calls\":%zu,\"A_free_calls\":%zu,\"B_alloc_calls\":%zu,\"B_free_calls\":%zu,",
    name,workers[0].alloc_calls,workers[0].free_calls,workers[1].alloc_calls,workers[1].free_calls);
  print_stats("A",workers[0].stats);std::putchar(',');print_stats("B",workers[1].stats);std::putchar(',');print_stats("parent",parent);
  const auto& a=workers[0].stats;const auto& b=workers[1].stats;
  auto total=a.malloc_normal.total+b.malloc_normal.total+parent.malloc_normal.total;
  auto current=a.malloc_normal.current+b.malloc_normal.current+parent.malloc_normal.current;
  auto count=a.malloc_normal_count.total+b.malloc_normal_count.total+parent.malloc_normal_count.total;
  std::printf(",\"sum\":{\"allocated_bytes\":%lld,\"current_bytes\":%lld,\"derived_freed_bytes\":%lld,\"allocated_count\":%lld}}\n",
    (long long)total,(long long)current,(long long)(total-current),(long long)count);
}
int main(int argc,char** argv) {
  if(argc!=3)return 2;
  bytes=std::strtoull(argv[2],nullptr,10);if(bytes!=64&&bytes!=4096)return 2;
  library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!library||API(mi_version)()!=30503)return 3;
  heap=API(mi_heap_new)();if(!heap)return 4;
  std::printf("{\"version\":30503,\"object_bytes\":%zu,\"objects\":1000,\"collect_merges_stats\":%ld,\"purge_delay\":%ld}\n",
    bytes,API(mi_option_get)(mi_option_collect_merges_stats),API(mi_option_get)(mi_option_purge_delay));
  std::thread a(work,0),b(work,1);
  checkpoint("baseline");
  act(0,1);checkpoint("A_allocated");
  act(0,3);checkpoint("A_collected_while_live");
  act(1,2);checkpoint("B_freed_all");
  act(1,3);checkpoint("B_collected");
  act(0,3);checkpoint("A_collected_after_free");
  act(0,3);act(1,3);checkpoint("both_collected_again");
  act(0,4);act(1,4);checkpoint("both_merged");
  if(workers[0].alloc_calls!=1000||workers[0].free_calls!=0||workers[1].alloc_calls!=0||workers[1].free_calls!=1000)std::abort();
  act(0,9);act(1,9);a.join();b.join();API(mi_heap_delete)(heap);
}
