# DBMS Transactions and Normalization

This project-authored reference covers transaction guarantees and schema normalization. Atomicity makes a transaction all-or-nothing. Consistency means committed changes preserve declared invariants. Isolation controls how concurrent transactions observe one another. Durability means committed data survives the failures covered by the storage design.

Isolation levels trade concurrency for anomaly prevention. Applications should use short transactions, deterministic lock order where practical, and retry logic for serialization failures or deadlocks. A transaction does not make an unsafe multi-step workflow correct unless all related state changes share the boundary.

Normalization separates facts to reduce update, insertion, and deletion anomalies. Third normal form generally requires non-key attributes to depend on the key, the whole key, and no non-key attribute. Deliberate denormalization can improve measured read paths, but it introduces consistency work that must be explicit.
