#include "remote_free.hpp"
#include "proc_metrics.hpp"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

namespace {
struct Cell {
  std::atomic<std::size_t> sequence;
  struct Message { void* pointer; std::size_t size; } value;
};

class BoundedMpmcQueue {
 public:
  explicit BoundedMpmcQueue(std::size_t requested) {
    capacity_ = 1;
    while (capacity_ < requested) capacity_ <<= 1;
    mask_ = capacity_ - 1;
    cells_.reset(new Cell[capacity_]);
    for (std::size_t index = 0; index < capacity_; ++index) cells_[index].sequence.store(index, std::memory_order_relaxed);
  }
  bool enqueue(Cell::Message value) {
    std::size_t position = enqueue_position_.load(std::memory_order_relaxed);
    for (;;) {
      Cell& cell = cells_[position & mask_];
      const std::size_t sequence = cell.sequence.load(std::memory_order_acquire);
      const std::intptr_t difference = static_cast<std::intptr_t>(sequence) - static_cast<std::intptr_t>(position);
      if (difference == 0) {
        if (enqueue_position_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) {
          cell.value = value;
          cell.sequence.store(position + 1, std::memory_order_release);
          return true;
        }
      } else if (difference < 0) return false;
      else position = enqueue_position_.load(std::memory_order_relaxed);
    }
  }
  bool dequeue(Cell::Message& value) {
    std::size_t position = dequeue_position_.load(std::memory_order_relaxed);
    for (;;) {
      Cell& cell = cells_[position & mask_];
      const std::size_t sequence = cell.sequence.load(std::memory_order_acquire);
      const std::intptr_t difference = static_cast<std::intptr_t>(sequence) - static_cast<std::intptr_t>(position + 1);
      if (difference == 0) {
        if (dequeue_position_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) {
          value = cell.value;
          cell.sequence.store(position + mask_ + 1, std::memory_order_release);
          return true;
        }
      } else if (difference < 0) return false;
      else position = dequeue_position_.load(std::memory_order_relaxed);
    }
  }
 private:
  std::unique_ptr<Cell[]> cells_;
  std::size_t capacity_{0}, mask_{0};
  std::atomic<std::size_t> enqueue_position_{0}, dequeue_position_{0};
};
}

int run_remote_free(const RunOptions& options, const AllocatorInfo& allocator) {
  const unsigned producers = options.producer_count, consumers = options.consumer_count;
  const auto allowed = current_affinity();
  if (allowed.size() < producers + consumers || options.threads != producers + consumers) {
    std::cerr << "remote_free requires thread_count == producers + consumers and enough allowed CPUs\n";
    return 4;
  }
  BoundedMpmcQueue queue(options.queue_capacity);
  const bool queue_only = options.scenario == "queue_only";
  std::atomic<unsigned> ready{0}; std::atomic<bool> start{false};
  std::atomic<std::uint64_t> consumed{0}, checksum{0}, full_waits{0}, empty_waits{0};
  std::atomic<std::uint64_t> backpressure_ns{0};
  const std::uint64_t per_producer = options.operations / producers;
  const std::uint64_t total = per_producer * producers;
  std::vector<std::thread> workers; workers.reserve(producers + consumers);
  for (unsigned producer = 0; producer < producers; ++producer) {
    workers.emplace_back([&, producer] {
      std::string error; if (!pin_current_thread(allowed[producer], error)) std::terminate();
      ready.fetch_add(1, std::memory_order_release); while (!start.load(std::memory_order_acquire)) {}
      for (std::uint64_t i = 0; i < per_producer; ++i) {
        const std::uint64_t sequence = producer * per_producer + i;
        Cell::Message value;
        if (queue_only) { value.pointer = reinterpret_cast<void*>(static_cast<std::uintptr_t>(sequence + 1)); value.size = 0; }
        else {
          const std::size_t size = options.size_profile == "mixed-wide" ? 16u << (sequence % 13) : (options.size_profile == "mixed-small" ? 16u << (sequence % 9) : options.size);
          auto* p = static_cast<unsigned char*>(std::malloc(size)); if (!p) std::terminate();
          if (options.touch_mode != "none") { p[0] = static_cast<unsigned char>(sequence); if (options.touch_mode != "first-byte") p[size - 1] = static_cast<unsigned char>(sequence >> 8); }
          value.pointer = p; value.size = size;
        }
        const auto waited = std::chrono::steady_clock::now();
        while (!queue.enqueue(value)) full_waits.fetch_add(1, std::memory_order_relaxed);
        backpressure_ns.fetch_add(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - waited).count(), std::memory_order_relaxed);
      }
    });
  }
  for (unsigned consumer = 0; consumer < consumers; ++consumer) {
    workers.emplace_back([&, consumer] {
      std::string error; if (!pin_current_thread(allowed[producers + consumer], error)) std::terminate();
      ready.fetch_add(1, std::memory_order_release); while (!start.load(std::memory_order_acquire)) {}
      while (consumed.load(std::memory_order_acquire) < total) {
        Cell::Message value{nullptr, 0};
        if (!queue.dequeue(value)) { empty_waits.fetch_add(1, std::memory_order_relaxed); continue; }
        if (queue_only) checksum.fetch_add(reinterpret_cast<std::uintptr_t>(value.pointer), std::memory_order_relaxed);
        else { auto* p = static_cast<unsigned char*>(value.pointer); checksum.fetch_add(p[0] + p[value.size - 1], std::memory_order_relaxed); std::free(p); }
        consumed.fetch_add(1, std::memory_order_release);
      }
    });
  }
  while (ready.load(std::memory_order_acquire) != producers + consumers) {}
  const ProcMetrics before = read_proc_metrics(); const auto began = std::chrono::steady_clock::now();
  start.store(true, std::memory_order_release);
  for (auto& worker : workers) worker.join();
  const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - began).count();
  const ProcMetrics after = read_proc_metrics();
  std::cout << "{\"valid\":" << (consumed == total ? "true" : "false") << ",\"scenario\":\"" << options.scenario
            << "\",\"allocator_version\":" << allocator.version << ",\"allocator_library_path\":\"" << allocator.library_path
            << "\",\"thread_count\":" << options.threads << ",\"producer_count\":" << producers << ",\"consumer_count\":" << consumers
            << ",\"queue_capacity\":" << options.queue_capacity << ",\"queue_full_wait_count\":" << full_waits << ",\"queue_empty_wait_count\":" << empty_waits
            << ",\"backpressure_ns\":" << backpressure_ns << ",\"transferred_pointer_count\":" << total << ",\"freed_pointer_count\":" << consumed
            << ",\"outstanding_pointer_count\":" << (total - consumed.load()) << ",\"operation_count\":" << total << ",\"elapsed_ns\":" << elapsed
            << ",\"touch_mode\":\"" << options.touch_mode << "\",\"peak_rss_bytes\":" << after.rss_bytes
            << ",\"user_cpu_ns\":" << (after.user_cpu_ns-before.user_cpu_ns)
            << ",\"system_cpu_ns\":" << (after.system_cpu_ns-before.system_cpu_ns)
            << ",\"page_faults\":{\"minor\":" << (after.minor_faults - before.minor_faults) << ",\"major\":" << (after.major_faults - before.major_faults)
            << "},\"checksum\":" << checksum << "}\n";
  return consumed == total ? 0 : 6;
}

int run_queue_only(const RunOptions& options, const AllocatorInfo& allocator) { return run_remote_free(options, allocator); }
