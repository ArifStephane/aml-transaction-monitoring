"""Détection d'anomalies non supervisée (Isolation Forest) sur des indicateurs
comportementaux calculés par membre. Complète les règles : elle repère des
comportements atypiques qu'aucune règle n'a prévus."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from config import PAYS_A_RISQUE

LIBELLES_FEATURES = {
    "ratio_entrees_revenu": "entrées mensuelles / revenus déclarés",
    "montant_max": "montant maximal d'une opération",
    "part_entrees_ressorties_48h": "part des entrées ressorties sous 48 h",
    "nb_contreparties_entrantes": "nombre d'émetteurs distincts",
    "part_international": "part des flux hors France",
    "part_montants_ronds": "part des montants ronds",
    "jours_inactivite_max": "plus longue période d'inactivité",
    "volume_total": "volume total des flux",
    "nb_operations": "nombre d'opérations",
}


def calculer_indicateurs(membres: pd.DataFrame, tx: pd.DataFrame) -> pd.DataFrame:
    t = tx.copy()
    t["horodatage"] = pd.to_datetime(t["horodatage"])
    t["mois"] = t["horodatage"].dt.to_period("M")
    entrees = t[t.sens == "IN"]
    sorties = t[t.sens == "OUT"]

    g = t.groupby("membre_id")
    f = pd.DataFrame({
        "volume_total": g["montant"].sum(),
        "nb_operations": g.size(),
        "montant_max": g["montant"].max(),
        "part_international": g["pays_contrepartie"].apply(lambda s: (s != "FR").mean()),
        "part_montants_ronds": g["montant"].apply(lambda s: ((s >= 1000) & (s % 1000 == 0)).mean()),
        "jours_inactivite_max": g["horodatage"].apply(lambda s: s.sort_values().diff().dt.days.max()).fillna(0),
    })
    f["nb_contreparties_entrantes"] = entrees.groupby("membre_id")["contrepartie_id"].nunique()
    ent_mois = entrees.groupby(["membre_id", "mois"])["montant"].sum().groupby("membre_id").max()
    f["ratio_entrees_revenu"] = ent_mois / membres.set_index("membre_id")["revenu_mensuel_declare"]
    f["a_pays_risque"] = t[t.pays_contrepartie.isin(PAYS_A_RISQUE)].groupby("membre_id").size()

    # Part des gros montants entrants ressortis sous 48 h (approximation par merge_asof)
    e = entrees[entrees.montant >= 3000][["membre_id", "horodatage", "montant"]].sort_values("horodatage")
    s = sorties[sorties.canal != "CARTE"][["membre_id", "horodatage", "montant"]].sort_values("horodatage")
    if len(e) and len(s):
        s = s.assign(cum=s.groupby("membre_id")["montant"].cumsum())
        debut = pd.merge_asof(e, s[["membre_id", "horodatage", "cum"]], on="horodatage", by="membre_id", direction="backward")
        e2 = e.assign(horodatage=e.horodatage + pd.Timedelta(hours=48))
        fin = pd.merge_asof(e2, s[["membre_id", "horodatage", "cum"]], on="horodatage", by="membre_id", direction="backward")
        sorti = fin["cum"].fillna(0).values - debut["cum"].fillna(0).values
        e = e.assign(ressorti=(sorti >= 0.8 * e["montant"].values))
        f["part_entrees_ressorties_48h"] = e.groupby("membre_id")["ressorti"].mean()
    f = f.reindex(membres["membre_id"]).fillna(0)
    return f


def scorer_anomalies(indicateurs: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Renvoie un score d'anomalie 0-1 et les 2 indicateurs les plus atypiques."""
    cols = list(LIBELLES_FEATURES)
    X = indicateurs[cols].copy()
    for c in ["volume_total", "montant_max", "nb_operations", "ratio_entrees_revenu", "nb_contreparties_entrantes"]:
        X[c] = np.log1p(X[c])
    Xs = RobustScaler().fit_transform(X)
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=seed).fit(Xs)
    brut = -iso.score_samples(Xs)
    score = (brut - brut.min()) / (brut.max() - brut.min())
    # Explicabilité simple : écart robuste le plus élevé par indicateur
    ecarts = np.abs(Xs)
    top = np.argsort(-ecarts, axis=1)[:, :2]
    raisons = [", ".join(LIBELLES_FEATURES[cols[j]] for j in row) for row in top]
    return pd.DataFrame({"score_anomalie": score, "indicateurs_atypiques": raisons}, index=indicateurs.index)
