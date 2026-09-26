"""Mesure la performance du dispositif grâce aux typologies injectées."""
from __future__ import annotations

import pandas as pd


def evaluer(alertes: pd.DataFrame, membres: pd.DataFrame) -> dict:
    d = alertes.merge(membres[["membre_id", "suspect_injecte", "typologie_injectee"]], on="membre_id")
    vp = int((d.alerte & d.suspect_injecte).sum())
    fp = int((d.alerte & ~d.suspect_injecte).sum())
    fn = int((~d.alerte & d.suspect_injecte).sum())
    par_typo = (d[d.suspect_injecte].groupby("typologie_injectee")["alerte"]
                  .agg(detectes="sum", total="count").assign(taux_detection=lambda x: (x.detectes / x.total).round(2)))
    return {
        "nb_alertes": int(d.alerte.sum()), "vrais_positifs": vp, "faux_positifs": fp, "faux_negatifs": fn,
        "precision": round(vp / max(vp + fp, 1), 3), "rappel": round(vp / max(vp + fn, 1), 3),
        "par_typologie": par_typo.reset_index(),
    }
