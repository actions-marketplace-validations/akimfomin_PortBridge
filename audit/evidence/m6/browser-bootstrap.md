# Browser startup before release

The local Pages export initially requested `/api/v1/health` on every cold visit. Static hosting returned 404, then the application fell back to the published manifest. Chromium also requested an absent `/favicon.ico`. The export now identifies itself in its HTML and embeds the existing bridge mark as its icon. The local API server still serves its original, unmarked entry page.

| Chromium check | Observation |
| --- | --- |
| Static export, English and Russian | Read `data/site.json`, rendered Lab, zero requests to the local API or root favicon |
| Actual local PortBridge HTTP server | Read `/api/v1/health` and `/api/v1/lab`, rendered Lab, zero manifest requests |
| Older unmarked static index | The unavailable dynamic endpoint was followed by the published manifest, Lab rendered |
| Marked export missing its manifest in an isolated test | Russian error and Retry were shown. No request to the local API |

Headless Chrome 158.0.8127.37 visited Home, Start (EN and RU), the ordinary PR search form, the XCL #2322 search, Lab, Research Radar, People and Impact at 1440 × 900 and 390 × 844 CSS pixels. There were no page-width overflows, failed application requests, uncaught JavaScript exceptions or console errors in the corrected local export. Searching for the ordinary XCL PR URL in both layouts exposed the `PB-0025` card and the pinned LLVM source. [XCL #2322](https://github.com/xcl-dev/xcl/pull/2322) · [LLVM StackColoring.cpp, line 8](https://github.com/llvm/llvm-project/blob/87f0227cb60147a26a1eeb4fb06e3b505e9c7261/llvm/lib/CodeGen/StackColoring.cpp#L8).

Run the browser network regression with `python -B -m unittest discover -s tests -p test_discovery_presentation.py` on a machine with Chrome or Chromium. This rehearsal covers the local export and local API. Production checks use the published Pages generation. [Network regression](../../../tests/test_discovery_presentation.py)
