#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <dlfcn.h>
#include <sched.h>
#include <time.h>
#include <sys/resource.h>

static void require(bool b) { if (!b) { std::fputs("validation failed\n",stderr); std::exit(2); } }
static uint64_t ns(clockid_t c) { timespec t; require(clock_gettime(c,&t)==0); return uint64_t(t.tv_sec)*1000000000+t.tv_nsec; }
static void waitgo() { require(std::getchar()=='g'); }
template<class T> T sym(const char* s) { auto p=dlsym(RTLD_DEFAULT,s); require(p!=nullptr); return reinterpret_cast<T>(p); }
int main(int argc,char** argv) {
  require(argc==8);
  const bool aligned=std::atoi(argv[1])!=0, full=std::atoi(argv[7])!=0;
  const size_t size=std::strtoull(argv[2],nullptr,10), num=std::strtoull(argv[3],nullptr,10);
  const size_t fraction=std::strtoull(argv[4],nullptr,10), cycles=std::strtoull(argv[5],nullptr,10);
  const bool life=std::atoi(argv[6])!=0;
  cpu_set_t cpus; CPU_ZERO(&cpus); CPU_SET(0,&cpus); require(sched_setaffinity(0,sizeof(cpus),&cpus)==0);
  auto usable=sym<size_t(*)(const void*)>("mi_usable_size");
  auto amalloc=sym<void*(*)(size_t,size_t)>("mi_malloc_aligned");
  auto arealloc=sym<void*(*)(void*,size_t,size_t)>("mi_realloc_aligned");
  auto collect=sym<void(*)(bool)>("mi_collect");
  auto version=sym<int(*)()>("mi_version");
  Dl_info info{}; require(dladdr(reinterpret_cast<void*>(version),&info)!=0);
  std::vector<void*> ptr(num); std::vector<size_t> target(num); std::vector<uintptr_t> old(num);
  std::printf("{\"phase\":\"ready\",\"version\":%d,\"library\":\"%s\"}\n",version(),info.dli_fname); std::fflush(stdout); waitgo();
  uint64_t totalwall=0,totalcpu=0,checksum=0,totalmoved=0,totalusable=0,requested=0,initial=0;
  long minflt=0,majflt=0; const uint64_t start=ns(CLOCK_MONOTONIC);
  for(size_t c=0;c<cycles+(life?0:1);++c) {
    initial=0; requested=0; totalusable=0; uint64_t moved=0;
    for(size_t i=0;i<num;++i) {
      ptr[i]=aligned?amalloc(size,64):std::malloc(size); require(ptr[i]!=nullptr);
      std::memset(ptr[i],int(i%251+1),size); old[i]=reinterpret_cast<uintptr_t>(ptr[i]);
      const size_t u=usable(ptr[i]); initial+=u; target[i]=u*fraction/16; requested+=target[i];
      require(target[i]>0 && target[i]<=size); // all retained bytes initialized
    }
    if(life) { std::printf("{\"phase\":\"allocated\",\"usable\":%llu,\"requested_after\":%llu}\n",(unsigned long long)initial,(unsigned long long)requested); std::fflush(stdout); waitgo(); }
    rusage a{},b{}; getrusage(RUSAGE_SELF,&a);
    const uint64_t cpu=ns(CLOCK_PROCESS_CPUTIME_ID),wall=ns(CLOCK_MONOTONIC);
    for(size_t i=0;i<num;++i) ptr[i]=aligned?arealloc(ptr[i],target[i],64):std::realloc(ptr[i],target[i]);
    const uint64_t dw=ns(CLOCK_MONOTONIC)-wall,dc=ns(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    getrusage(RUSAGE_SELF,&b);
    if(life || c>0) { totalwall+=dw; totalcpu+=dc; minflt+=b.ru_minflt-a.ru_minflt; majflt+=b.ru_majflt-a.ru_majflt; }
    for(size_t i=0;i<num;++i) {
      require(ptr[i]!=nullptr); const auto q=static_cast<unsigned char*>(ptr[i]);
      if(aligned) require(reinterpret_cast<uintptr_t>(q)%64==0);
      moved+=(reinterpret_cast<uintptr_t>(q)!=old[i]); totalusable+=usable(q);
      require(usable(q)>=target[i]);
      for(size_t j=0;j<target[i];j+=(full?1:4096)) require(q[j]==i%251+1);
      require(q[target[i]-1]==i%251+1); if(life || c>0) checksum+=q[0]+q[target[i]-1];
    }
    if(life || c>0) totalmoved+=moved;
    if(life) {
      std::printf("{\"phase\":\"shrunk\",\"wall_ns\":%llu,\"cpu_ns\":%llu,\"moved\":%llu,\"usable\":%llu}\n",(unsigned long long)dw,(unsigned long long)dc,(unsigned long long)moved,(unsigned long long)totalusable); std::fflush(stdout); waitgo();
      collect(true); std::puts("{\"phase\":\"collected\"}"); std::fflush(stdout); waitgo();
    }
    for(void* p:ptr) std::free(p);
  }
  const uint64_t loop=ns(CLOCK_MONOTONIC)-start;
  if(life) collect(true);
  std::printf("{\"phase\":\"done\",\"wall_ns\":%llu,\"cpu_ns\":%llu,\"loop_ns\":%llu,\"calls\":%llu,\"moved\":%llu,\"checksum\":%llu,\"minor_faults\":%ld,\"major_faults\":%ld,\"live\":0}\n",(unsigned long long)totalwall,(unsigned long long)totalcpu,(unsigned long long)loop,(unsigned long long)(cycles*num),(unsigned long long)totalmoved,(unsigned long long)checksum,minflt,majflt); std::fflush(stdout); waitgo();
}
