"""Pipeline complet : données -> règles SQL -> ML -> score -> alertes -> évaluation."""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from evaluate import evaluer
from ml import calculer_indicateurs, scorer_anomalies
from rules import charger_base, executer_regles
from scoring import construire_alertes

RACINE = Path(__file__).resolve().parents[1]


def executer(dossier_data: Path = RACINE / "data", dossier_sortie: Path = RACINE / "output"):
    t0 = time.time()
    membres = pd.read_csv(dossier_data / "membres.csv")
    tx = pd.read_csv(dossier_data / "transactions.csv")
    regles = executer_regles(charger_base(membres, tx))
    indicateurs = calculer_indicateurs(membres, tx)
    anomalies = scorer_anomalies(indicateurs)
    alertes = construire_alertes(membres, regles, anomalies)
    dossier_sortie.mkdir(exist_ok=True)
    alertes.to_csv(dossier_sortie / "alertes.csv", index=False)
    regles.to_csv(dossier_sortie / "declenchements_regles.csv", index=False)
    indicateurs.to_csv(dossier_sortie / "indicateurs_membres.csv")
    res = evaluer(alertes, membres)
    print(f"Pipeline exécuté en {time.time() - t0:.1f} s sur {len(tx):,} transactions / {len(membres)} membres")
    print(f"Alertes : {res['nb_alertes']} | précision : {res['precision']:.0%} | rappel : {res['rappel']:.0%}")
    print(res["par_typologie"].to_string(index=False))
    return alertes, res


if __name__ == "__main__":
    executer()
