#pragma once
#include "benchmark.hpp"
int run_remote_free(const RunOptions& options, const AllocatorInfo& allocator);
int run_queue_only(const RunOptions& options, const AllocatorInfo& allocator);
