// Read policy from each existing release library; no performance workload.
#include "mimalloc.h"
#include <stdio.h>
#include <unistd.h>
int main(void) {
  printf("{\"version\":%d,\"allow_thp\":%ld,\"minimal_purge_size_option\":%ld,"
         "\"purge_delay\":%ld,\"arena_purge_mult\":%ld,\"purge_decommits\":%ld,\"os_page_size\":%ld}\n",
    mi_version(), mi_option_get(mi_option_allow_thp), mi_option_get(mi_option_minimal_purge_size),
    mi_option_get(mi_option_purge_delay), mi_option_get(mi_option_arena_purge_mult),
    mi_option_get(mi_option_purge_decommits), sysconf(_SC_PAGESIZE));
  return 0;
}
