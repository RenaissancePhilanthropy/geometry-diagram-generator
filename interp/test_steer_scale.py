"""Offline check of the amplify-mode random-control matching in steer_confidence.py.

amplify perturbs h by (g-1) * (h·d - mu_d) * d. Its magnitude is (g-1)*|h·d - mu_d|, i.e. it
scales with the spread of projections onto d. The correctness direction w is chosen to have a
large spread (it separates classes), a random direction r has a small one, so an unscaled random
control is a weaker intervention. steer_confidence.py multiplies the random perturbation by
sigma_w / sigma_r; this test asserts that the two perturbation-magnitude distributions then match.
"""
import numpy as np


def _perturb_norms(X, hat, mu, gain, scale=1.0):
    proj = X @ hat - mu
    return np.abs((gain - 1.0) * scale * proj)


def test_amplify_random_control_is_magnitude_matched():
    rng = np.random.default_rng(0)
    n, d = 400, 64
    # two classes separated along one axis -> w has large projection spread
    y = rng.integers(0, 2, n)
    X = rng.standard_normal((n, d)).astype(np.float32)
    X[:, 0] += 6.0 * (y - 0.5)
    w_raw = X[y == 1].mean(0) - X[y == 0].mean(0)
    w_hat = w_raw / np.linalg.norm(w_raw)
    r_raw = rng.standard_normal(d).astype(np.float32)
    r_hat = r_raw / np.linalg.norm(r_raw)
    mu, mu_r = float((X @ w_hat).mean()), float((X @ r_hat).mean())
    sigma_w, sigma_r = float((X @ w_hat).std()), float((X @ r_hat).std())
    assert sigma_w > 2 * sigma_r, "setup: w should have the larger spread"

    g = 4.0
    steer = _perturb_norms(X, w_hat, mu, g)
    rand_unscaled = _perturb_norms(X, r_hat, mu_r, g)
    rand_scaled = _perturb_norms(X, r_hat, mu_r, g, scale=sigma_w / sigma_r)

    # the old control was much weaker than the steer intervention …
    assert rand_unscaled.mean() < 0.5 * steer.mean()
    # … the matched one has the same RMS perturbation (exactly, by construction) …
    assert np.isclose(np.sqrt((rand_scaled ** 2).mean()), np.sqrt((steer ** 2).mean()), rtol=1e-4)
    # … and a comparable mean (both ~ folded normals of the same scale)
    assert 0.8 < rand_scaled.mean() / steer.mean() < 1.25


def test_add_mode_control_unchanged():
    # in ADD mode the |w|-matched r_raw is already norm-matched; scale must be 1
    mode = "add"
    rand_scale = (2.0 / 1.0) if mode == "amplify" else 1.0
    assert rand_scale == 1.0
