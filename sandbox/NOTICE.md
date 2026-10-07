# Runtime security profile provenance

`docker-seccomp.json` vendors the Docker/Moby default profile from
https://github.com/moby/profiles/blob/main/seccomp/default.json (retrieved 2026-10-01).
The upstream Apache 2.0 license is retained in `MOBY_LICENSE`.

IntervAI modification: one additional `SCMP_ACT_ALLOW` rule for `unshare` with
argument 0 exactly `CLONE_NEWUSER | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS`.
The default action and all upstream rules remain intact. The trusted guard uses
this to create fresh rootless execution namespaces; before executing candidate
code its additional seccomp filter denies unshare, setns, and mount operations.
No SYS_ADMIN capability or seccomp-unconfined setting is used.

Review this narrow modification when updating the vendored profile. Do not
replace it with unrestricted namespace or Docker-daemon access.
