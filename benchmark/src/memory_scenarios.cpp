#include "memory_scenarios.hpp"
#include "proc_metrics.hpp"
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <thread>
#include <vector>

namespace {
void touch(unsigned char* pointer, std::size_t size, const std::string& mode, std::uint64_t value, std::uint64_t& checksum) {
  if (mode == "none") return;
  pointer[0] = static_cast<unsigned char>(value);
  checksum += pointer[0];
  if (mode == "first-byte") return;
  pointer[size - 1] = static_cast<unsigned char>(value >> 8);
  checksum += pointer[size - 1];
  if (mode == "first-and-last") return;
  const std::size_t stride = mode == "per-cache-line" ? 64 : 4096;
  for (std::size_t offset = 0; offset < size; offset += stride) {
    pointer[offset] = static_cast<unsigned char>(value + offset);
    checksum += pointer[offset];
  }
  if (mode == "full-write") {
    std::memset(pointer, static_cast<int>(value), size);
    checksum += pointer[size / 2];
  }
}

void emit(const RunOptions& options, const AllocatorInfo& allocator, std::uint64_t count,
          std::uint64_t checksum, std::int64_t elapsed_ns, const ProcMetrics& before,
          const ProcMetrics& after, std::uint64_t rss_after_free, std::uint64_t rss_after_idle) {
  std::cout << "{\"valid\":true,\"scenario\":\"" << options.scenario
            << "\",\"allocator_version\":" << allocator.version
            << ",\"allocator_library_path\":\"" << allocator.library_path
            << "\",\"thread_count\":" << options.threads
            << ",\"operation_count\":" << count << ",\"elapsed_ns\":" << elapsed_ns
            << ",\"touch_mode\":\"" << options.touch_mode << "\""
            << ",\"peak_rss_bytes\":" << after.rss_bytes
            << ",\"user_cpu_ns\":" << (after.user_cpu_ns-before.user_cpu_ns)
            << ",\"system_cpu_ns\":" << (after.system_cpu_ns-before.system_cpu_ns)
            << ",\"rss_after_free_bytes\":" << rss_after_free
            << ",\"rss_after_idle_bytes\":" << rss_after_idle
            << ",\"page_faults\":{\"minor\":" << (after.minor_faults - before.minor_faults)
            << ",\"major\":" << (after.major_faults - before.major_faults)
            << "},\"checksum\":" << checksum << "}\n";
}
}

int run_memory_scenario(const RunOptions& options, const AllocatorInfo& allocator) {
  const auto allowed = current_affinity();
  if (allowed.empty()) { std::cerr << "no allowed CPU\n"; return 4; }
  std::string affinity_error;
  if (!pin_current_thread(allowed[0], affinity_error)) { std::cerr << affinity_error << "\n"; return 4; }
  const ProcMetrics before = read_proc_metrics();
  const auto began = std::chrono::steady_clock::now();
  std::uint64_t checksum = 0, count = 0;
  std::uint64_t rss_after_free = 0, rss_after_idle = 0;

  if (options.scenario == "lifetime_mix") {
    // Fixed 70/20/10 allocation mix.  Medium and long objects survive 16 and
    // 128 subsequent allocation slots respectively, making fragmentation and
    // delayed remote reclamation observable without unbounded retention.
    std::vector<unsigned char*> medium(16, nullptr), longer(128, nullptr);
    for (std::uint64_t i = 0; i < options.operations; ++i) {
      unsigned char* p = static_cast<unsigned char*>(std::malloc(options.size));
      if (!p) return 5;
      touch(p, options.size, options.touch_mode, i, checksum); ++count;
      const unsigned slot = static_cast<unsigned>(i % 10);
      if (slot < 7) std::free(p);
      else if (slot < 9) {
        const std::size_t index = (i / 10) % medium.size();
        if (medium[index]) std::free(medium[index]);
        medium[index] = p;
      } else {
        const std::size_t index = (i / 10) % longer.size();
        if (longer[index]) std::free(longer[index]);
        longer[index] = p;
      }
    }
    for (auto* p : medium) if (p) std::free(p);
    for (auto* p : longer) if (p) std::free(p);
  } else if (options.scenario == "burst_purge") {
    const std::size_t burst = options.batch_size;
    std::vector<unsigned char*> pointers; pointers.reserve(burst);
    for (std::uint64_t i = 0; i < options.operations; ++i) {
      pointers.clear();
      for (std::size_t n = 0; n < burst; ++n) {
        unsigned char* p = static_cast<unsigned char*>(std::malloc(options.size));
        if (!p) return 5;
        touch(p, options.size, options.touch_mode, i * burst + n, checksum);
        pointers.push_back(p); ++count;
      }
      for (auto* p : pointers) std::free(p);
      rss_after_free = read_proc_metrics().rss_bytes;
      std::this_thread::sleep_for(std::chrono::milliseconds(options.idle_ms));
      rss_after_idle = read_proc_metrics().rss_bytes;
    }
  } else if (options.scenario == "thread_churn") {
    for (std::uint64_t i = 0; i < options.operations; ++i) {
      unsigned char* retained = nullptr;
      std::thread worker([&] {
        retained = static_cast<unsigned char*>(std::malloc(options.size));
        if (!retained) std::terminate();
        touch(retained, options.size, options.touch_mode, i, checksum);
      });
      worker.join();
      // Deliberately free from the parent, after the allocating thread exits.
      std::free(retained); ++count;
    }
  } else { // large_alloc
    static const std::size_t sizes[] = {65536, 262144, 1048576, 2097152, 4194304, 16777216, 67108864};
    for (std::uint64_t i = 0; i < options.operations; ++i) {
      const std::size_t size = sizes[i % 7];
      unsigned char* p = static_cast<unsigned char*>(std::malloc(size));
      if (!p) return 5;
      touch(p, size, options.touch_mode, i, checksum);
      if (options.hold_ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(options.hold_ms));
      }
      std::free(p); ++count;
    }
  }

  if (!rss_after_free) rss_after_free = read_proc_metrics().rss_bytes;
  if (!rss_after_idle) rss_after_idle = rss_after_free;
  const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - began).count();
  const ProcMetrics after = read_proc_metrics();
  emit(options, allocator, count, checksum, elapsed, before, after, rss_after_free, rss_after_idle);
  return count == options.operations || options.scenario == "burst_purge" ? 0 : 6;
}
