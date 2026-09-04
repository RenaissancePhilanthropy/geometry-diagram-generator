# Session logs — vast.ai box 50423dca401c, 2026-09-02/03

Console logs from the 2x RTX 5090 box that produced the four fresh Mistral-Small-24B
cells (`fix_mistral_math`, `fix_mistral_mmlu_pro`, `fix_mistral_gpqa`,
`fix_mistral_temporal`), the steering replication with the magnitude-matched random
control, and the 4x4 transfer matrix. `save_off_box.sh` copies results but not these,
so they were pulled off by hand before the box was destroyed.

| file | what it covers |
|---|---|
| `setup.log` | box provisioning: venv, torch 2.11+cu128, repo clone, HF cache |
| `download.log` | model + dataset downloads |
| `overnight.log` | the unattended run (`overnight_mistral.sh`), 03:23–08:48 box-time |
| `morning.log` | GPQA capture + geometry temporal capture (`morning.sh`) |
| `tier1_partial.log`, `tier1_3dom.log`, `tier1_4dom.log` | `tier1_review.py` as domains were added (2, 3, then 4 cells) |
| `save.log`, `save_final.log` | `save_off_box.sh` runs; the final one is the 20:00 sync that cleared the box for destroy |
| `sso_login.log` | AWS SSO device login for the Tier B upload (device code redacted) |
| `ports.log` | forwarded ports |

Known issue visible in `save_final.log`: the Tier A `git push` failed on the box
("Permission denied (publickey)" — that shell had no `ssh -A` agent forwarding) and
`save_off_box.sh` still reported "SAVE COMPLETE. Safe to destroy the box." and exited 0.
The commit reached origin another way, so nothing was lost, but the script does not
currently fail on a failed Tier A push.
