// Untimed check that malloc/free and mi_version resolve to the same library.
#include <dlfcn.h>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <set>
#include <string>

int main() {
    Dl_info info[3]{};
    const char* names[] = {"malloc", "free", "mi_version"};
    for (int i = 0; i < 3; ++i) {
        void* symbol = dlsym(RTLD_DEFAULT, names[i]);
        if (!symbol || !dladdr(symbol, &info[i]) || !info[i].dli_fname) return 2;
    }
    if (std::strcmp(info[0].dli_fname, info[2].dli_fname) != 0 ||
        std::strcmp(info[1].dli_fname, info[2].dli_fname) != 0) return 3;
    std::set<std::string> libraries;
    std::ifstream maps("/proc/self/maps");
    if (!maps) return 4;
    std::string line;
    while (std::getline(maps, line)) {
        if (line.find("libmimalloc") != std::string::npos) {
            const auto start = line.find('/');
            if (start != std::string::npos) libraries.insert(line.substr(start));
        }
    }
    if (libraries.size() != 1) return 5;
    std::printf("{\"valid\":true,\"malloc_library\":\"%s\",\"free_library\":\"%s\","
                "\"mi_version_library\":\"%s\",\"mapped_library\":\"%s\"}\n",
                info[0].dli_fname, info[1].dli_fname, info[2].dli_fname, libraries.begin()->c_str());
}
