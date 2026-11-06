// Untimed regression diagnostic: first explicit C++ allocation on new pthreads.
#include <pthread.h>
#include <dlfcn.h>
#include <new>
#include <cstdio>
#include <cstdint>

static void* allocate_first(void*) {
    try {
        auto* p = new unsigned char[4096];
        p[0] = 42;
        p[4095] = 19;
        const unsigned sum = p[0] + p[4095];
        // Escaping the pointer prevents removal of new/delete in this diagnostic.
        asm volatile("" : : "r"(p) : "memory");
        delete[] p;
        return reinterpret_cast<void*>(static_cast<std::uintptr_t>(sum));
    } catch (...) {
        return nullptr;
    }
}

int main() {
    for (int n = 0; n < 1000; ++n) {
        pthread_t thread;
        void* result = nullptr;
        if (pthread_create(&thread, nullptr, allocate_first, nullptr) != 0) return 2;
        if (pthread_join(thread, &result) != 0) return 3;
        if (reinterpret_cast<std::uintptr_t>(result) != 61) return 4;
    }
    auto version = reinterpret_cast<int(*)()>(dlsym(RTLD_DEFAULT, "mi_version"));
    if (!version) return 5;
    std::printf("{\"threads\":1000,\"valid\":true,\"mi_version\":%d}\n", version());
}
