#include "tcp_policy_record.hpp"
#include "proc_metrics.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <memory>
#include <sched.h>
#include <thread>
#include <unistd.h>
#include <utility>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

struct Message {
  unsigned char* pointer{nullptr};
  std::size_t size{0};
  std::uint64_t sequence{0};
  std::uint64_t sample_started_ns{0};
  unsigned origin{0};
  bool measured{false};
};

struct Cell {
  std::atomic<std::size_t> sequence;
  Message value;
};

class Queue {
 public:
  explicit Queue(std::size_t requested) {
    capacity_ = 1;
    while (capacity_ < requested) capacity_ <<= 1;
    mask_ = capacity_ - 1;
    cells_.reset(new Cell[capacity_]);
    for (std::size_t i = 0; i < capacity_; ++i)
      cells_[i].sequence.store(i, std::memory_order_relaxed);
  }

  bool enqueue(const Message& value) {
    std::size_t position = enqueue_.load(std::memory_order_relaxed);
    for (;;) {
      Cell& cell = cells_[position & mask_];
      const std::size_t sequence = cell.sequence.load(std::memory_order_acquire);
      const std::intptr_t difference = static_cast<std::intptr_t>(sequence) -
                                       static_cast<std::intptr_t>(position);
      if (difference == 0) {
        if (enqueue_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) {
          cell.value = value;
          update_occupancy(1);
          cell.sequence.store(position + 1, std::memory_order_release);
          return true;
        }
      } else if (difference < 0) {
        return false;
      } else {
        position = enqueue_.load(std::memory_order_relaxed);
      }
    }
  }

  bool dequeue(Message& value) {
    std::size_t position = dequeue_.load(std::memory_order_relaxed);
    for (;;) {
      Cell& cell = cells_[position & mask_];
      const std::size_t sequence = cell.sequence.load(std::memory_order_acquire);
      const std::intptr_t difference = static_cast<std::intptr_t>(sequence) -
                                       static_cast<std::intptr_t>(position + 1);
      if (difference == 0) {
        if (dequeue_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) {
          value = cell.value;
          cell.sequence.store(position + mask_ + 1, std::memory_order_release);
          occupancy_.fetch_sub(1, std::memory_order_relaxed);
          return true;
        }
      } else if (difference < 0) {
        return false;
      } else {
        position = dequeue_.load(std::memory_order_relaxed);
      }
    }
  }

  std::uint64_t max_occupancy() const { return maximum_.load(std::memory_order_relaxed); }
  void release_storage() { cells_.reset(); }

 private:
  void update_occupancy(std::uint64_t delta) {
    const std::uint64_t value = occupancy_.fetch_add(delta, std::memory_order_relaxed) + delta;
    std::uint64_t old = maximum_.load(std::memory_order_relaxed);
    while (old < value && !maximum_.compare_exchange_weak(old, value, std::memory_order_relaxed)) {}
  }
  std::unique_ptr<Cell[]> cells_;
  std::size_t capacity_{0}, mask_{0};
  std::atomic<std::size_t> enqueue_{0}, dequeue_{0};
  std::atomic<std::uint64_t> occupancy_{0}, maximum_{0};
};

void enqueue_with_backpressure(Queue& queue, const Message& message,
                               std::atomic<std::uint64_t>& full_waits,
                               std::atomic<std::uint64_t>& backpressure_ns) {
  if (queue.enqueue(message)) return;
  const auto began = Clock::now();
  do {
    full_waits.fetch_add(1, std::memory_order_relaxed);
    std::this_thread::yield();
  } while (!queue.enqueue(message));
  backpressure_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - began).count(),
      std::memory_order_relaxed);
}

struct Counters {
  std::atomic<std::uint64_t> allocated{0}, policy{0}, returned{0}, recorded{0}, freed{0};
  std::atomic<std::uint64_t> ingress_full{0}, ingress_empty{0}, return_full{0}, return_empty{0};
  std::atomic<std::uint64_t> record_full{0}, record_empty{0}, backpressure_ns{0};
  std::atomic<std::uint64_t> checksum_allocate{0}, checksum_policy{0}, checksum_return{0}, checksum_record{0};
  std::atomic<std::uint64_t> duplicate{0}, bank_seals{0}, bank_saturated{0};
};

struct RoleCpu {
  std::atomic<std::uint64_t> tcpio{0}, policy{0}, record{0};
};

std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
}

std::uint64_t thread_cpu_ns() {
  timespec value{};
  if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &value) != 0) return 0;
  return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL +
         static_cast<std::uint64_t>(value.tv_nsec);
}

std::uint64_t mix(std::uint64_t value) {
  value ^= value >> 30; value *= 0xbf58476d1ce4e5b9ULL;
  value ^= value >> 27; value *= 0x94d049bb133111ebULL;
  return value ^ (value >> 31);
}

std::size_t payload_size(std::uint64_t sequence, std::uint64_t seed) {
  const unsigned bucket = static_cast<unsigned>(mix(sequence ^ seed) % 100);
  if (bucket < 10) return 64;
  if (bucket < 25) return 256;
  if (bucket < 50) return 1024;
  if (bucket < 80) return 4096;
  if (bucket < 95) return 16384;
  return 65536;
}

void ingress_work(Message& message, bool service) {
  if (service) {
    std::memset(message.pointer, static_cast<int>(message.sequence), message.size);
  } else {
    message.pointer[0] = static_cast<unsigned char>(message.sequence);
    message.pointer[message.size - 1] = static_cast<unsigned char>(message.sequence >> 8);
  }
}

void policy_work(Message& message, bool service) {
  if (!service) {
    message.pointer[0] ^= 0x5a;
    message.pointer[message.size - 1] ^= 0xa5;
    return;
  }
  std::uint64_t value = message.sequence;
  for (std::size_t offset = 0; offset < message.size; offset += 64)
    value = mix(value + message.pointer[offset] + offset);
  message.pointer[message.size / 2] ^= static_cast<unsigned char>(value);
}

void return_work(Message& message, bool service) {
  if (!service) {
    message.pointer[0] ^= 0x5a;
    message.pointer[message.size - 1] ^= 0xa5;
    return;
  }
  const unsigned char key = static_cast<unsigned char>(message.sequence * 33u);
  for (std::size_t offset = 0; offset < message.size; ++offset) message.pointer[offset] ^= key;
}

void record_work(const Message& message, bool service, std::uint64_t& checksum) {
  if (!service) {
    checksum += message.pointer[0] + message.pointer[message.size - 1];
    return;
  }
  for (std::size_t offset = 0; offset < message.size; offset += 64)
    checksum = mix(checksum + message.pointer[offset] + offset);
}

double percentile(const std::vector<std::uint64_t>& sorted, double p) {
  if (sorted.empty()) return 0.0;
  const double index = p * static_cast<double>(sorted.size() - 1);
  const std::size_t low = static_cast<std::size_t>(index);
  const std::size_t high = std::min(low + 1, sorted.size() - 1);
  return sorted[low] + (sorted[high] - sorted[low]) * (index - low);
}

void add_cpu(RoleCpu& role, std::atomic<std::uint64_t>& target, std::uint64_t began) {
  target.fetch_add(thread_cpu_ns() - began, std::memory_order_relaxed);
  (void)role;
}

}  // namespace

int run_tcp_policy_record(const RunOptions& o, const AllocatorInfo& allocator) {
  const unsigned total_workers = o.tcpio_count + o.policy_count + o.record_count;
  const auto allowed = current_affinity();
  if (o.topology == "isolated" && allowed.size() < total_workers) {
    std::cerr << "isolated topology requires one allowed CPU per worker\n";
    return 4;
  }
  if (o.topology == "service-like" && allowed.size() < o.tcpio_count) {
    std::cerr << "service-like topology requires one allowed CPU per tcpio worker\n";
    return 4;
  }
  if (o.threads != total_workers) {
    std::cerr << "thread_count must equal tcpio + policy + record\n";
    return 4;
  }

  Queue ingress(o.queue_capacity);
  std::vector<std::unique_ptr<Queue>> returns, records;
  for (unsigned i = 0; i < o.tcpio_count; ++i)
    returns.emplace_back(new Queue(o.return_queue_capacity));
  for (unsigned i = 0; i < o.record_count; ++i)
    records.emplace_back(new Queue(o.record_queue_capacity));

  Counters measured, warm;
  RoleCpu role_cpu;
  std::atomic<int> phase{0};  // 0=created, 1=warm-up, 2=paused, 3=measured, 4=stop
  std::atomic<unsigned> ready{0}, paused{0};
  std::vector<int> cpu_start(total_workers, -1), cpu_end(total_workers, -1);
  std::vector<unsigned char> seen(static_cast<std::size_t>(o.operations), 0);
  std::vector<std::uint32_t> measured_sizes(static_cast<std::size_t>(o.operations));
  std::vector<std::uint32_t> warm_sizes(static_cast<std::size_t>(o.warmup_count));
  std::uint64_t size_counts[6]{0, 0, 0, 0, 0, 0};
  const std::size_t profile_sizes[6]{64, 256, 1024, 4096, 16384, 65536};
  for (std::uint64_t sequence = 0; sequence < o.operations; ++sequence) {
    const auto size = static_cast<std::uint32_t>(payload_size(sequence, o.seed));
    measured_sizes[static_cast<std::size_t>(sequence)] = size;
    for (unsigned i = 0; i < 6; ++i) if (size == profile_sizes[i]) ++size_counts[i];
  }
  for (std::uint64_t sequence = 0; sequence < o.warmup_count; ++sequence)
    warm_sizes[static_cast<std::size_t>(sequence)] =
        static_cast<std::uint32_t>(payload_size(sequence, o.seed));
  std::vector<std::vector<std::uint64_t>> latency(o.record_count);
  std::vector<std::thread> workers;
  workers.reserve(total_workers);
  const bool service = o.stage_work == "service";
  const bool queue_only = o.scenario == "tcp_policy_record_queue_only";

  auto phase_total = [&](bool is_measured) { return is_measured ? o.operations : o.warmup_count; };
  auto counters = [&](bool is_measured) -> Counters& { return is_measured ? measured : warm; };

  for (unsigned id = 0; id < o.tcpio_count; ++id) {
    workers.emplace_back([&, id] {
      std::string error;
      const std::size_t cpu_index = o.topology == "service-like" ? id * 2u : id;
      if (cpu_index >= allowed.size() || !pin_current_thread(allowed[cpu_index], error)) std::terminate();
      cpu_start[id] = sched_getcpu();
      ready.fetch_add(1, std::memory_order_release);
      int prior_phase = 0;
      std::uint64_t generated_warm = id, generated_measured = id, cpu_began = 0;
      bool pause_ack = false;
      bool ingress_pending = false;
      Message pending_message;
      Clock::time_point ingress_wait_began;
      while (phase.load(std::memory_order_acquire) != 4) {
        const int current = phase.load(std::memory_order_acquire);
        if (current == 0 || current == 2) {
          if (current == 2 && !pause_ack) {
            paused.fetch_add(1, std::memory_order_release);
            pause_ack = true;
          }
          std::this_thread::yield();
          prior_phase = current;
          continue;
        }
        if (current != prior_phase) {
          pause_ack = false;
          if (current == 3) cpu_began = thread_cpu_ns();
          prior_phase = current;
        }
        const bool is_measured = current == 3;
        Counters& stats = counters(is_measured);
        Message message;
        if (returns[id]->dequeue(message)) {
          if (!queue_only) return_work(message, service);
          stats.returned.fetch_add(1, std::memory_order_relaxed);
          stats.checksum_return.fetch_add(message.sequence + 1, std::memory_order_relaxed);
          const unsigned shard = id % o.record_count;
          enqueue_with_backpressure(*records[shard], message, stats.record_full, stats.backpressure_ns);
          stats.recorded.fetch_add(1, std::memory_order_release);
          continue;
        }
        stats.return_empty.fetch_add(1, std::memory_order_relaxed);
        if (ingress_pending) {
          if (ingress.enqueue(pending_message)) {
            stats.backpressure_ns.fetch_add(
                std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - ingress_wait_began).count(),
                std::memory_order_relaxed);
            ingress_pending = false;
          } else {
            stats.ingress_full.fetch_add(1, std::memory_order_relaxed);
          }
          continue;
        }
        std::uint64_t& generated = is_measured ? generated_measured : generated_warm;
        const std::uint64_t target = phase_total(is_measured);
        if (generated < target) {
          message.sequence = generated;
          message.origin = id;
          message.measured = is_measured;
          message.size = queue_only ? 0 :
              (is_measured ? measured_sizes[static_cast<std::size_t>(generated)]
                           : warm_sizes[static_cast<std::size_t>(generated)]);
          if (queue_only) {
            message.pointer = reinterpret_cast<unsigned char*>(
                static_cast<std::uintptr_t>(generated + 1));
          } else {
            message.pointer = static_cast<unsigned char*>(std::malloc(message.size));
            if (!message.pointer) std::terminate();
            ingress_work(message, service);
          }
          if (is_measured && mix(generated ^ o.seed) % o.latency_sample_rate == 0)
            message.sample_started_ns = now_ns();
          stats.allocated.fetch_add(1, std::memory_order_relaxed);
          stats.checksum_allocate.fetch_add(generated + 1, std::memory_order_relaxed);
          if (!ingress.enqueue(message)) {
            stats.ingress_full.fetch_add(1, std::memory_order_relaxed);
            pending_message = message;
            ingress_pending = true;
            ingress_wait_began = Clock::now();
          }
          generated += o.tcpio_count;
        } else {
          std::this_thread::yield();
        }
      }
      if (cpu_began) add_cpu(role_cpu, role_cpu.tcpio, cpu_began);
      cpu_end[id] = sched_getcpu();
    });
  }

  for (unsigned id = 0; id < o.policy_count; ++id) {
    const unsigned worker_id = o.tcpio_count + id;
    workers.emplace_back([&, worker_id] {
      std::string error;
      if (o.topology == "isolated" &&
          !pin_current_thread(allowed[worker_id], error)) std::terminate();
      cpu_start[worker_id] = sched_getcpu();
      ready.fetch_add(1, std::memory_order_release);
      int prior_phase = 0; bool pause_ack = false; std::uint64_t cpu_began = 0;
      while (phase.load(std::memory_order_acquire) != 4) {
        const int current = phase.load(std::memory_order_acquire);
        if (current == 0 || current == 2) {
          if (current == 2 && !pause_ack) { paused.fetch_add(1, std::memory_order_release); pause_ack = true; }
          std::this_thread::yield(); prior_phase = current; continue;
        }
        if (current != prior_phase) {
          pause_ack = false; if (current == 3) cpu_began = thread_cpu_ns(); prior_phase = current;
        }
        Message message;
        Counters& stats = counters(current == 3);
        if (!ingress.dequeue(message)) {
          stats.ingress_empty.fetch_add(1, std::memory_order_relaxed);
          std::this_thread::yield(); continue;
        }
        if (!queue_only) policy_work(message, service);
        stats.policy.fetch_add(1, std::memory_order_relaxed);
        stats.checksum_policy.fetch_add(message.sequence + 1, std::memory_order_relaxed);
        enqueue_with_backpressure(*returns[message.origin], message, stats.return_full, stats.backpressure_ns);
      }
      if (cpu_began) add_cpu(role_cpu, role_cpu.policy, cpu_began);
      cpu_end[worker_id] = sched_getcpu();
    });
  }

  for (unsigned id = 0; id < o.record_count; ++id) {
    const unsigned worker_id = o.tcpio_count + o.policy_count + id;
    workers.emplace_back([&, id, worker_id] {
      std::string error;
      if (o.topology == "isolated" &&
          !pin_current_thread(allowed[worker_id], error)) std::terminate();
      cpu_start[worker_id] = sched_getcpu();
      ready.fetch_add(1, std::memory_order_release);
      int prior_phase = 0; bool pause_ack = false; std::uint64_t cpu_began = 0;
      std::vector<Message> banks[2]; unsigned active = 0;
      banks[0].reserve(o.record_bank_items); banks[1].reserve(o.record_bank_items);
      std::size_t bank_bytes = 0;
      std::uint64_t record_checksum = 0;
      auto flush = [&](Counters& stats) {
        auto& bank = banks[active];
        if (bank.empty()) return;
        const unsigned sealed = active;
        active ^= 1u;
        banks[active].clear();
        bank_bytes = 0;
        stats.bank_seals.fetch_add(1, std::memory_order_relaxed);
        for (const Message& message : banks[sealed]) {
          if (!queue_only) record_work(message, service, record_checksum);
          stats.checksum_record.fetch_add(message.sequence + 1, std::memory_order_relaxed);
          if (message.measured) {
            if (message.sequence >= seen.size() || seen[message.sequence]++)
              stats.duplicate.fetch_add(1, std::memory_order_relaxed);
            if (message.sample_started_ns)
              latency[id].push_back(now_ns() - message.sample_started_ns);
          }
          if (!queue_only) std::free(message.pointer);
          stats.freed.fetch_add(1, std::memory_order_release);
        }
        banks[sealed].clear();
      };
      while (phase.load(std::memory_order_acquire) != 4) {
        const int current = phase.load(std::memory_order_acquire);
        if (current == 0 || current == 2) {
          if (current == 2 && !pause_ack) { paused.fetch_add(1, std::memory_order_release); pause_ack = true; }
          std::this_thread::yield(); prior_phase = current; continue;
        }
        if (current != prior_phase) {
          pause_ack = false; if (current == 3) cpu_began = thread_cpu_ns(); prior_phase = current;
        }
        Counters& stats = counters(current == 3);
        Message message;
        if (records[id]->dequeue(message)) {
          banks[active].push_back(message);
          bank_bytes += message.size;
          if (bank_bytes >= o.record_bank_bytes || banks[active].size() >= o.record_bank_items) {
            if (bank_bytes >= o.record_bank_bytes && banks[active].size() >= o.record_bank_items)
              stats.bank_saturated.fetch_add(1, std::memory_order_relaxed);
            flush(stats);
          }
          continue;
        }
        stats.record_empty.fetch_add(1, std::memory_order_relaxed);
        const std::uint64_t target = phase_total(current == 3);
        if (stats.recorded.load(std::memory_order_acquire) == target) flush(stats);
        std::this_thread::yield();
      }
      Counters& stats = measured.recorded.load() ? measured : warm;
      flush(stats);
      if (cpu_began) add_cpu(role_cpu, role_cpu.record, cpu_began);
      cpu_end[worker_id] = sched_getcpu();
      (void)record_checksum;
    });
  }

  while (ready.load(std::memory_order_acquire) != total_workers) std::this_thread::yield();
  if (o.warmup_count) {
    phase.store(1, std::memory_order_release);
    while (warm.freed.load(std::memory_order_acquire) != o.warmup_count) std::this_thread::yield();
  }
  phase.store(2, std::memory_order_release);
  while (paused.load(std::memory_order_acquire) != total_workers) std::this_thread::yield();
  if (!o.diagnostic_ready_file.empty()) {
    std::ofstream ready_file(o.diagnostic_ready_file, std::ios::trunc);
    if (!ready_file) {
      phase.store(4, std::memory_order_release);
      for (auto& worker : workers) worker.join();
      std::cerr << "cannot write diagnostic ready file\n";
      return 4;
    }
    ready_file << getpid() << "\n";
  }

  const ProcMetrics before = read_proc_metrics();
  const auto began = Clock::now();
  phase.store(3, std::memory_order_release);
  while (measured.freed.load(std::memory_order_acquire) != o.operations) std::this_thread::yield();
  const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - began).count();
  phase.store(4, std::memory_order_release);
  for (auto& worker : workers) worker.join();
  const ProcMetrics after = read_proc_metrics();

  std::vector<std::uint64_t> samples;
  for (auto& shard : latency) samples.insert(samples.end(), shard.begin(), shard.end());
  std::sort(samples.begin(), samples.end());
  std::uint64_t ingress_max = ingress.max_occupancy(), return_max = 0, record_max = 0;
  for (const auto& queue : returns) return_max = std::max(return_max, queue->max_occupancy());
  for (const auto& queue : records) record_max = std::max(record_max, queue->max_occupancy());
  const std::uint64_t expected_checksum = o.operations * (o.operations + 1) / 2;
  const std::uint64_t seen_count = static_cast<std::uint64_t>(
      std::count(seen.begin(), seen.end(), static_cast<unsigned char>(1)));
  const bool correct = measured.allocated == o.operations && measured.policy == o.operations &&
      measured.returned == o.operations && measured.recorded == o.operations &&
      measured.freed == o.operations && measured.duplicate == 0 && seen_count == o.operations &&
      measured.checksum_allocate == expected_checksum && measured.checksum_policy == expected_checksum &&
      measured.checksum_return == expected_checksum && measured.checksum_record == expected_checksum;

  // The response window begins only after payloads and harness-owned dynamic
  // buffers are released. This keeps VmRSS retention from being dominated by
  // the deterministic size table or correctness bookkeeping.
  ingress.release_storage();
  returns.clear();
  records.clear();
  std::vector<unsigned char>().swap(seen);
  std::vector<std::uint32_t>().swap(measured_sizes);
  std::vector<std::uint32_t>().swap(warm_sizes);

  std::vector<std::pair<std::uint64_t, std::uint64_t>> post_drain_rss;
  post_drain_rss.emplace_back(0, read_proc_metrics().rss_bytes);
  if (o.post_drain_observe_ms > 0) {
    const auto observe_began = Clock::now();
    std::uint64_t offset = o.post_drain_sample_ms;
    while (offset < o.post_drain_observe_ms) {
      std::this_thread::sleep_until(
          observe_began + std::chrono::milliseconds(offset));
      post_drain_rss.emplace_back(offset, read_proc_metrics().rss_bytes);
      offset += o.post_drain_sample_ms;
    }
    std::this_thread::sleep_until(
        observe_began + std::chrono::milliseconds(o.post_drain_observe_ms));
    post_drain_rss.emplace_back(
        o.post_drain_observe_ms, read_proc_metrics().rss_bytes);
  }

  std::cout << "{\"valid\":" << (correct ? "true" : "false")
            << ",\"scenario\":\"" << o.scenario << "\",\"allocator_version\":" << allocator.version
            << ",\"allocator_library_path\":\"" << allocator.library_path << "\""
            << ",\"thread_count\":" << total_workers << ",\"tcpio_count\":" << o.tcpio_count
            << ",\"policy_count\":" << o.policy_count << ",\"record_count\":" << o.record_count
            << ",\"topology\":\"" << o.topology << "\",\"payload_profile\":\"" << o.payload_profile
            << "\",\"payload_size_counts\":{\"64\":" << size_counts[0] << ",\"256\":" << size_counts[1]
            << ",\"1024\":" << size_counts[2] << ",\"4096\":" << size_counts[3]
            << ",\"16384\":" << size_counts[4] << ",\"65536\":" << size_counts[5] << "}"
            << ",\"stage_work\":\"" << o.stage_work << "\",\"operation_count\":" << o.operations
            << ",\"warmup_count\":" << o.warmup_count << ",\"elapsed_ns\":" << elapsed
            << ",\"transferred_counts\":{\"allocated\":" << measured.allocated << ",\"policy\":" << measured.policy
            << ",\"returned_to_origin\":" << measured.returned << ",\"recorded\":" << measured.recorded
            << ",\"freed\":" << measured.freed << "},\"outstanding_pointer_count\":" << (o.operations - measured.freed)
            << ",\"queue_max_occupancy\":{\"ingress\":" << ingress_max << ",\"return\":" << return_max
            << ",\"record\":" << record_max << "},\"queue_waits\":{\"ingress_full\":" << measured.ingress_full
            << ",\"ingress_empty\":" << measured.ingress_empty << ",\"return_full\":" << measured.return_full
            << ",\"return_empty\":" << measured.return_empty << ",\"record_full\":" << measured.record_full
            << ",\"record_empty\":" << measured.record_empty << "},\"backpressure_ns\":" << measured.backpressure_ns
            << ",\"record_bank_seals\":" << measured.bank_seals << ",\"record_bank_saturation_count\":" << measured.bank_saturated
            << ",\"role_cpu_ns\":{\"tcpio\":" << role_cpu.tcpio << ",\"policy\":" << role_cpu.policy
            << ",\"record\":" << role_cpu.record << "},\"latency_sample_count\":" << samples.size()
            << ",\"latency_percentiles_ns\":{\"p50\":" << percentile(samples, .50)
            << ",\"p90\":" << percentile(samples, .90) << ",\"p95\":" << percentile(samples, .95)
            << ",\"p99\":" << percentile(samples, .99) << ",\"p99_9\":" << percentile(samples, .999)
            << ",\"max\":" << (samples.empty() ? 0 : samples.back()) << "}"
            << ",\"worker_cpu_start\":[";
  for (std::size_t i = 0; i < cpu_start.size(); ++i) std::cout << (i ? "," : "") << cpu_start[i];
  std::cout << "],\"worker_cpu_end\":[";
  for (std::size_t i = 0; i < cpu_end.size(); ++i) std::cout << (i ? "," : "") << cpu_end[i];
  std::cout << "],\"post_drain_vm_rss\":[";
  for (std::size_t i = 0; i < post_drain_rss.size(); ++i) {
    std::cout << (i ? "," : "") << "{\"offset_ms\":" << post_drain_rss[i].first
              << ",\"vm_rss_bytes\":" << post_drain_rss[i].second << "}";
  }
  std::cout << "],\"post_drain_observe_ms\":" << o.post_drain_observe_ms
            << ",\"peak_rss_bytes\":" << after.rss_bytes
            << ",\"user_cpu_ns\":" << (after.user_cpu_ns - before.user_cpu_ns)
            << ",\"system_cpu_ns\":" << (after.system_cpu_ns - before.system_cpu_ns)
            << ",\"page_faults\":{\"minor\":" << (after.minor_faults - before.minor_faults)
            << ",\"major\":" << (after.major_faults - before.major_faults)
            << "},\"checksum\":" << measured.checksum_record << "}\n";
  return correct ? 0 : 6;
}
