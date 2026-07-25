#include "benchmark.hpp"
#include <cerrno>
#include <sched.h>
#include <cstring>

bool pin_current_thread(int cpu, std::string& error) {
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(cpu, &set);
  if (sched_setaffinity(0, sizeof(set), &set) != 0) {
    error = std::strerror(errno);
    return false;
  }
  return true;
}

std::vector<int> current_affinity() {
  cpu_set_t set;
  CPU_ZERO(&set);
  std::vector<int> result;
  if (sched_getaffinity(0, sizeof(set), &set) != 0) return result;
  for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
    if (CPU_ISSET(cpu, &set)) result.push_back(cpu);
  }
  return result;
}
