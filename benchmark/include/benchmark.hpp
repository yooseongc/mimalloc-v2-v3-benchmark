#pragma once
#include <cstdint>
#include <string>
#include <vector>

struct AllocatorInfo {
  bool mimalloc_detected{false};
  int version{0};
  std::string library_path;
};

struct RunOptions {
  std::string scenario{"local_churn"};
  std::uint64_t operations{100000};
  unsigned threads{1};
  std::size_t size{64};
  std::string size_profile{"fixed"};
  std::size_t batch_size{1};
  std::string free_order{"fifo"};
  std::string touch_mode{"first-and-last"};
  std::string allocation_api{"malloc"};
  std::uint64_t idle_ms{10};
  std::uint64_t hold_ms{0};
  std::string diagnostic_ready_file;
  unsigned producer_count{1};
  unsigned consumer_count{1};
  std::size_t queue_capacity{1024};
};

AllocatorInfo detect_allocator();
bool pin_current_thread(int cpu, std::string& error);
std::vector<int> current_affinity();
