#include "benchmark.hpp"
#include <dlfcn.h>
#include <link.h>

AllocatorInfo detect_allocator() {
  AllocatorInfo result;
  void* symbol = dlsym(RTLD_DEFAULT, "mi_version");
  if (symbol == nullptr) return result;
  using VersionFunction = int (*)();
  result.version = reinterpret_cast<VersionFunction>(symbol)();
  Dl_info info{};
  if (dladdr(symbol, &info) != 0 && info.dli_fname != nullptr) {
    result.library_path = info.dli_fname;
  }
  result.mimalloc_detected = true;
  return result;
}

