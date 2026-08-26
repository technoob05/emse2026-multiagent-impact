# External actionability transfer gate

The external package supplies LLM-derived labels for 5,652 review
comments from 5 sources.  A word n-gram classifier was
trained four sources at a time and tested on the fifth source.

The gate **failed**.  The weakest held-out ROC AUC
was 0.599 for `aidar-freeed/ai-codereviewer`; the
weakest balanced accuracy at the fixed 0.5 threshold was
0.518 for
`Human`.  Because every source must clear both
thresholds, the model was not applied to AIDev.

This is a construct-transfer falsification, not evidence about review quality,
semantic resolution, or causal impact.  No raw comment text is exported.
