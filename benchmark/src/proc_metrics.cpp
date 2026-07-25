#include "proc_metrics.hpp"
#include <fstream>
#include <sys/resource.h>
#include <string>
#include <unistd.h>
namespace {
std::uint64_t timeval_ns(const timeval& value) {
  return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL +
         static_cast<std::uint64_t>(value.tv_usec) * 1000ULL;
}
}
ProcMetrics read_proc_metrics() {
  ProcMetrics m; std::ifstream status("/proc/self/status"); std::string key;
  while(status>>key) { if(key=="VmRSS:"){std::uint64_t k;status>>k;m.rss_bytes=k*1024;} else { std::string rest;std::getline(status,rest); } }
  struct rusage usage{};
  if (getrusage(RUSAGE_SELF, &usage) == 0) {
    m.minor_faults = static_cast<std::uint64_t>(usage.ru_minflt);
    m.major_faults = static_cast<std::uint64_t>(usage.ru_majflt);
    m.user_cpu_ns = timeval_ns(usage.ru_utime);
    m.system_cpu_ns = timeval_ns(usage.ru_stime);
  }
  return m;
}
