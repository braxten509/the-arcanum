# HollowCrawl Phase 8 false-pass case

This learner project is the exact reconstructed artifact retained by the strict validator on
2026-07-14, before HollowCrawl was reopened at Phase 8. The original Phase 8 reviewer returned an
empty findings list even though the ordinary entrypoint crashed and the acceptance mode printed a
constant-success receipt.

The later manual HollowCrawl theme redesign is deliberately absent from this fixture and must not
be counted as a model or harness failure. This case measures only ordinary cold-start behavior and
acceptance-proof integrity.
