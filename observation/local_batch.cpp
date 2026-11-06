// Same-thread batch allocation/free; fixed work, no thread creation in timing.
#include <sched.h>
#include <sys/resource.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <time.h>
static void* objects[1024];
static size_t bytes;
static uint64_t checksum=0;
static uint64_t now(){timespec t{};if(clock_gettime(CLOCK_MONOTONIC,&t))std::abort();return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;}
static void batch(){
  for(size_t i=0;i<1024;i++){
    auto p=static_cast<unsigned char*>(std::malloc(bytes));if(!p)std::abort();
    p[0]=p[bytes-1]=static_cast<unsigned char>(i%251);objects[i]=p;
  }
  for(size_t i=0;i<1024;i++){
    auto p=static_cast<unsigned char*>(objects[i]);
    if(p[0]!=i%251||p[bytes-1]!=i%251)std::abort();
    checksum+=p[0]+p[bytes-1];std::free(p);objects[i]=nullptr;
  }
}
static uint64_t cpu(const rusage& r){return uint64_t(r.ru_utime.tv_sec+r.ru_stime.tv_sec)*1000000000+uint64_t(r.ru_utime.tv_usec+r.ru_stime.tv_usec)*1000;}
int main(int argc,char** argv){
  if(argc!=4||std::atoi(argv[1])!=1)return 2;
  bytes=std::strtoull(argv[2],nullptr,10);size_t cycles=std::strtoull(argv[3],nullptr,10);
  if((bytes!=64&&bytes!=4096)||!cycles)return 2;
  cpu_set_t c;CPU_ZERO(&c);CPU_SET(2,&c);if(sched_setaffinity(0,sizeof(c),&c)||sched_getcpu()!=2)return 3;
  auto version=reinterpret_cast<int(*)()>(dlsym(RTLD_DEFAULT,"mi_version"));Dl_info info{};
  if(!version||!dladdr(reinterpret_cast<void*>(version),&info))return 4;
  for(int i=0;i<100;i++){batch();}
  checksum=0;
  std::printf("{\"version\":%d,\"library\":\"%s\"}\n",version(),info.dli_fname);std::fflush(stdout);
  if(std::getchar()!='g')return 5;
  rusage before{},after{};if(getrusage(RUSAGE_SELF,&before))return 6;
  uint64_t t=now();for(size_t i=0;i<cycles;i++)batch();uint64_t elapsed=now()-t;
  if(getrusage(RUSAGE_SELF,&after)||sched_getcpu()!=2)return 6;
  std::printf("{\"cycles\":%zu,\"allocations\":%llu,\"frees\":%llu,\"checksum\":%llu,\"elapsed_ns\":%llu,\"cpu_ns\":%llu,\"minor_faults\":%ld,\"major_faults\":%ld,\"peak_rss_bytes\":%ld,\"live_objects\":0}\n",cycles,(unsigned long long)(cycles*1024),(unsigned long long)(cycles*1024),(unsigned long long)checksum,(unsigned long long)elapsed,(unsigned long long)(cpu(after)-cpu(before)),after.ru_minflt-before.ru_minflt,after.ru_majflt-before.ru_majflt,after.ru_maxrss*1024);
  std::fflush(stdout);return std::getchar()=='q'?0:7;
}
