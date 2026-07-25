FROM rockylinux:8
RUN dnf -y install binutils cmake findutils gcc gcc-c++ git make numactl numactl-libs perf procps-ng python3 python3-pip strace which && dnf clean all
WORKDIR /work
COPY container/entrypoint.sh /usr/local/bin/mimalloc-entrypoint
RUN chmod 0755 /usr/local/bin/mimalloc-entrypoint
ENTRYPOINT ["/usr/local/bin/mimalloc-entrypoint"]
CMD ["bash"]
