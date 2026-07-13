# Codebase

This folder contains detailed source layout, dependency, port, and naming rules.

* [Source Layout](source-layout.md) - Defines OMYM2's feature-oriented source layout, including Bootstrap and durable Operation placement, dependency layers, composition, and directory rules.
* [Dependency Boundaries](dependency-boundaries.md) - Defines OMYM2's dependency direction between adapters, features, domain, and shared layers, the forbidden dependencies, and where business rules must live.
* [Ports And UnitOfWork](ports-uow.md) - Defines OMYM2's ports and UnitOfWork contract, including durable Operations, Config revision CAS, atomic Apply claims, filesystem mutation preconditions, and FileEvent transaction ordering.
* [Source Naming](naming.md) - Authoritative Python naming conventions for OMYM2 modules, classes, functions, and constants, including banned vague names and per-layer naming rules for domain, features, and adapters.
* [Web Frontend](web-frontend.md) - Defines the clean-room desktop React and Vite Web frontend contract, including routes, design rules, API boundaries, layout behavior, production serving, packaging, security, and performance gates.
