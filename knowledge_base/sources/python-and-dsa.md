# Python Generators, Decorators, Binary Search, and Hash Tables

This project-authored reference covers selected Python and data-structure concepts. A generator produces values lazily and suspends its frame at `yield`. Lazy iteration can reduce peak memory and can represent streams, although a generator is normally single-pass. Exceptions and cleanup still need explicit handling, often with `try` and `finally`.

A decorator receives a callable and returns a callable, commonly using a closure. `functools.wraps` preserves useful metadata. Decorators are suitable for cross-cutting behavior such as tracing or authorization only when the wrapper preserves the original contract and does not hide important control flow.

Binary search requires a monotonic search condition and shrinks the candidate interval by half, giving logarithmic comparisons. Boundary choices must be consistent to avoid infinite loops and off-by-one errors. A hash table offers expected constant-time lookup under a suitable hash distribution, but collisions must be resolved and worst-case behavior can degrade. Resizing trades occasional expensive operations for good amortized performance.
