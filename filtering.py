import pandas as pd


def weighted_present(values):
    num = 0.0
    den = 0.0
    for value, weight in values:
        if value is None or pd.isna(value):
            continue
        num += float(value) * float(weight)
        den += float(weight)
    return (num / den) if den > 0 else None


def select_high_interaction_molecules(df, cutoff, top_n=8):
    if df.empty or "interaction_count" not in df.columns:
        return df.head(0).copy()
    subset = df[df["interaction_count"].map(lambda x: x is not None and not pd.isna(x) and float(x) >= cutoff)].copy()
    if subset.empty:
        return subset
    sort_cols = ["interaction_count", "overall_score", "priority_score", "score"]
    present_cols = [col for col in sort_cols if col in subset.columns]
    ascending = [False, False, False, True][: len(present_cols)]
    return subset.sort_values(present_cols, ascending=ascending).head(top_n)


def bounded_score(value, low, high):
    if value is None or pd.isna(value):
        return None
    if low <= value <= high:
        return 1.0
    if value < low:
        span = max(abs(low), 1.0)
        return max(0.0, 1.0 - ((low - value) / span))
    span = max(abs(high), 1.0)
    return max(0.0, 1.0 - ((value - high) / span))


def druglike_score_from_row(row):
    parts = [
        (bounded_score(row.get("mol_wt"), 250.0, 550.0), 0.18),
        (bounded_score(row.get("clogp"), 1.0, 4.8), 0.12),
        (bounded_score(row.get("tpsa"), 20.0, 110.0), 0.18),
        (bounded_score(row.get("rot_bonds"), 0.0, 8.0), 0.24),
        (bounded_score(row.get("hbd"), 0.0, 3.0), 0.10),
        (bounded_score(row.get("hba"), 1.0, 10.0), 0.10),
        (bounded_score(row.get("rings"), 2.0, 5.0), 0.08),
    ]
    return weighted_present(parts)


def apply_report_filters(df, max_hbd=None, max_rot_bonds=None, neutral_only=None):
    out = df.copy()
    if max_hbd is not None:
        out["passes_hbd_filter"] = out["hbd"].map(lambda x: (x is not None) and (not pd.isna(x)) and (x <= max_hbd))
    else:
        out["passes_hbd_filter"] = True
    if max_rot_bonds is not None:
        out["passes_rotb_filter"] = out["rot_bonds"].map(lambda x: (x is not None) and (not pd.isna(x)) and (x <= max_rot_bonds))
    else:
        out["passes_rotb_filter"] = True
    if neutral_only:
        if "is_neutral_ph7" in out.columns:
            out["passes_neutral_filter"] = out["is_neutral_ph7"].map(lambda x: x is True)
        else:
            out["passes_neutral_filter"] = out["formal_charge"].map(
                lambda x: (x is not None) and (not pd.isna(x)) and abs(float(x)) < 1e-9
            )
    else:
        out["passes_neutral_filter"] = True

    out["report_eligible"] = out["passes_hbd_filter"] & out["passes_rotb_filter"] & out["passes_neutral_filter"]
    reasons = []
    for _, row in out.iterrows():
        tags = []
        if not row["passes_hbd_filter"]:
            tags.append("hbd")
        if not row["passes_rotb_filter"]:
            tags.append("rot_bonds")
        if not row["passes_neutral_filter"]:
            tags.append("charged")
        reasons.append(";".join(tags))
    out["report_exclusion_reason"] = reasons
    return out