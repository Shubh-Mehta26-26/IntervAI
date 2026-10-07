# Operating Systems: Processes, Threads, and Deadlocks

This project-authored reference distinguishes processes and threads. A process has its own virtual address space and protected resources. Threads within a process share that address space and resources while retaining their own stack and execution state. Threads can make communication cheaper, but shared mutable state requires synchronization.

A race condition occurs when correctness depends on an uncontrolled ordering of concurrent operations. Mutexes, semaphores, immutable messages, and ownership models are common controls. Locking must protect the invariant, not merely an individual line of code.

Deadlock requires mutual exclusion, hold-and-wait, no preemption, and circular wait. Systems prevent or avoid deadlocks by breaking at least one condition, such as imposing a global lock order. Detection and recovery are alternatives. Starvation differs from deadlock: work may continue globally while one participant is repeatedly denied progress.
