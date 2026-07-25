cmake_minimum_required(VERSION 3.16)
project(mimalloc_comparison LANGUAGES CXX)
option(BENCHMARK_WARNINGS_AS_ERRORS "Treat warnings as errors" OFF)
add_subdirectory(benchmark)

