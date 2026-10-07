# DBMS Indexes and Query Planning

This project-authored reference describes database indexing for interview evaluation. A B-tree index keeps ordered keys and supports equality, range predicates, and ordered scans. A composite index is most effective when a query constrains its leading columns. An index can reduce reads, but every additional index adds storage and write maintenance.

Query planners compare estimated costs for sequential scans, index scans, and joins. Cardinality statistics guide those estimates. `EXPLAIN` shows the chosen plan; `EXPLAIN ANALYZE` executes the query and reports actual timing and row counts. Large gaps between estimated and actual rows often indicate stale statistics or correlated data.

An index is not automatically useful for a small table, a low-selectivity predicate, or a query that returns much of the table. Evaluation should reward candidates who discuss workload, selectivity, write cost, and measurement rather than claiming that indexes always make queries faster.
