// Fresh diagnostic for thread initialization, teardown, and post-exit remote free.
#include <pthread.h>
#include <sched.h>
#include <sys/resource.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <time.h>
static void* objects[1024];
static size_t bytes;
static int mode;
static uint64_t checksum, allocations, frees, first_ns;
static uint64_t now() { timespec t{}; if(clock_gettime(CLOCK_MONOTONIC,&t)) std::abort(); return uint64_t(t.tv_sec)*1000000000+t.tv_nsec; }
static void pin(int n) { cpu_set_t c; CPU_ZERO(&c); CPU_SET(n,&c); if(sched_setaffinity(0,sizeof(c),&c)||sched_getcpu()!=n) std::abort(); }
static void release() {
  for(size_t i=0;i<1024;i++) {
    auto p=static_cast<unsigned char*>(objects[i]);
    if(!p || p[0]!=static_cast<unsigned char>(i%251) || p[bytes-1]!=static_cast<unsigned char>(i%251)) std::abort();
    checksum+=p[0]+p[bytes-1]; std::free(p); objects[i]=nullptr; ++frees;
  }
}
static void* worker(void*) {
  pin(0);
  if(mode) {
    for(size_t i=0;i<1024;i++) {
      uint64_t t=i==0?now():0;
      auto p=static_cast<unsigned char*>(std::malloc(bytes));
      if(i==0) first_ns+=now()-t;
      if(!p) std::abort();
      p[0]=p[bytes-1]=static_cast<unsigned char>(i%251); objects[i]=p; ++allocations;
    }
    if(mode==1) release();
  }
  if(sched_getcpu()!=0) std::abort();
  return nullptr;
}
static void cycle() { pthread_t t; if(pthread_create(&t,nullptr,worker,nullptr)||pthread_join(t,nullptr)) std::abort(); if(mode==2) release(); }
static uint64_t cpu(const rusage& r) { return uint64_t(r.ru_utime.tv_sec+r.ru_stime.tv_sec)*1000000000+uint64_t(r.ru_utime.tv_usec+r.ru_stime.tv_usec)*1000; }
int main(int argc,char** argv) {
  if(argc!=4) return 2;
  mode=std::atoi(argv[1]); bytes=std::strtoull(argv[2],nullptr,10); size_t cycles=std::strtoull(argv[3],nullptr,10);
  if(mode<0||mode>2||bytes<2||!cycles) return 2;
  pin(2);
  auto version=reinterpret_cast<int(*)()>(dlsym(RTLD_DEFAULT,"mi_version"));
  Dl_info info{}; if(!version||!dladdr(reinterpret_cast<void*>(version),&info)) return 3;
  for(int i=0;i<20;i++) cycle();
  checksum=allocations=frees=first_ns=0;
  std::printf("{\"version\":%d,\"library\":\"%s\"}\n",version(),info.dli_fname); std::fflush(stdout);
  if(std::getchar()!='g') return 4;
  rusage before{},after{}; if(getrusage(RUSAGE_SELF,&before)) return 5;
  uint64_t t=now(); for(size_t i=0;i<cycles;i++) cycle(); uint64_t elapsed=now()-t;
  if(getrusage(RUSAGE_SELF,&after)||sched_getcpu()!=2) return 5;
  for(auto p:objects) if(p) return 6;
  std::printf("{\"cycles\":%zu,\"allocations\":%llu,\"frees\":%llu,\"checksum\":%llu,\"elapsed_ns\":%llu,\"cpu_ns\":%llu,\"first_malloc_ns_sum\":%llu,\"minor_faults\":%ld,\"major_faults\":%ld,\"peak_rss_bytes\":%ld,\"live_objects\":0}\n",cycles,(unsigned long long)allocations,(unsigned long long)frees,(unsigned long long)checksum,(unsigned long long)elapsed,(unsigned long long)(cpu(after)-cpu(before)),(unsigned long long)first_ns,after.ru_minflt-before.ru_minflt,after.ru_majflt-before.ru_majflt,after.ru_maxrss*1024);
  std::fflush(stdout); if(std::getchar()!='q') return 4;
}
