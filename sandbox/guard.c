#define _GNU_SOURCE
#include <linux/landlock.h>
#include <linux/sched.h>
#include <linux/capability.h>
#include <sched.h>
#include <seccomp.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifndef LANDLOCK_ACCESS_FS_TRUNCATE
#define LANDLOCK_ACCESS_FS_TRUNCATE (1ULL << 14)
#endif

/* This trusted launcher runs ONLY in the dedicated runner container. Fail closed. */
static void die(void) { perror("sandbox security setup"); exit(125); }
static void limit(int kind, rlim_t value) {
    struct rlimit r = {value, value}; if (setrlimit(kind, &r)) die();
}
static void map_file(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0 || write(fd, value, strlen(value)) != (ssize_t)strlen(value)) die();
    close(fd);
}
static void ephemeral_namespaces(void) {
    uid_t uid = getuid(); gid_t gid = getgid();
    if (!uid || !gid) return die();
    if (unshare(CLONE_NEWUSER | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS)) die();
    char mapping[80];
    snprintf(mapping, sizeof(mapping), "%u %u 1\n", uid, uid);
    map_file("/proc/self/uid_map", mapping);
    map_file("/proc/self/setgroups", "deny\n");
    snprintf(mapping, sizeof(mapping), "%u %u 1\n", gid, gid);
    map_file("/proc/self/gid_map", mapping);
    for (int capability=0; capability<=CAP_LAST_CAP; capability++)
        if (prctl(PR_CAPBSET_DROP, capability, 0, 0, 0)) die();
    struct __user_cap_header_struct header = {.version=_LINUX_CAPABILITY_VERSION_3, .pid=0};
    struct __user_cap_data_struct caps[2] = {{0},{0}};
    if (syscall(SYS_capset, &header, caps)) die();
    pid_t child = fork();
    if (child < 0) die();
    if (child > 0) {
        int status;
        if (waitpid(child, &status, 0) < 0) die();
        exit(WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status));
    }
    if (getpid() != 1 || getuid() != uid || getgid() != gid) die();
}
static void allow_path(int rules, const char *path, __u64 permissions) {
    int fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) { if (access(path, F_OK)) return; die(); }
    struct landlock_path_beneath_attr attr = {.allowed_access=permissions, .parent_fd=fd};
    if (syscall(__NR_landlock_add_rule, rules, LANDLOCK_RULE_PATH_BENEATH, &attr, 0)) die();
    close(fd);
}
int main(int argc, char **argv) {
    if (argc < 6) return 125;
    int compiling = !strcmp(argv[1], "compile");
    long memory_mb = strtol(argv[3], NULL, 10);
    long cpu_seconds = strtol(argv[4], NULL, 10);
    if (memory_mb < 32 || memory_mb > 2048 || cpu_seconds < 1 || cpu_seconds > 30) return 125;
    if (syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION) < 3) return 125;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) die();
    ephemeral_namespaces();
    __u64 read = LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR | LANDLOCK_ACCESS_FS_EXECUTE;
    __u64 write = LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
        LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SYM |
        LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE;
    struct landlock_ruleset_attr ruleset = {.handled_access_fs=read | write |
        LANDLOCK_ACCESS_FS_MAKE_CHAR | LANDLOCK_ACCESS_FS_MAKE_BLOCK | LANDLOCK_ACCESS_FS_MAKE_SOCK | LANDLOCK_ACCESS_FS_MAKE_FIFO};
    int rules = syscall(__NR_landlock_create_ruleset, &ruleset, sizeof(ruleset), 0);
    if (rules < 0 || prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || prctl(PR_SET_DUMPABLE, 0)) die();
    allow_path(rules, "/usr", read); allow_path(rules, "/lib", read); allow_path(rules, "/lib64", read);
    allow_path(rules, "/etc/ld.so.cache", LANDLOCK_ACCESS_FS_READ_FILE);
    allow_path(rules, "/etc/alternatives", read);
    allow_path(rules, "/etc/java-17-openjdk", read);
    allow_path(rules, "/etc/java-21-openjdk", read);
    allow_path(rules, "/dev/null", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE);
    allow_path(rules, "/dev/urandom", LANDLOCK_ACCESS_FS_READ_FILE);
    allow_path(rules, argv[2], read | write);
    if (syscall(__NR_landlock_restrict_self, rules, 0)) die();
    close(rules);
    limit(RLIMIT_CORE, 0); limit(RLIMIT_NOFILE, 64); limit(RLIMIT_FSIZE, 16*1024*1024);
    limit(RLIMIT_CPU, cpu_seconds); limit(RLIMIT_AS, (rlim_t)memory_mb*1024*1024);
    limit(RLIMIT_NPROC, compiling ? 48 : 32);
    scmp_filter_ctx filter = seccomp_init(SCMP_ACT_ALLOW);
    if (!filter) die();
    const char *blocked[] = {"socket","connect","bind","listen","accept","accept4",
        "ptrace","process_vm_readv","process_vm_writev","mount","umount2","unshare","setns",
        "bpf","keyctl","add_key","request_key","open_by_handle_at","reboot","userfaultfd",
        "perf_event_open","io_uring_setup","kill","tkill","pidfd_open","pidfd_send_signal","setsid","setpgid",NULL};
    for (int i=0; blocked[i]; i++) {
        int syscall_id = seccomp_syscall_resolve_name(blocked[i]);
        if (syscall_id != __NR_SCMP_ERROR && seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), syscall_id, 0)) die();
    }
    /* The JVM uses anonymous AF_UNIX socketpairs internally for file channels.
       They cannot address another process; socket/connect/bind remain denied. */
    /* Deny every domain below or above AF_UNIX. Only AF_UNIX equals the permitted domain. */
    if (seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), SCMP_SYS(socketpair), 1, SCMP_A0(SCMP_CMP_LT, AF_UNIX)) ||
        seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), SCMP_SYS(socketpair), 1, SCMP_A0(SCMP_CMP_GT, AF_UNIX))) die();
    if (seccomp_rule_add(filter, SCMP_ACT_ERRNO(38), SCMP_SYS(clone3), 0)) die();
    /* JVM thread signals may only target this guarded process's own thread group. */
    int thread_signals[] = {SCMP_SYS(tgkill), SCMP_SYS(rt_sigqueueinfo), SCMP_SYS(rt_tgsigqueueinfo)};
    for (unsigned int i=0; i<sizeof(thread_signals)/sizeof(thread_signals[0]); i++) {
        if (seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), thread_signals[i], 1, SCMP_A0(SCMP_CMP_LT, getpid())) ||
            seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), thread_signals[i], 1, SCMP_A0(SCMP_CMP_GT, getpid()))) die();
    }
    if (!compiling) {
        if (seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), SCMP_SYS(fork), 0) ||
            seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), SCMP_SYS(vfork), 0) ||
            seccomp_rule_add(filter, SCMP_ACT_ERRNO(1), SCMP_SYS(clone), 1,
                SCMP_A0(SCMP_CMP_MASKED_EQ, CLONE_THREAD, 0))) die();
    }
    if (seccomp_load(filter)) die();
    seccomp_release(filter);
    execv(argv[5], &argv[5]); die();
}
