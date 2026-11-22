#include "memory_scenarios.hpp"
#include "proc_metrics.hpp"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <iostream>
#include <thread>
#include <utility>
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

int run_memory_return(const RunOptions& options, const AllocatorInfo& allocator) {
  using MiCollect = void (*)(bool);
  MiCollect mi_collect = nullptr;
  if (options.memory_return_mode == "collect-normal" || options.memory_return_mode == "collect-force") {
    mi_collect = reinterpret_cast<MiCollect>(dlsym(RTLD_DEFAULT, "mi_collect"));
    if (mi_collect == nullptr) {
      std::cerr << "mi_collect was not resolved for collect mode\n";
      return 7;
    }
  }

  const ProcMetrics before = read_proc_metrics();
  const auto began = std::chrono::steady_clock::now();
  const std::size_t burst = options.batch_size;
  std::vector<unsigned char*> pointers;
  pointers.reserve(burst);
  std::uint64_t checksum = 0;

  const auto allocate_burst = [&](std::uint64_t phase) -> bool {
    pointers.clear();
    for (std::size_t n = 0; n < burst; ++n) {
      unsigned char* p = static_cast<unsigned char*>(std::malloc(options.size));
      if (p == nullptr) return false;
      touch(p, options.size, options.touch_mode, phase * burst + n, checksum);
      pointers.push_back(p);
    }
    return true;
  };
  const auto free_burst = [&]() {
    for (auto* p : pointers) std::free(p);
    pointers.clear();
  };

  const auto allocation_began = std::chrono::steady_clock::now();
  const ProcMetrics allocation_before = read_proc_metrics();
  if (!allocate_burst(0)) {
    free_burst();
    return 5;
  }
  const ProcMetrics allocation_after = read_proc_metrics();
  const std::uint64_t allocation_elapsed_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - allocation_began).count());
  const std::uint64_t working_set_rss = allocation_after.rss_bytes;

  const auto free_began = std::chrono::steady_clock::now();
  free_burst();
  const std::uint64_t free_elapsed_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - free_began).count());
  const ProcMetrics after_free = read_proc_metrics();

  std::uint64_t action_count = 0;
  std::uint64_t action_elapsed_ns = 0;
  const auto perform_action = [&]() -> bool {
    const auto action_began = std::chrono::steady_clock::now();
    if (options.memory_return_mode == "allocator-activity") {
      unsigned char* pulse = static_cast<unsigned char*>(std::malloc(64));
      if (pulse == nullptr) return false;
      pulse[0] = static_cast<unsigned char>(action_count);
      checksum += pulse[0];
      std::free(pulse);
    } else if (options.memory_return_mode == "collect-normal") {
      mi_collect(false);
    } else if (options.memory_return_mode == "collect-force") {
      mi_collect(true);
    }
    if (options.memory_return_mode != "passive") {
      ++action_count;
      action_elapsed_ns += static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(
              std::chrono::steady_clock::now() - action_began).count());
    }
    return true;
  };

  const auto observe_began = std::chrono::steady_clock::now();
  std::vector<std::pair<std::uint64_t, std::uint64_t>> observations;
  const std::uint64_t checkpoints[] = {0, 10, 100, 1000, 5000};
  if (options.memory_return_mode == "collect-force") {
    if (!perform_action()) return 5;
  } else if (options.memory_return_mode == "allocator-activity" ||
             options.memory_return_mode == "collect-normal") {
    if (!perform_action()) return 5;
  }
  observations.emplace_back(0, read_proc_metrics().rss_bytes);

  for (std::uint64_t offset = options.memory_action_interval_ms;
       offset <= options.idle_ms;
       offset += options.memory_action_interval_ms) {
    std::this_thread::sleep_until(observe_began + std::chrono::milliseconds(offset));
    if (options.memory_return_mode == "allocator-activity" ||
        options.memory_return_mode == "collect-normal") {
      if (!perform_action()) return 5;
    }
    for (const std::uint64_t checkpoint : checkpoints) {
      if (offset == checkpoint) observations.emplace_back(offset, read_proc_metrics().rss_bytes);
    }
  }
  if (observations.back().first != options.idle_ms) {
    std::this_thread::sleep_until(observe_began + std::chrono::milliseconds(options.idle_ms));
    observations.emplace_back(options.idle_ms, read_proc_metrics().rss_bytes);
  }
  const std::uint64_t observation_elapsed_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - observe_began).count());

  std::uint64_t reallocation_elapsed_ns = 0;
  std::uint64_t reallocation_free_elapsed_ns = 0;
  std::uint64_t reallocation_minor_faults = 0;
  std::uint64_t reallocation_major_faults = 0;
  std::uint64_t reallocation_working_set_rss = 0;
  std::uint64_t rss_after_reallocation_free = 0;
  if (options.reallocate_after_observe) {
    const ProcMetrics reallocation_before = read_proc_metrics();
    const auto reallocation_began = std::chrono::steady_clock::now();
    if (!allocate_burst(1)) {
      free_burst();
      return 5;
    }
    const ProcMetrics reallocation_after = read_proc_metrics();
    reallocation_elapsed_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - reallocation_began).count());
    reallocation_minor_faults = reallocation_after.minor_faults - reallocation_before.minor_faults;
    reallocation_major_faults = reallocation_after.major_faults - reallocation_before.major_faults;
    reallocation_working_set_rss = reallocation_after.rss_bytes;
    const auto reallocation_free_began = std::chrono::steady_clock::now();
    free_burst();
    reallocation_free_elapsed_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - reallocation_free_began).count());
    rss_after_reallocation_free = read_proc_metrics().rss_bytes;
  }

  const ProcMetrics after = read_proc_metrics();
  std::uint64_t maximum_observed_rss = std::max(working_set_rss, reallocation_working_set_rss);
  for (const auto& sample : observations) maximum_observed_rss = std::max(maximum_observed_rss, sample.second);
  const auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now() - began).count();
  std::cout << "{\"valid\":true,\"scenario\":\"memory_return\""
            << ",\"allocator_version\":" << allocator.version
            << ",\"allocator_library_path\":\"" << allocator.library_path << "\""
            << ",\"thread_count\":" << options.threads
            << ",\"operation_count\":" << burst
            << ",\"elapsed_ns\":" << elapsed_ns
            << ",\"touch_mode\":\"" << options.touch_mode << "\""
            << ",\"memory_return_mode\":\"" << options.memory_return_mode << "\""
            << ",\"memory_action_interval_ms\":" << options.memory_action_interval_ms
            << ",\"memory_action_count\":" << action_count
            << ",\"memory_action_elapsed_ns\":" << action_elapsed_ns
            << ",\"rss_before_burst_bytes\":" << before.rss_bytes
            << ",\"working_set_rss_bytes\":" << working_set_rss
            << ",\"rss_after_free_bytes\":" << after_free.rss_bytes
            << ",\"rss_after_idle_bytes\":" << observations.back().second
            << ",\"maximum_observed_rss_bytes\":" << maximum_observed_rss
            << ",\"allocation_elapsed_ns\":" << allocation_elapsed_ns
            << ",\"allocation_minor_faults\":" << (allocation_after.minor_faults - allocation_before.minor_faults)
            << ",\"allocation_major_faults\":" << (allocation_after.major_faults - allocation_before.major_faults)
            << ",\"free_elapsed_ns\":" << free_elapsed_ns
            << ",\"observation_elapsed_ns\":" << observation_elapsed_ns
            << ",\"rss_observations\":[";
  for (std::size_t i = 0; i < observations.size(); ++i) {
    std::cout << (i ? "," : "") << "{\"offset_ms\":" << observations[i].first
              << ",\"rss_bytes\":" << observations[i].second << "}";
  }
  std::cout << "]"
            << ",\"reallocation_enabled\":" << (options.reallocate_after_observe ? "true" : "false")
            << ",\"reallocation_count\":" << (options.reallocate_after_observe ? burst : 0)
            << ",\"reallocation_elapsed_ns\":" << reallocation_elapsed_ns
            << ",\"reallocation_minor_faults\":" << reallocation_minor_faults
            << ",\"reallocation_major_faults\":" << reallocation_major_faults
            << ",\"reallocation_working_set_rss_bytes\":" << reallocation_working_set_rss
            << ",\"reallocation_free_elapsed_ns\":" << reallocation_free_elapsed_ns
            << ",\"rss_after_reallocation_free_bytes\":" << rss_after_reallocation_free
            << ",\"user_cpu_ns\":" << (after.user_cpu_ns - before.user_cpu_ns)
            << ",\"system_cpu_ns\":" << (after.system_cpu_ns - before.system_cpu_ns)
            << ",\"page_faults\":{\"minor\":" << (after.minor_faults - before.minor_faults)
            << ",\"major\":" << (after.major_faults - before.major_faults)
            << "},\"checksum\":" << checksum << "}\n";
  return 0;
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
  if (options.scenario == "memory_return") return run_memory_return(options, allocator);
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
