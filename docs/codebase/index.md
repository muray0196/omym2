# Codebase

This folder contains detailed source layout, dependency, port, and naming rules.

* [Source Layout](source-layout.md) - Defines OMYM2's feature-oriented source layout, including artist naming, Bootstrap, durable Operation, desktop-shell placement, dependency layers, composition, and directory rules.
* [Dependency Boundaries](dependency-boundaries.md) - Defines OMYM2's dependency direction between CLI, Web, desktop and outbound adapters, features, domain, and shared layers, the forbidden dependencies, and where business rules must live.
* [Ports And UnitOfWork](ports-uow.md) - Defines OMYM2's ports and UnitOfWork contract, including configured artist-name resolution, cache and cadence transactions, durable Operations, Config revision CAS, atomic Apply claims, cross-platform retained-object mutation preconditions, and FileEvent ordering.
* [Source Naming](naming.md) - Authoritative Python naming conventions for OMYM2 modules, classes, functions, and constants, including banned vague names and per-layer naming rules for domain, features, and adapters.
* [Web Frontend](web-frontend.md) - Defines the bundled desktop React and Vite Web frontend contract, including routes, artist-name settings and Plan diagnostics, design rules, API boundaries, browser and native-window serving, packaging, security, and performance gates.
