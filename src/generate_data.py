"""Génère un jeu de données FICTIF de membres et de transactions.

Les comportements suspects (typologies LCB-FT) sont injectés volontairement et
étiquetés, ce qui permet de mesurer la performance du dispositif de détection.
Aucune donnée réelle n'est utilisée.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import PAYS_A_RISQUE, SEUIL_VIGILANCE

DEBUT = datetime(2026, 1, 1)
NB_JOURS = 180
PAYS_NORMAUX = ["FR"] * 85 + ["BE", "DE", "ES", "IT", "PT", "LU", "NL", "CH", "GB", "MA", "SN", "BJ", "CI", "TN"]
TYPOLOGIES = [
    "fractionnement", "compte_de_passage", "pays_a_risque",
    "reveil_compte_dormant", "collecte_multi_emetteurs", "incoherence_profil", "montants_ronds",
]


class Generateur:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.tx: list[dict] = []
        self.n_cp = 0

    # ------------------------------------------------------------------ utils
    def date(self, jour_min=0, jour_max=NB_JOURS) -> datetime:
        j = self.rng.uniform(jour_min, jour_max)
        return DEBUT + timedelta(days=float(j))

    def contrepartie(self) -> str:
        self.n_cp += 1
        return f"CP{self.rng.integers(1, 4000):05d}"

    def ajout(self, membre, ts, montant, sens, canal, pays="FR", cp=None, typologie=None):
        self.tx.append({
            "membre_id": membre, "horodatage": ts.replace(microsecond=0), "montant": round(float(montant), 2),
            "sens": sens, "canal": canal, "pays_contrepartie": pays,
            "contrepartie_id": cp or self.contrepartie(), "typologie_injectee": typologie,
        })

    # ------------------------------------------------------ comportements normaux
    def activite_particulier(self, m, revenu, jour_debut=0, jour_fin=NB_JOURS):
        employeur = self.contrepartie()
        bailleur = self.contrepartie()
        loyer = revenu * self.rng.uniform(0.25, 0.4)
        for mois in range(6):
            base = DEBUT + timedelta(days=30 * mois)
            if not (jour_debut <= 30 * mois + 28 <= jour_fin):
                continue
            self.ajout(m, base + timedelta(days=int(self.rng.integers(25, 29))), revenu * self.rng.uniform(0.97, 1.03), "IN", "VIREMENT", "FR", employeur)
            self.ajout(m, base + timedelta(days=int(self.rng.integers(1, 5))), loyer, "OUT", "PRELEVEMENT", "FR", bailleur)
            for _ in range(int(self.rng.integers(15, 40))):  # paiements carte
                self.ajout(m, base + timedelta(days=float(self.rng.uniform(0, 30))), self.rng.lognormal(3.2, 0.9), "OUT", "CARTE",
                           self.rng.choice(PAYS_NORMAUX))
            if self.rng.random() < 0.5:  # virement ponctuel entre proches
                self.ajout(m, base + timedelta(days=float(self.rng.uniform(0, 30))), self.rng.uniform(20, 400),
                           self.rng.choice(["IN", "OUT"]), "SEPA_INSTANT", "FR")

    def activite_pro(self, m, ca_mensuel):
        clients = [self.contrepartie() for _ in range(int(self.rng.integers(5, 25)))]
        fournisseurs = [self.contrepartie() for _ in range(int(self.rng.integers(3, 10)))]
        for mois in range(6):
            base = DEBUT + timedelta(days=30 * mois)
            n_fact = int(self.rng.integers(4, 15))
            for montant in self.rng.dirichlet(np.ones(n_fact)) * ca_mensuel * self.rng.uniform(0.8, 1.2):
                self.ajout(m, base + timedelta(days=float(self.rng.uniform(0, 30))), montant, "IN", "VIREMENT",
                           self.rng.choice(PAYS_NORMAUX), self.rng.choice(clients))
            for montant in self.rng.dirichlet(np.ones(6)) * ca_mensuel * self.rng.uniform(0.6, 0.9):
                self.ajout(m, base + timedelta(days=float(self.rng.uniform(0, 30))), montant, "OUT", "VIREMENT",
                           "FR", self.rng.choice(fournisseurs))
            for _ in range(int(self.rng.integers(5, 20))):
                self.ajout(m, base + timedelta(days=float(self.rng.uniform(0, 30))), self.rng.lognormal(4, 1), "OUT", "CARTE", "FR")

    # ------------------------------------------------------ typologies suspectes
    def fractionnement(self, m):
        j = self.rng.uniform(10, NB_JOURS - 10)
        for _ in range(int(self.rng.integers(3, 6))):
            self.ajout(m, self.date(j, j + 6), self.rng.uniform(0.88, 0.995) * SEUIL_VIGILANCE, "IN", "VIREMENT",
                       "FR", typologie="fractionnement")

    def compte_de_passage(self, m):
        for _ in range(int(self.rng.integers(2, 5))):
            ts = self.date(35, NB_JOURS - 5)
            montant = self.rng.uniform(6_000, 40_000)
            self.ajout(m, ts, montant, "IN", "VIREMENT", "FR", typologie="compte_de_passage")
            reste = montant * self.rng.uniform(0.9, 0.99)
            for part in self.rng.dirichlet(np.ones(int(self.rng.integers(1, 4)))) * reste:
                self.ajout(m, ts + timedelta(hours=float(self.rng.uniform(1, 40))), part, "OUT", "SEPA_INSTANT",
                           self.rng.choice(["FR", "BE", "LT", "ES"]), typologie="compte_de_passage")

    def pays_a_risque(self, m):
        for _ in range(int(self.rng.integers(1, 4))):
            self.ajout(m, self.date(), self.rng.uniform(1_500, 15_000), self.rng.choice(["IN", "OUT"]), "VIREMENT",
                       self.rng.choice(PAYS_A_RISQUE), typologie="pays_a_risque")

    def collecte_multi_emetteurs(self, m):
        j = self.rng.uniform(0, NB_JOURS - 30)
        for _ in range(int(self.rng.integers(18, 40))):
            self.ajout(m, self.date(j, j + 25), self.rng.uniform(150, 1_500), "IN", "SEPA_INSTANT", "FR",
                       typologie="collecte_multi_emetteurs")

    def incoherence_profil(self, m, revenu):
        for _ in range(int(self.rng.integers(3, 7))):
            self.ajout(m, self.date(), revenu * self.rng.uniform(1.5, 4), "IN", "VIREMENT",
                       self.rng.choice(PAYS_NORMAUX), typologie="incoherence_profil")

    def montants_ronds(self, m):
        j = self.rng.uniform(0, NB_JOURS - 30)
        for _ in range(int(self.rng.integers(5, 10))):
            self.ajout(m, self.date(j, j + 28), float(self.rng.integers(2, 9)) * 1_000, self.rng.choice(["IN", "OUT"]),
                       "VIREMENT", "FR", typologie="montants_ronds")

    # ------------------------------------------------------------------ run
    def run(self, n_membres=1000, taux_suspects=0.06):
        membres = []
        n_susp = int(n_membres * taux_suspects)
        suspects = set(self.rng.choice(n_membres, n_susp, replace=False).tolist())
        for i in range(n_membres):
            m = f"M{i:05d}"
            pro = self.rng.random() < 0.2
            revenu = float(self.rng.lognormal(10, 0.6) if pro else self.rng.lognormal(7.9, 0.35))
            typo = None
            if i in suspects:
                typo = TYPOLOGIES[len([s for s in suspects if s < i]) % len(TYPOLOGIES)]
            if typo == "reveil_compte_dormant":
                pro = False
                # activité normale au début, silence, puis gros volumes
                self.activite_particulier(m, revenu, 0, 40)
                j = self.rng.uniform(140, 160)
                for _ in range(int(self.rng.integers(4, 8))):
                    self.ajout(m, self.date(j, j + 15), self.rng.uniform(3_000, 12_000), self.rng.choice(["IN", "OUT"]),
                               "VIREMENT", "FR", typologie="reveil_compte_dormant")
            elif pro:
                self.activite_pro(m, revenu)
            else:
                self.activite_particulier(m, revenu)

            if typo and typo != "reveil_compte_dormant":
                if typo == "incoherence_profil":
                    self.incoherence_profil(m, revenu)
                else:
                    getattr(self, typo)(m)

            # Faux positifs réalistes : comportements atypiques mais légitimes
            if typo is None and self.rng.random() < 0.02:  # héritage / vente immobilière
                self.ajout(m, self.date(), self.rng.uniform(30_000, 150_000), "IN", "VIREMENT", "FR")
            if typo is None and self.rng.random() < 0.03:  # envoi d'argent à la famille à l'étranger
                for _ in range(6):
                    self.ajout(m, self.date(), self.rng.uniform(100, 600), "OUT", "VIREMENT",
                               self.rng.choice(["MA", "SN", "BJ", "CI"]))

            membres.append({
                "membre_id": m, "type_membre": "PRO" if pro else "PARTICULIER",
                "revenu_mensuel_declare": round(revenu, 0),
                "niveau_risque_kyc": self.rng.choice(["FAIBLE", "MOYEN", "ELEVE"], p=[0.7, 0.25, 0.05]),
                "date_entree_relation": (DEBUT - timedelta(days=int(self.rng.integers(30, 900)))).date().isoformat(),
                "suspect_injecte": typo is not None, "typologie_injectee": typo,
            })
        tx = pd.DataFrame(self.tx).sort_values(["membre_id", "horodatage"]).reset_index(drop=True)
        tx.insert(0, "tx_id", [f"T{i:07d}" for i in range(len(tx))])
        return pd.DataFrame(membres), tx


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--membres", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--sortie", default=str(Path(__file__).resolve().parents[1] / "data"))
    a = p.parse_args()
    membres, tx = Generateur(a.seed).run(a.membres)
    out = Path(a.sortie); out.mkdir(exist_ok=True, parents=True)
    membres.to_csv(out / "membres.csv", index=False)
    tx.to_csv(out / "transactions.csv", index=False)
    print(f"{len(membres)} membres, {len(tx)} transactions, {membres.suspect_injecte.sum()} suspects injectés -> {out}")


if __name__ == "__main__":
    main()
