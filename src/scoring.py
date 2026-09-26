"""Combine les règles (connaissance métier) et le score d'anomalie (ML) en un
score de risque 0-100, avec des motifs lisibles pour l'analyste."""
from __future__ import annotations

import pandas as pd

from config import (LIBELLES_REGLES, POIDS_ML_MAX, POIDS_REGLES,
                    SEUIL_ALERTE, SEUIL_PRIORITE_HAUTE)


def construire_alertes(membres: pd.DataFrame, regles: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    base = membres.set_index("membre_id")[["type_membre", "revenu_mensuel_declare", "niveau_risque_kyc"]].copy()
    if len(regles):
        r = regles.assign(poids=regles.regle.map(POIDS_REGLES))
        # Incohérence de profil répétée sur plusieurs mois : poids renforcé
        r.loc[(r.regle == "R6_INCOHERENCE_PROFIL") & (r.nb_occurrences >= 2), "poids"] += 15
        pts = r.groupby("membre_id")["poids"].sum().clip(upper=100 - POIDS_ML_MAX)
        motifs = (r.assign(txt=r.regle.map(LIBELLES_REGLES) + " (" + r.detail + ")")
                    .groupby("membre_id")["txt"].apply(" | ".join))
        codes = r.groupby("membre_id")["regle"].apply(lambda s: ", ".join(sorted(s)))
    else:
        pts = motifs = codes = pd.Series(dtype=object)
    base["points_regles"] = pts.reindex(base.index).fillna(0)
    base["regles_declenchees"] = codes.reindex(base.index).fillna("")
    base["motifs"] = motifs.reindex(base.index).fillna("")
    base = base.join(anomalies)
    # Le ML n'apporte des points qu'au-delà du comportement « normal » (score > 0.4)
    base["points_ml"] = ((base["score_anomalie"] - 0.4).clip(lower=0) / 0.6 * POIDS_ML_MAX).round(1)
    # Majoration si le profil KYC est déjà classé à risque élevé
    base["majoration_kyc"] = (base["niveau_risque_kyc"] == "ELEVE") * 5
    base["score_risque"] = (base.points_regles + base.points_ml + base.majoration_kyc).clip(upper=100).round(0)
    base["alerte"] = base.score_risque >= SEUIL_ALERTE
    base["priorite"] = pd.cut(base.score_risque, [-1, SEUIL_ALERTE - 0.1, SEUIL_PRIORITE_HAUTE - 0.1, 101],
                              labels=["AUCUNE", "MOYENNE", "HAUTE"])
    return base.reset_index().sort_values("score_risque", ascending=False)
