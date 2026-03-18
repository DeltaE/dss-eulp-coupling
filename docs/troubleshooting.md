# 6. Troubleshooting

## 6.1 OpenDSS Convergence / Connection Issues
- **Symptom:** Circuit fails to solve or crashes.
- **Action:** Add circuit to a `SKIP_CIRCUITS` list in instantiation scripts and re-run matching/instantiation for remaining feeders.

## 6.2 Long Runtime for kVAr/kW Ratios
- **Expected:** ~579 minutes for a full-state dataset.
- **Mitigation:** Reduce circuit set, parallelize where possible, or precompute/store ratios per feeder cohort.

## 6.3 Large Scenario Memory Footprint
- **Symptom:** Python crashes during aggregation.
- **Action:** Process in batches; use chunked CSV reads; convert intermediates to parquet.

## 6.4 Read the Docs Build Failures
- Missing `.readthedocs.yaml` or wrong path to `docs/conf.py`.
- Mixed Markdown/RST without MyST enabled (ensure `myst_parser` is in extensions).
- Autodoc importing Windows-only/OpenDSS deps. **Fix:** use `autodoc_mock_imports` (already configured).

```{admonition} Tip
:class: tip
When in doubt, open the RTD build logs from the project dashboard. They usually point to the exact failure line.
```
