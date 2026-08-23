#include "benchmark.hpp"
#include "remote_free.hpp"
#include "memory_scenarios.hpp"
#include "proc_metrics.hpp"
#include "tcp_policy_record.hpp"
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <new>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {
struct alignas(64) WorkerResult { std::uint64_t checksum{0}; std::uint64_t allocations{0}; };
std::uint64_t parse_u64(const char* text) { return std::strtoull(text, nullptr, 10); }

bool parse_args(int argc, char** argv, RunOptions& o) {
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--scenario") == 0 && i + 1 < argc) o.scenario = argv[++i];
    else if (std::strcmp(argv[i], "--operations") == 0 && i + 1 < argc) o.operations = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--threads") == 0 && i + 1 < argc) o.threads = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--size") == 0 && i + 1 < argc) o.size = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--size-profile") == 0 && i + 1 < argc) o.size_profile = argv[++i];
    else if (std::strcmp(argv[i], "--batch-size") == 0 && i + 1 < argc) o.batch_size = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--free-order") == 0 && i + 1 < argc) o.free_order = argv[++i];
    else if (std::strcmp(argv[i], "--touch-mode") == 0 && i + 1 < argc) o.touch_mode = argv[++i];
    else if (std::strcmp(argv[i], "--allocation-api") == 0 && i + 1 < argc) o.allocation_api = argv[++i];
    else if (std::strcmp(argv[i], "--idle-ms") == 0 && i + 1 < argc) o.idle_ms = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--hold-ms") == 0 && i + 1 < argc) o.hold_ms = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--memory-return-mode") == 0 && i + 1 < argc) o.memory_return_mode = argv[++i];
    else if (std::strcmp(argv[i], "--memory-action-interval-ms") == 0 && i + 1 < argc) o.memory_action_interval_ms = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--reallocate-after-observe") == 0 && i + 1 < argc) o.reallocate_after_observe = parse_u64(argv[++i]) != 0;
    else if (std::strcmp(argv[i], "--diagnostic-ready-file") == 0 && i + 1 < argc) o.diagnostic_ready_file = argv[++i];
    else if (std::strcmp(argv[i], "--producers") == 0 && i + 1 < argc) o.producer_count = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--consumers") == 0 && i + 1 < argc) o.consumer_count = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--queue-capacity") == 0 && i + 1 < argc) o.queue_capacity = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--tcpio") == 0 && i + 1 < argc) o.tcpio_count = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--policy") == 0 && i + 1 < argc) o.policy_count = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--record") == 0 && i + 1 < argc) o.record_count = static_cast<unsigned>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--return-queue-capacity") == 0 && i + 1 < argc) o.return_queue_capacity = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--record-queue-capacity") == 0 && i + 1 < argc) o.record_queue_capacity = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--record-bank-bytes") == 0 && i + 1 < argc) o.record_bank_bytes = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--record-bank-items") == 0 && i + 1 < argc) o.record_bank_items = static_cast<std::size_t>(parse_u64(argv[++i]));
    else if (std::strcmp(argv[i], "--payload-profile") == 0 && i + 1 < argc) o.payload_profile = argv[++i];
    else if (std::strcmp(argv[i], "--stage-work") == 0 && i + 1 < argc) o.stage_work = argv[++i];
    else if (std::strcmp(argv[i], "--topology") == 0 && i + 1 < argc) o.topology = argv[++i];
    else if (std::strcmp(argv[i], "--warmup-count") == 0 && i + 1 < argc) o.warmup_count = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc) o.seed = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--latency-sample-rate") == 0 && i + 1 < argc) o.latency_sample_rate = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--post-drain-observe-ms") == 0 && i + 1 < argc) o.post_drain_observe_ms = parse_u64(argv[++i]);
    else if (std::strcmp(argv[i], "--post-drain-sample-ms") == 0 && i + 1 < argc) o.post_drain_sample_ms = parse_u64(argv[++i]);
    else return false;
  }
  return o.threads > 0 && o.size > 0 && o.batch_size > 0 && o.producer_count > 0 && o.consumer_count > 0 && o.queue_capacity > 1
      && o.tcpio_count > 0 && o.policy_count > 0 && o.record_count > 0
      && o.return_queue_capacity > 1 && o.record_queue_capacity > 1
      && o.record_bank_bytes > 0 && o.record_bank_items > 0 && o.latency_sample_rate > 0
      && o.post_drain_sample_ms > 0
      && o.memory_action_interval_ms > 0
      && o.payload_profile == "tcp-proxy-v1"
      && (o.stage_work == "allocator" || o.stage_work == "service")
      && (o.topology == "isolated" || o.topology == "service-like")
      && (o.memory_return_mode == "passive" || o.memory_return_mode == "allocator-activity" || o.memory_return_mode == "collect-normal" || o.memory_return_mode == "collect-force")
      && (o.size_profile == "fixed" || o.size_profile == "mixed-small" || o.size_profile == "mixed-wide")
      && (o.free_order == "fifo" || o.free_order == "lifo" || o.free_order == "random")
      && (o.touch_mode == "none" || o.touch_mode == "first-byte" || o.touch_mode == "first-and-last" || o.touch_mode == "per-cache-line" || o.touch_mode == "per-page" || o.touch_mode == "full-write")
      && (o.allocation_api == "malloc" || o.allocation_api == "cpp-new" || o.allocation_api == "aligned" || o.allocation_api == "realloc");
}
}

int main(int argc, char** argv) {
  RunOptions options;
  if (!parse_args(argc, argv, options) || (options.scenario != "local_churn" && options.scenario != "remote_free" && options.scenario != "queue_only" && options.scenario != "lifetime_mix" && options.scenario != "burst_purge" && options.scenario != "memory_return" && options.scenario != "thread_churn" && options.scenario != "large_alloc" && options.scenario != "tcp_policy_record" && options.scenario != "tcp_policy_record_queue_only")) {
    std::cerr << "usage: mimalloc-bench --scenario local_churn --operations N --threads N --size N\n";
    return 2;
  }
  const AllocatorInfo allocator = detect_allocator();
  if (!allocator.mimalloc_detected) {
    std::cerr << "allocator validation failed: mi_version was not resolved\n";
    return 3;
  }
  const bool pipeline_scenario = options.scenario == "tcp_policy_record" ||
                                 options.scenario == "tcp_policy_record_queue_only";
  if (!options.diagnostic_ready_file.empty() && !pipeline_scenario) {
    std::ofstream ready(options.diagnostic_ready_file, std::ios::trunc);
    if (!ready) {
      std::cerr << "cannot write diagnostic ready file\n";
      return 4;
    }
    ready << getpid() << "\n";
  }
  if (options.scenario == "remote_free") return run_remote_free(options, allocator);
  if (options.scenario == "queue_only") return run_queue_only(options, allocator);
  if (options.scenario == "tcp_policy_record" || options.scenario == "tcp_policy_record_queue_only")
    return run_tcp_policy_record(options, allocator);
  if (options.scenario != "local_churn") return run_memory_scenario(options, allocator);
  const auto allowed = current_affinity();
  if (allowed.empty()) {
    std::cerr << "no CPUs in current affinity set\n";
    return 4;
  }

  std::atomic<unsigned> ready{0};
  std::atomic<bool> start{false};
  std::vector<WorkerResult> results(options.threads);
  std::vector<std::thread> workers;
  workers.reserve(options.threads);
  for (unsigned worker = 0; worker < options.threads; ++worker) {
    workers.emplace_back([&, worker] {
      std::string error;
      // Oversubscription is an explicit Tier 3 condition: workers round-robin
      // through the fixed cpuset instead of silently escaping it.
      if (!pin_current_thread(allowed[worker % allowed.size()], error)) std::terminate();
      ready.fetch_add(1, std::memory_order_release);
      while (!start.load(std::memory_order_acquire)) {}
      WorkerResult local;
      const std::uint64_t count = options.operations / options.threads;
      std::vector<unsigned char*> pointers;
      pointers.reserve(options.batch_size);
      std::vector<std::size_t> sizes;
      sizes.reserve(options.batch_size);
      for (std::uint64_t base = 0; base < count; base += options.batch_size) {
        pointers.clear(); sizes.clear();
        const std::uint64_t end = std::min(count, base + options.batch_size);
        for (std::uint64_t i = base; i < end; ++i) {
          std::size_t size = options.size;
          if (options.size_profile == "mixed-small") size = 16u << (i % 9);
          if (options.size_profile == "mixed-wide") size = 16u << (i % 13);
          unsigned char* p = nullptr;
          if (options.allocation_api == "cpp-new") {
            p = static_cast<unsigned char*>(::operator new(size));
          } else if (options.allocation_api == "aligned") {
            void* raw = nullptr;
            if (posix_memalign(&raw, 64, size) == 0) p = static_cast<unsigned char*>(raw);
          } else if (options.allocation_api == "realloc") {
            const std::size_t initial = std::max<std::size_t>(16, size / 2);
            p = static_cast<unsigned char*>(std::malloc(initial));
            if (p != nullptr) p = static_cast<unsigned char*>(std::realloc(p, size));
          } else {
            p = static_cast<unsigned char*>(std::malloc(size));
          }
          if (p == nullptr) std::terminate();
          if (options.touch_mode != "none") {
            p[0] = static_cast<unsigned char>(i); local.checksum += p[0];
            if (options.touch_mode != "first-byte") {
              p[size - 1] = static_cast<unsigned char>(i >> 8); local.checksum += p[size - 1];
              if (options.touch_mode == "per-cache-line" || options.touch_mode == "per-page" || options.touch_mode == "full-write") {
                const std::size_t stride = options.touch_mode == "per-cache-line" ? 64 : 4096;
                for (std::size_t offset = 0; offset < size; offset += stride) { p[offset] = static_cast<unsigned char>(i + offset); local.checksum += p[offset]; }
                if (options.touch_mode == "full-write") { std::memset(p, static_cast<int>(i), size); local.checksum += p[size / 2]; }
              }
            }
          }
          ++local.allocations;
          pointers.push_back(p); sizes.push_back(size);
        }
        if (options.free_order == "random") {
          std::uint64_t state = base + worker + 1;
          for (std::size_t n = pointers.size(); n > 1; --n) { state = state * 6364136223846793005ULL + 1; std::swap(pointers[n-1], pointers[state % n]); }
        }
        if (options.free_order == "lifo") std::reverse(pointers.begin(), pointers.end());
        for (auto* p : pointers) {
          if (options.allocation_api == "cpp-new") ::operator delete(p);
          else std::free(p);
        }
      }
      results[worker] = local;
    });
  }
  while (ready.load(std::memory_order_acquire) != options.threads) {}
  const ProcMetrics metrics_before = read_proc_metrics();
  const auto began = std::chrono::steady_clock::now();
  start.store(true, std::memory_order_release);
  for (auto& worker : workers) worker.join();
  const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - began).count();
  const ProcMetrics metrics_after = read_proc_metrics();

  std::uint64_t checksum = 0, allocations = 0;
  for (const auto& r : results) { checksum += r.checksum; allocations += r.allocations; }
  std::cout << "{\"valid\":true,\"scenario\":\"local_churn\",\"allocator_version\":" << allocator.version
            << ",\"allocator_library_path\":\"" << allocator.library_path << "\",\"thread_count\":" << options.threads
            << ",\"size_profile\":\"" << options.size_profile << "\",\"operation_count\":" << allocations << ",\"elapsed_ns\":" << elapsed
            << ",\"batch_size\":" << options.batch_size << ",\"free_order\":\"" << options.free_order << "\""
            << ",\"touch_mode\":\"" << options.touch_mode << "\""
            << ",\"allocation_api\":\"" << options.allocation_api << "\""
            << ",\"peak_rss_bytes\":" << metrics_after.rss_bytes
            << ",\"user_cpu_ns\":" << (metrics_after.user_cpu_ns-metrics_before.user_cpu_ns)
            << ",\"system_cpu_ns\":" << (metrics_after.system_cpu_ns-metrics_before.system_cpu_ns)
            << ",\"page_faults\":{\"minor\":" << (metrics_after.minor_faults-metrics_before.minor_faults) << ",\"major\":" << (metrics_after.major_faults-metrics_before.major_faults) << "},\"checksum\":" << checksum << "}\n";
  return allocations == (options.operations / options.threads) * options.threads ? 0 : 5;
}
