add_executable(mimalloc-bench
  src/main.cpp
  src/remote_free.cpp
  src/memory_scenarios.cpp
  src/proc_metrics.cpp
  src/allocator_detector.cpp
  src/affinity.cpp
)
target_compile_features(mimalloc-bench PRIVATE cxx_std_17)
target_compile_options(mimalloc-bench PRIVATE
  -O3 -DNDEBUG -fno-builtin-malloc -fno-builtin-free -fno-builtin-realloc
  -Wall -Wextra -Wpedantic
)
if(BENCHMARK_WARNINGS_AS_ERRORS)
  target_compile_options(mimalloc-bench PRIVATE -Werror)
endif()
target_include_directories(mimalloc-bench PRIVATE include)
target_link_libraries(mimalloc-bench PRIVATE dl pthread)
