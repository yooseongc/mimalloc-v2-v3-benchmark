// Batch handoff lifecycle: one producer and one consumer per independent ring.
#include <atomic>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <dlfcn.h>
#include <new>
#include <sched.h>
#include <sys/mman.h>
#include <thread>
#include <time.h>
#include <unistd.h>

constexpr size_t batch=256;
struct alignas(64) Slot { std::atomic<unsigned> full{0}; };
struct alignas(64) Counter {
  std::atomic<uint64_t> published{0};
  uint64_t count=0, waits=0, checksum=0, cpu=0, ended=0;
  int cpu_start=-1, cpu_end=-1;
};
struct Pair { Slot* slots; unsigned char** ptrs; size_t capacity, batches; Counter producer, consumer; };
static Pair rings[2];
static std::atomic<unsigned> ready{0}, done{0}, phase{0};
static size_t object_bytes,pair_count;
static bool retained,verify_full;
static uint64_t began;
static uint64_t now(clockid_t id=CLOCK_MONOTONIC) {
  timespec t{};if(clock_gettime(id,&t))std::abort();
  return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;
}
static void pin(int cpu) {
  cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
  if(sched_setaffinity(0,sizeof(set),&set)||sched_getcpu()!=cpu)std::abort();
}
static void pause_cpu(uint64_t n) {
  __asm__ __volatile__("pause");
  if((n&4095)==0)sched_yield();
}
static void wait_phase(unsigned want) {
  while(phase.load(std::memory_order_acquire)<want) {
    timespec t{0,100000}; nanosleep(&t,nullptr);
  }
}
static uint64_t identity(size_t id,size_t b,size_t j) {return (uint64_t(b)*batch+j)*2+id+1;}
static void fill(Pair& r,size_t id,size_t b,bool allocate) {
  auto ptrs=r.ptrs+(b%r.capacity)*batch;
  for(size_t j=0;j<batch;++j) {
    if(allocate) {ptrs[j]=static_cast<unsigned char*>(std::malloc(object_bytes));if(!ptrs[j])std::abort();}
    auto p=ptrs[j];uint64_t seq=identity(id,b,j),tail=~seq;
    std::memset(p,static_cast<int>(seq%251),object_bytes);
    std::memcpy(p,&seq,8);std::memcpy(p+object_bytes-8,&tail,8);
  }
}
static void producer(size_t id) {
  auto& r=rings[id];auto& c=r.producer;pin(int(id*4));
  for(size_t b=0;b<r.capacity;++b) {fill(r,id,b,true);r.slots[b].full.store(1,std::memory_order_release);}
  ready.fetch_add(1,std::memory_order_release);wait_phase(1);
  c.cpu_start=sched_getcpu();const uint64_t cpu=now(CLOCK_THREAD_CPUTIME_ID);
  for(size_t b=r.capacity;b<r.batches;++b) {
    auto& s=r.slots[b%r.capacity];
    while(s.full.load(std::memory_order_acquire)!=0)pause_cpu(++c.waits);
    fill(r,id,b,!retained);c.count+=batch;
    c.published.store(c.count,std::memory_order_release);
    s.full.store(1,std::memory_order_release);
  }
  c.ended=now();c.cpu=now(CLOCK_THREAD_CPUTIME_ID)-cpu;c.cpu_end=sched_getcpu();
  done.fetch_add(1,std::memory_order_release);wait_phase(2);
}
static void consumer(size_t id) {
  auto& r=rings[id];auto& c=r.consumer;pin(int(id*4+2));
  ready.fetch_add(1,std::memory_order_release);wait_phase(1);
  c.cpu_start=sched_getcpu();const uint64_t cpu=now(CLOCK_THREAD_CPUTIME_ID);
  for(size_t b=0;b<r.batches;++b) {
    auto& s=r.slots[b%r.capacity];
    while(s.full.load(std::memory_order_acquire)!=1)pause_cpu(++c.waits);
    auto ptrs=r.ptrs+(b%r.capacity)*batch;
    for(size_t j=0;j<batch;++j) {
      auto p=ptrs[j];uint64_t head,tail,expected=identity(id,b,j);
      std::memcpy(&head,p,8);std::memcpy(&tail,p+object_bytes-8,8);
      if(head!=expected||tail!=~expected)std::abort();
      if(verify_full)for(size_t k=8;k<object_bytes-8;++k)if(p[k]!=expected%251)std::abort();
      c.checksum+=head;
      if(!retained){std::free(p);ptrs[j]=nullptr;}
    }
    c.count+=batch;c.published.store(c.count,std::memory_order_release);
    s.full.store(0,std::memory_order_release);
  }
  c.ended=now();c.cpu=now(CLOCK_THREAD_CPUTIME_ID)-cpu;c.cpu_end=sched_getcpu();
  done.fetch_add(1,std::memory_order_release);wait_phase(2);
  if(retained)for(size_t j=0;j<r.capacity*batch;++j)std::free(r.ptrs[j]);
}
static void emit(bool finished) {
  uint64_t produced=0,consumed=0,end=began,sum=0,cpu=0;
  for(size_t i=0;i<pair_count;++i) {
    // Read consumed before produced: monotonic publication avoids a negative live estimate.
    consumed+=rings[i].consumer.published.load(std::memory_order_acquire);
    produced+=rings[i].producer.published.load(std::memory_order_acquire);
    if(finished){end=std::max(end,std::max(rings[i].producer.ended,rings[i].consumer.ended));
      sum+=rings[i].consumer.checksum;cpu+=rings[i].consumer.cpu+rings[i].producer.cpu;}
  }
  const uint64_t initial=rings[0].capacity*pair_count*batch;
  const uint64_t live=retained?initial:(initial+produced-consumed);
  std::printf("{\"done\":%s,\"produced\":%llu,\"consumed\":%llu,\"live_estimate_bytes\":%llu,\"elapsed_ns\":%llu,\"cpu_ns\":%llu,\"checksum\":%llu,\"workers\":[",
    finished?"true":"false",(unsigned long long)produced,(unsigned long long)consumed,
    (unsigned long long)(live*object_bytes),(unsigned long long)(finished?end-began:now()-began),
    (unsigned long long)cpu,(unsigned long long)sum);
  if(finished)for(size_t i=0;i<pair_count;++i)for(size_t role=0;role<2;++role) {
    auto& c=role?rings[i].consumer:rings[i].producer;
    std::printf("%s{\"pair\":%zu,\"role\":\"%s\",\"count\":%llu,\"wait_polls\":%llu,\"cpu_ns\":%llu,\"cpu_start\":%d,\"cpu_end\":%d}",
      i||role?",":"",i,role?"consumer":"producer",(unsigned long long)c.count,
      (unsigned long long)c.waits,(unsigned long long)c.cpu,c.cpu_start,c.cpu_end);
  }
  std::printf("]}\n");
}
int main(int argc,char** argv) {
  if(argc!=7)return 2;
  pair_count=std::strtoull(argv[1],nullptr,10);object_bytes=std::strtoull(argv[2],nullptr,10);
  size_t cap=std::strtoull(argv[3],nullptr,10),total=std::strtoull(argv[4],nullptr,10);
  retained=std::atoi(argv[5])!=0;verify_full=std::atoi(argv[6])!=0;
  if((pair_count!=1&&pair_count!=2)||object_bytes<64||object_bytes>4096||cap==0||cap>512ULL*1024*1024||
    cap%(pair_count*batch*object_bytes)||total%(pair_count*batch)||total<cap/object_bytes*2)return 2;
  pin(8);setvbuf(stdout,nullptr,_IONBF,0);
  auto ver=reinterpret_cast<int(*)()>(dlsym(RTLD_DEFAULT,"mi_version"));
  Dl_info a{},f{};
  if(!ver||!dladdr(dlsym(RTLD_DEFAULT,"malloc"),&a)||!dladdr(dlsym(RTLD_DEFAULT,"free"),&f)||std::strcmp(a.dli_fname,f.dli_fname))return 3;
  std::thread threads[4];
  for(size_t i=0;i<pair_count;++i) {
    auto& r=rings[i];r.capacity=cap/(pair_count*batch*object_bytes);r.batches=total/(pair_count*batch);
    r.slots=static_cast<Slot*>(mmap(nullptr,r.capacity*sizeof(Slot),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    r.ptrs=static_cast<unsigned char**>(mmap(nullptr,r.capacity*batch*sizeof(void*),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0));
    if(r.slots==MAP_FAILED||r.ptrs==MAP_FAILED)return 4;
    for(size_t k=0;k<r.capacity;++k)new(r.slots+k)Slot;
    threads[i*2]=std::thread(producer,i);threads[i*2+1]=std::thread(consumer,i);
  }
  while(ready.load(std::memory_order_acquire)!=pair_count*2)std::this_thread::yield();
  std::printf("{\"ready\":true,\"pid\":%d,\"version\":%d,\"library\":\"%s\",\"live_bytes\":%zu}\n",getpid(),ver(),a.dli_fname,cap);
  char line[32];
  while(true) {
    size_t n=0;char ch;
    while(n+1<sizeof(line)) {if(read(0,&ch,1)!=1)std::abort();if(ch=='\n')break;line[n++]=ch;}line[n]=0;
    if(std::strcmp(line,"go")==0) {if(phase.load()!=0)std::abort();began=now();phase.store(1,std::memory_order_release);std::printf("{\"started\":true}\n");}
    else if(std::strcmp(line,"sample")==0)emit(done.load(std::memory_order_acquire)==pair_count*2);
    else if(std::strcmp(line,"quit")==0) {if(done.load(std::memory_order_acquire)!=pair_count*2)std::abort();phase.store(2,std::memory_order_release);break;}
    else std::abort();
  }
  for(size_t i=0;i<pair_count*2;++i)threads[i].join();
  return 0;
}
