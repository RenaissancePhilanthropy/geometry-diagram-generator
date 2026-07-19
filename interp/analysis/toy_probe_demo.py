"""
THE WHOLE EXPERIMENT, shrunk to 2D toy numbers you can trace by hand.
Run:  interp/.venv/bin/python interp/analysis/toy_probe_demo.py

We pretend the model's internal vectors are just 2 numbers (instead of 3584),
and we have 6 point-tokens. We ask the one question the real project asks:
"Is the fact 'this point is a MIDPOINT' written into the vector — readably?"
We show it's NOT readable at an early layer, and IS readable at a late layer.
"""
import numpy as np

# ----------------------------------------------------------------------
# SUB-STEP 1.  Twenty "point tokens." In the real run each is a 3584-number
# vector captured from the model; here each is just 2 numbers so we can see it.
# Half are truly midpoints (label 1), half are not (label 0). The label comes
# from the GEOMETRY (the answer key), NOT from the token's letter.
# (We use 20, not 6, so the held-out test set is big enough to not get lucky --
#  that "too few test points fools you" trap is exactly what bit our real run.)
rng = np.random.default_rng(0)
labels = np.array([1]*10 + [0]*10)

# SUB-STEP 2.  "EARLY LAYER" activations: pure noise. The midpoint fact has NOT
# been computed yet, so the vectors carry no signal about it -> not separable.
early = rng.normal(size=(20, 2)).round(2)

# SUB-STEP 3.  "LATE LAYER" activations: now the model HAS computed midpoint-ness
# and written it along a direction -> midpoints cluster one way, non-midpoints
# the other (with noise). This is what "the fact is encoded" looks like.
late = (rng.normal(size=(20, 2)) + np.where(labels[:, None] == 1, +2.0, -2.0)).round(2)

def show(title, X, k=6):
    print(f"\n{title}  (first {k} of 20)")
    print("  vector        midpoint?")
    for v, y in list(zip(X, labels))[:k]:
        print(f"   [{v[0]:+5.2f},{v[1]:+5.2f}]     {'YES' if y else 'no'}")

show("EARLY-LAYER vectors (no signal yet):", early)
show("LATE-LAYER vectors (midpoint-ness baked in):", late)

# ----------------------------------------------------------------------
# SUB-STEP 4.  THE PROBE.  A linear probe is literally: pick a direction w,
# score each vector by the dot product (w . vector), and threshold.
# Training = find the w that best separates midpoints from non-midpoints.
# We train on 4 points and TEST on 2 held-out points (so success = it
# generalizes, not memorizes).
from sklearn.linear_model import LogisticRegression

# train on 14 points, TEST on 6 held-out points (success = generalizes).
train_idx = list(range(0,7)) + list(range(10,17))    # 7 midpoints + 7 not
test_idx  = [7,8,9,17,18,19]                          # 3 midpoints + 3 not held out

def probe(X, title):
    clf = LogisticRegression().fit(X[train_idx], labels[train_idx])
    w = clf.coef_[0]
    acc = clf.score(X[test_idx], labels[test_idx])
    print(f"\n{title}")
    print(f"  learned direction w = [{w[0]:+.2f}, {w[1]:+.2f}]   (the probe's 'readout')")
    print(f"  held-out accuracy on 6 unseen points = {acc:.0%}  ->  "
          f"{'DECODABLE: the fact is in the vector' if acc>=0.8 else 'NOT decodable: ~coin-flip, the fact is not there'}")

probe(early, "PROBE on EARLY layer:")
probe(late,  "PROBE on LATE layer:")

# ----------------------------------------------------------------------
print("""
----------------------------------------------------------------------
WHAT JUST HAPPENED (map back to the real project):

  toy 2-number vector      ->  the model's real 3584-number residual vector
  'is this a midpoint?'     ->  any geometry fact (role / coords / angle)
  label from `labels`       ->  label from SymPy ground truth (the answer key)
  EARLY layer (noise)       ->  a layer where the model hasn't computed it yet
  LATE layer (signal)       ->  a layer where the model HAS computed it
  the direction w           ->  what `probe.py` learns (after PCA + scaling)
  held-out P and C          ->  held-out PROMPTS (this is the leakage fix:
                                 test on points the probe never trained on)
  EARLY fails, LATE works   ->  'decodability rises with depth' = the model
                                 BUILDS the fact across layers (didn't copy it)

That's the entire experiment. Everything else (29 real layers, PCA, the
naming baseline, patching) is a refinement of these five sub-steps.
""")
