#pragma once
#include <cstdint>
struct ProcMetrics {
  std::uint64_t rss_bytes{0};
  std::uint64_t minor_faults{0};
  std::uint64_t major_faults{0};
  std::uint64_t user_cpu_ns{0};
  std::uint64_t system_cpu_ns{0};
};
ProcMetrics read_proc_metrics();
