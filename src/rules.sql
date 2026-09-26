-- =====================================================================
-- Règles de surveillance LCB-FT (SQLite, fonctions de fenêtrage)
-- Chaque règle renvoie : membre_id, regle, nb_occurrences, detail
-- Paramètres injectés par Python : :seuil, :pays_list (via table pays_risque)
-- =====================================================================

-- R1 : fractionnement — au moins 3 virements entrants entre 85 % et 100 % du
-- seuil de vigilance sur une fenêtre glissante de 7 jours
WITH proches_seuil AS (
    SELECT membre_id, horodatage, montant,
           COUNT(*) OVER (
               PARTITION BY membre_id ORDER BY julianday(horodatage)
               RANGE BETWEEN 7 PRECEDING AND CURRENT ROW
           ) AS nb_7j
    FROM transactions
    WHERE sens = 'IN' AND montant >= 0.85 * :seuil AND montant < :seuil
)
SELECT membre_id, 'R1_FRACTIONNEMENT' AS regle, MAX(nb_7j) AS nb_occurrences,
       'max ' || MAX(nb_7j) || ' virements sous le seuil en 7 j' AS detail
FROM proches_seuil GROUP BY membre_id HAVING MAX(nb_7j) >= 3

UNION ALL

-- R2 : compte de passage — entrée >= 5 000 € puis sorties >= 80 % du montant
-- dans les 48 heures vers des bénéficiaires jamais payés auparavant
-- (limite : les 30 premiers jours du jeu de données servent d'historique)
-- (exclut les paiements récurrents de fournisseurs d'un professionnel)
SELECT membre_id, 'R2_COMPTE_DE_PASSAGE', COUNT(*),
       COUNT(*) || ' entrée(s) ressortie(s) en < 48 h vers de nouveaux bénéficiaires'
FROM (
    SELECT e.membre_id, e.tx_id
    FROM transactions e
    JOIN transactions s
      ON s.membre_id = e.membre_id AND s.sens = 'OUT' AND s.canal <> 'CARTE'
     AND julianday(s.horodatage) BETWEEN julianday(e.horodatage) AND julianday(e.horodatage) + 2
     AND NOT EXISTS (
         SELECT 1 FROM transactions h
         WHERE h.membre_id = s.membre_id AND h.contrepartie_id = s.contrepartie_id
           AND h.horodatage < e.horodatage
     )
    WHERE e.sens = 'IN' AND e.montant >= 5000
      -- au moins 30 jours d'historique, sinon tout bénéficiaire paraît « nouveau »
      AND julianday(e.horodatage) - 30 >= (SELECT julianday(MIN(horodatage)) FROM transactions)
    GROUP BY e.membre_id, e.tx_id, e.montant
    HAVING SUM(s.montant) >= 0.8 * e.montant
)
GROUP BY membre_id

UNION ALL

-- R3 : flux avec un pays à risque
SELECT t.membre_id, 'R3_PAYS_A_RISQUE', COUNT(*),
       GROUP_CONCAT(DISTINCT t.pays_contrepartie) || ' — ' || CAST(ROUND(SUM(t.montant)) AS INT) || ' €'
FROM transactions t JOIN pays_risque p ON p.code = t.pays_contrepartie
GROUP BY t.membre_id

UNION ALL

-- R4 : réveil d'un compte dormant — plus de 90 jours sans opération, puis
-- plus de 10 000 € de flux dans les 30 jours qui suivent
SELECT r.membre_id, 'R4_REVEIL_COMPTE_DORMANT', 1,
       CAST(r.jours_inactivite AS INT) || ' j d''inactivité puis ' || CAST(ROUND(SUM(t.montant)) AS INT) || ' € en 30 j'
FROM (
    SELECT membre_id, horodatage,
           julianday(horodatage) - julianday(LAG(horodatage) OVER (PARTITION BY membre_id ORDER BY horodatage)) AS jours_inactivite
    FROM transactions
) r
JOIN transactions t
  ON t.membre_id = r.membre_id
 AND julianday(t.horodatage) BETWEEN julianday(r.horodatage) AND julianday(r.horodatage) + 30
WHERE r.jours_inactivite > 90
GROUP BY r.membre_id, r.horodatage, r.jours_inactivite
HAVING SUM(t.montant) > 10000

UNION ALL

-- R5 : collecte — au moins 15 émetteurs distincts sur 30 jours glissants
-- (hors membres professionnels, pour qui c'est l'activité normale)
SELECT membre_id, 'R5_COLLECTE_MULTI_EMETTEURS', MAX(nb_emetteurs),
       'jusqu''à ' || MAX(nb_emetteurs) || ' émetteurs distincts en 30 j'
FROM (
    SELECT e.membre_id, e.tx_id, COUNT(DISTINCT p.contrepartie_id) AS nb_emetteurs
    FROM transactions e
    JOIN membres m ON m.membre_id = e.membre_id AND m.type_membre = 'PARTICULIER'
    JOIN transactions p
      ON p.membre_id = e.membre_id AND p.sens = 'IN'
     AND julianday(p.horodatage) BETWEEN julianday(e.horodatage) - 30 AND julianday(e.horodatage)
    WHERE e.sens = 'IN'
    GROUP BY e.membre_id, e.tx_id
)
GROUP BY membre_id
HAVING MAX(nb_emetteurs) >= 15

UNION ALL

-- R6 : incohérence avec le profil KYC — flux entrants mensuels > 3 fois
-- les revenus (ou le chiffre d'affaires) déclarés. Une ligne par mois concerné :
-- un seul mois (ex. héritage) pèse moins qu'une incohérence répétée.
SELECT membre_id, 'R6_INCOHERENCE_PROFIL', COUNT(*) AS nb_mois,
       COUNT(*) || ' mois > 3x les revenus déclarés (max ' || CAST(ROUND(MAX(total)) AS INT)
       || ' € vs ' || CAST(MAX(revenu) AS INT) || ' €)'
FROM (
    SELECT t.membre_id, strftime('%Y-%m', t.horodatage) AS mois, SUM(t.montant) AS total,
           m.revenu_mensuel_declare AS revenu
    FROM transactions t JOIN membres m USING (membre_id)
    WHERE t.sens = 'IN'
    GROUP BY t.membre_id, mois
    HAVING SUM(t.montant) > 3 * m.revenu_mensuel_declare
)
GROUP BY membre_id

UNION ALL

-- R7 : répétition de montants ronds élevés (>= 2 000 €, multiples de 1 000)
SELECT membre_id, 'R7_MONTANTS_RONDS', COUNT(*),
       COUNT(*) || ' opérations à montant rond'
FROM transactions
WHERE montant >= 2000 AND montant = CAST(montant / 1000 AS INT) * 1000
GROUP BY membre_id
HAVING COUNT(*) >= 5;
