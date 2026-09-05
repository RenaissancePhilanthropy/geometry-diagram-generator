import json, sys
d = json.load(open(sys.argv[1]))
print("model:", d["model"], "| layer:", d["layer_acts"], "| n_eval:", d["n_eval"])
print("direction_from:", d.get("direction_from"))
rc = d.get("random_control", {})
print("random_control:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rc.items()})
print()
hdr = ("condition", "parse", "conf FAIL", "conf OK", "stated AUROC", "ECE", "logit hi-lo")
print(f"{hdr[0]:18} {hdr[1]:>6} {hdr[2]:>10} {hdr[3]:>8} {hdr[4]:>13} {hdr[5]:>7} {hdr[6]:>12}")
def fmt(x, s="{:.1f}"):
    return s.format(x) if isinstance(x, (int, float)) and x == x else "-"
for k, v in d["results"].items():
    print(f"{k:18} {v['parse_rate']:>6.2f} {fmt(v.get('mean_conf_fail')):>10} "
          f"{fmt(v.get('mean_conf_ok')):>8} {fmt(v.get('auroc'), '{:.3f}'):>13} "
          f"{fmt(v.get('ece'), '{:.3f}'):>7} {v['logit_diff']:>12.3f}")
print()
print("row keys:", list(list(d["results"].values())[0].keys()))
