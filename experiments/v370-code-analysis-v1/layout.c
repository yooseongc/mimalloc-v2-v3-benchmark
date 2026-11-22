#include <stddef.h>
#include <stdio.h>
#include "mimalloc/types.h"
int main(void) {
 printf("{\"large_pages\":%d,\"small_max\":%zu,\"medium_max\":%zu,\"large_max\":%zu,\"page_sizeof\":%zu,\"xthread_free_offset\":%zu,\"free_offset\":%zu,\"local_free_offset\":%zu,\"page_start_offset\":%zu,\"secure\":%d,\"stats\":%d,\"profile\":%d}\n", MI_ENABLE_LARGE_PAGES,(size_t)MI_SMALL_MAX_OBJ_SIZE,(size_t)MI_MEDIUM_MAX_OBJ_SIZE,(size_t)MI_LARGE_MAX_OBJ_SIZE,sizeof(mi_page_t),offsetof(mi_page_t,xthread_free),offsetof(mi_page_t,free),offsetof(mi_page_t,local_free),offsetof(mi_page_t,page_start),MI_SECURE,MI_STATS,MI_PROFILE);
 return 0;
}