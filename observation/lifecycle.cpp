// A deliberately sequential memory lifecycle; no per-object queue or clock.
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <mutex>
#include <sched.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <thread>
#include <unistd.h>

static unsigned char** objects;
static size_t count, bytes;
static std::mutex mutex;
static std::condition_variable command_ready, completed;
static int command = 0, target = 0;
static bool pending = false, finished = false, stopping = false;
static unsigned ready = 0;
static void (*collect_fn)(bool);
static unsigned long long checksum = 0;

static long long ns() {
  timespec t{};
  if (clock_gettime(CLOCK_MONOTONIC, &t)) std::abort();
  return t.tv_sec * 1000000000LL + t.tv_nsec;
}
static long long cpu_ns(const rusage& u) {
  return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000000000LL +
         (u.ru_utime.tv_usec + u.ru_stime.tv_usec) * 1000LL;
}
static void pin(int cpu) {
  cpu_set_t mask; CPU_ZERO(&mask); CPU_SET(cpu, &mask);
  if (sched_setaffinity(0, sizeof(mask), &mask) || sched_getcpu() != cpu) std::abort();
}
static unsigned char pattern(size_t i) { return static_cast<unsigned char>((i * 37 + 11) % 251); }

// Observable returned checksum and explicit mismatch checks keep payload reads.
__attribute__((noinline)) static unsigned long long verify_payload() {
  unsigned long long sum = 0;
  for (size_t i = 0; i < count; ++i) if (objects[i]) {
    const unsigned char expected = pattern(i);
    for (size_t j = 0; j < bytes; ++j) {
      const auto value = objects[i][j];
      if (value != expected) std::abort();
      sum += value;
    }
  }
  return sum;
}
struct Result {
  long long begin = 0, end = 0, cpu = 0, minor = 0, major = 0;
  size_t affected = 0;
  int worker = -1, cpu_start = -1, cpu_end = -1;
} result;

static void worker(int id) {
  pin(id == 0 ? 0 : 2);
  std::unique_lock<std::mutex> lock(mutex);
  ++ready; completed.notify_one();
  while (true) {
    command_ready.wait(lock, [id] { return stopping || (pending && target == id); });
    if (stopping) return;
    int action = command;
    lock.unlock();
    Result r;
    r.worker = id; r.cpu_start = sched_getcpu();
    rusage before{}, after{};
    if (getrusage(RUSAGE_THREAD, &before)) std::abort();
    r.begin = ns();
    if (action == 1) { // allocate only
      for (size_t i = 0; i < count; ++i) {
        if (objects[i]) std::abort();
        objects[i] = static_cast<unsigned char*>(std::malloc(bytes));
        if (!objects[i]) std::abort();
        ++r.affected;
      }
    } else if (action == 2) { // first-touch/full write, separate from allocation
      for (size_t i = 0; i < count; ++i) {
        if (!objects[i]) std::abort();
        std::memset(objects[i], pattern(i), bytes);
        ++r.affected;
      }
    } else if (action == 3 || action == 4 || action == 5) {
      const size_t first = action == 4 ? 1 : 0;
      const size_t stride = action == 5 ? 1 : 2;
      for (size_t i = first; i < count; i += stride) {
        if (!objects[i]) std::abort();
        std::free(objects[i]); objects[i] = nullptr; ++r.affected;
      }
    } else if (action == 6) {
      checksum += verify_payload();
    } else if (action == 7) {
      // Equal small same-thread warm-up for BOTH workers.
      for (size_t i = 0; i < 32; ++i) {
        auto p = static_cast<unsigned char*>(std::malloc(bytes));
        if (!p) std::abort();
        std::memset(p, 19, bytes);
        checksum += p[bytes - 1];
        std::free(p);
      }
    } else if (action == 8 || action == 9) {
      collect_fn(action == 9);
    } else if (action != 0) std::abort(); // empty phase is a timing control
    r.end = ns();
    if (getrusage(RUSAGE_THREAD, &after)) std::abort();
    r.cpu = cpu_ns(after) - cpu_ns(before);
    r.minor = after.ru_minflt - before.ru_minflt;
    r.major = after.ru_majflt - before.ru_majflt;
    r.cpu_end = sched_getcpu();
    lock.lock();
    result = r; pending = false; finished = true; completed.notify_one();
  }
}

int main(int argc, char** argv) {
  if (argc != 3) return 2;
  count = std::strtoull(argv[1], nullptr, 10);
  bytes = std::strtoull(argv[2], nullptr, 10);
  if (!count || count % 2 || !bytes || count > 1048576 || bytes > 1048576 ||
      count * bytes > 512ULL * 1024 * 1024) return 2;
  const auto process_start = ns();
  pin(4);
  auto version = reinterpret_cast<int (*)()>(dlsym(RTLD_DEFAULT, "mi_version"));
  collect_fn = reinterpret_cast<void (*)(bool)>(dlsym(RTLD_DEFAULT, "mi_collect"));
  Dl_info alloc_info{}, free_info{}, version_info{};
  if (!version || !collect_fn || !dladdr(dlsym(RTLD_DEFAULT, "malloc"), &alloc_info) ||
      !dladdr(dlsym(RTLD_DEFAULT, "free"), &free_info) ||
      !dladdr(reinterpret_cast<void*>(version), &version_info) ||
      std::strcmp(alloc_info.dli_fname, free_info.dli_fname) ||
      std::strcmp(alloc_info.dli_fname, version_info.dli_fname)) return 3;
  objects = static_cast<unsigned char**>(mmap(nullptr, count * sizeof(void*),
      PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
  if (objects == MAP_FAILED) return 4;
  std::memset(objects, 0, count * sizeof(void*));
  setvbuf(stdout, nullptr, _IONBF, 0);
  std::thread a(worker, 0), b(worker, 1);
  {
    std::unique_lock<std::mutex> lock(mutex);
    completed.wait(lock, [] { return ready == 2; });
  }
  std::printf("{\"event\":\"ready\",\"pid\":%d,\"version\":%d,\"library\":\"%s\",\"start_ns\":%lld}\n",
      getpid(), version(), alloc_info.dli_fname, process_start);
  char line[64];
  // Main blocks in read between commands; workers block on condition variables.
  while (true) {
    size_t used = 0;
    while (used + 1 < sizeof(line)) {
      char ch;
      if (read(STDIN_FILENO, &ch, 1) != 1) std::abort();
      if (ch == '\n') break;
      line[used++] = ch;
    }
    line[used] = 0;
    if (std::strcmp(line, "quit") == 0) break;
    int action, owner;
    if (std::sscanf(line, "%d %d", &action, &owner) != 2 || owner < 0 || owner > 1) std::abort();
    const auto dispatch = ns();
    {
      std::unique_lock<std::mutex> lock(mutex);
      command = action; target = owner; pending = true; finished = false;
      command_ready.notify_all();
      completed.wait(lock, [] { return finished; });
    }
    const auto joined = ns();
    size_t live = 0;
    for (size_t i = 0; i < count; ++i) live += objects[i] != nullptr;
    std::printf("{\"event\":\"phase\",\"action\":%d,\"worker\":%d,\"cpu_start\":%d,\"cpu_end\":%d,"
        "\"begin_ns\":%lld,\"end_ns\":%lld,\"wall_ns\":%lld,\"cpu_ns\":%lld,"
        "\"dispatch_join_ns\":%lld,\"minor_faults\":%lld,\"major_faults\":%lld,"
        "\"affected\":%zu,\"live_objects\":%zu,\"live_bytes\":%zu,\"checksum\":%llu}\n",
        action, result.worker, result.cpu_start, result.cpu_end,
        result.begin, result.end, result.end-result.begin, result.cpu,
        joined-dispatch, result.minor, result.major, result.affected, live, live*bytes, checksum);
  }
  for (size_t i = 0; i < count; ++i) if (objects[i]) std::abort();
  { std::lock_guard<std::mutex> lock(mutex); stopping = true; command_ready.notify_all(); }
  a.join(); b.join();
  if (munmap(objects, count * sizeof(void*))) return 5;
  return 0;
}
