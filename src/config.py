"""Paramètres du dispositif de surveillance (à ajuster selon l'appétence au risque)."""

# Seuil interne de vigilance utilisé pour détecter le fractionnement (en euros)
SEUIL_VIGILANCE = 10_000

# Pays à risque (exemple). À mettre à jour selon la liste GAFI et la liste de
# l'UE des pays tiers à haut risque en vigueur, et la politique interne.
PAYS_A_RISQUE = ["IR", "KP", "MM"]

# Poids de chaque règle dans le score de risque (total plafonné à 70, + 30 pour le ML)
POIDS_REGLES = {
    "R1_FRACTIONNEMENT": 30,
    "R2_COMPTE_DE_PASSAGE": 35,
    "R3_PAYS_A_RISQUE": 35,
    "R4_REVEIL_COMPTE_DORMANT": 25,
    "R5_COLLECTE_MULTI_EMETTEURS": 25,
    "R6_INCOHERENCE_PROFIL": 20,  # +15 si répété sur 2 mois ou plus
    "R7_MONTANTS_RONDS": 15,
}
POIDS_ML_MAX = 30

# Seuils de priorité des alertes (score 0-100)
SEUIL_ALERTE = 35
SEUIL_PRIORITE_HAUTE = 60

LIBELLES_REGLES = {
    "R1_FRACTIONNEMENT": "Fractionnement : plusieurs virements entrants juste sous le seuil de vigilance en 7 jours",
    "R2_COMPTE_DE_PASSAGE": "Compte de passage : fonds reçus puis ressortis en moins de 48 h",
    "R3_PAYS_A_RISQUE": "Flux avec un pays à risque",
    "R4_REVEIL_COMPTE_DORMANT": "Réveil d'un compte dormant (> 90 jours) avec des volumes importants",
    "R5_COLLECTE_MULTI_EMETTEURS": "Collecte : nombreux émetteurs distincts en 30 jours",
    "R6_INCOHERENCE_PROFIL": "Flux entrants incohérents avec les revenus déclarés au KYC",
    "R7_MONTANTS_RONDS": "Répétition de montants ronds élevés",
}
