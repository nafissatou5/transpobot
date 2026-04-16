-- ============================================================
--  TranspoBot — Base de données MySQL enrichie
--  Projet GLSi L3 — ESP/UCAD
--  5 véhicules | 5 chauffeurs | 4 lignes | 12 tarifs
--  52 trajets (janv-avril 2026) | 18 incidents
-- ============================================================



SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS trajets;
DROP TABLE IF EXISTS tarifs;
DROP TABLE IF EXISTS chauffeurs;
DROP TABLE IF EXISTS lignes;
DROP TABLE IF EXISTS vehicules;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE vehicules (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  immatriculation  VARCHAR(20)  NOT NULL UNIQUE,
  type             ENUM('bus','minibus','taxi') NOT NULL,
  capacite         INT          NOT NULL,
  statut           ENUM('actif','maintenance','hors_service') DEFAULT 'actif',
  kilometrage      INT          DEFAULT 0,
  date_acquisition DATE,
  created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chauffeurs (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  nom               VARCHAR(100) NOT NULL,
  prenom            VARCHAR(100) NOT NULL,
  telephone         VARCHAR(20),
  numero_permis     VARCHAR(30)  UNIQUE NOT NULL,
  categorie_permis  VARCHAR(5),
  disponibilite     BOOLEAN      DEFAULT TRUE,
  vehicule_id       INT,
  date_embauche     DATE,
  created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicule_id) REFERENCES vehicules(id)
);

CREATE TABLE lignes (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  code          VARCHAR(10)   NOT NULL UNIQUE,
  nom           VARCHAR(100),
  origine       VARCHAR(100)  NOT NULL,
  destination   VARCHAR(100)  NOT NULL,
  distance_km   DECIMAL(6,2),
  duree_minutes INT
);

CREATE TABLE tarifs (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  ligne_id     INT           NOT NULL,
  type_client  ENUM('normal','etudiant','senior') DEFAULT 'normal',
  prix         DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (ligne_id) REFERENCES lignes(id)
);

CREATE TABLE trajets (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  ligne_id             INT           NOT NULL,
  chauffeur_id         INT           NOT NULL,
  vehicule_id          INT           NOT NULL,
  date_heure_depart    DATETIME      NOT NULL,
  date_heure_arrivee   DATETIME,
  statut               ENUM('planifie','en_cours','termine','annule') DEFAULT 'planifie',
  nb_passagers         INT           DEFAULT 0,
  recette              DECIMAL(10,2) DEFAULT 0,
  created_at           TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ligne_id)     REFERENCES lignes(id),
  FOREIGN KEY (chauffeur_id) REFERENCES chauffeurs(id),
  FOREIGN KEY (vehicule_id)  REFERENCES vehicules(id)
);

CREATE TABLE incidents (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  trajet_id      INT  NOT NULL,
  type           ENUM('panne','accident','retard','autre') NOT NULL,
  description    TEXT,
  gravite        ENUM('faible','moyen','grave') DEFAULT 'faible',
  date_incident  DATETIME NOT NULL,
  resolu         BOOLEAN  DEFAULT FALSE,
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (trajet_id) REFERENCES trajets(id)
);

INSERT INTO vehicules (immatriculation, type, capacite, statut, kilometrage, date_acquisition) VALUES
('DK-1234-AB', 'bus',     60, 'actif',        45000, '2021-03-15'),
('DK-5678-CD', 'minibus', 25, 'actif',        32000, '2022-06-01'),
('DK-9012-EF', 'bus',     60, 'maintenance',  78000, '2019-11-20'),
('DK-3456-GH', 'taxi',     5, 'actif',       120000, '2020-01-10'),
('DK-7890-IJ', 'minibus', 25, 'actif',        15000, '2023-09-05');

INSERT INTO chauffeurs (nom, prenom, telephone, numero_permis, categorie_permis, vehicule_id, date_embauche) VALUES
('DIOP',   'Mamadou',  '+221771234567', 'P-2019-001', 'D', 1, '2019-04-01'),
('FALL',   'Ibrahima', '+221772345678', 'P-2020-002', 'D', 2, '2020-07-15'),
('NDIAYE', 'Fatou',    '+221773456789', 'P-2021-003', 'B', 4, '2021-02-01'),
('SECK',   'Ousmane',  '+221774567890', 'P-2022-004', 'D', 5, '2022-10-20'),
('BA',     'Aminata',  '+221775678901', 'P-2023-005', 'D', NULL, '2023-01-10');

INSERT INTO lignes (code, nom, origine, destination, distance_km, duree_minutes) VALUES
('L1', 'Ligne Dakar-Thiès',    'Dakar',       'Thiès',  70.5,  90),
('L2', 'Ligne Dakar-Mbour',    'Dakar',       'Mbour',  82.0, 120),
('L3', 'Ligne Centre-Banlieue','Plateau',     'Pikine', 15.0,  45),
('L4', 'Ligne Aéroport',       'Centre-ville','AIBD',   45.0,  60);

INSERT INTO tarifs (ligne_id, type_client, prix) VALUES
(1,'normal',2500),(1,'etudiant',1500),(1,'senior',1800),
(2,'normal',3000),(2,'etudiant',1800),(2,'senior',2200),
(3,'normal', 500),(3,'etudiant', 300),(3,'senior', 400),
(4,'normal',5000),(4,'etudiant',3000),(4,'senior',3500);

INSERT INTO trajets (ligne_id,chauffeur_id,vehicule_id,date_heure_depart,date_heure_arrivee,statut,nb_passagers,recette) VALUES
(1,1,1,'2026-01-06 06:00:00','2026-01-06 07:30:00','termine',52,130000),
(3,4,5,'2026-01-06 07:30:00','2026-01-06 08:15:00','termine',23,11500),
(2,3,4,'2026-01-07 07:00:00','2026-01-07 09:00:00','termine', 4,12000),
(4,2,2,'2026-01-08 09:00:00','2026-01-08 10:00:00','termine',20,100000),
(1,5,1,'2026-01-09 06:00:00','2026-01-09 07:30:00','termine',48,120000),
(3,1,1,'2026-01-10 08:00:00','2026-01-10 08:45:00','termine',19,9500),
(1,2,2,'2026-01-13 06:00:00','2026-01-13 07:30:00','termine',24,60000),
(2,4,5,'2026-01-14 07:00:00','2026-01-14 09:00:00','termine', 3,9000),
(3,3,4,'2026-01-15 07:30:00','2026-01-15 08:15:00','termine',21,10500),
(4,5,2,'2026-01-16 09:00:00','2026-01-16 10:00:00','termine',15,75000),
(1,1,1,'2026-01-20 06:00:00','2026-01-20 07:30:00','termine',55,137500),
(3,2,5,'2026-01-21 07:30:00','2026-01-21 08:15:00','termine',20,10000),
(2,3,4,'2026-01-22 07:00:00',NULL,'annule',0,0),
(4,4,5,'2026-01-23 09:00:00','2026-01-23 10:00:00','termine',22,110000),
(1,5,1,'2026-01-27 06:00:00','2026-01-27 07:30:00','termine',50,125000),
(1,1,1,'2026-02-03 06:00:00','2026-02-03 07:30:00','termine',57,142500),
(3,2,2,'2026-02-03 07:30:00','2026-02-03 08:15:00','termine',18,9000),
(2,3,4,'2026-02-04 07:00:00','2026-02-04 09:00:00','termine', 5,15000),
(4,4,5,'2026-02-05 09:00:00','2026-02-05 10:00:00','termine',19,95000),
(1,5,1,'2026-02-06 06:00:00','2026-02-06 07:30:00','termine',53,132500),
(3,1,5,'2026-02-10 07:30:00','2026-02-10 08:15:00','termine',22,11000),
(1,2,2,'2026-02-11 06:00:00','2026-02-11 07:30:00','termine',25,62500),
(2,3,4,'2026-02-12 07:00:00','2026-02-12 09:00:00','termine', 4,12000),
(4,4,5,'2026-02-13 09:00:00','2026-02-13 10:00:00','termine',17,85000),
(1,5,1,'2026-02-17 06:00:00','2026-02-17 07:30:00','termine',60,150000),
(3,2,2,'2026-02-18 07:30:00','2026-02-18 08:15:00','termine',20,10000),
(1,1,1,'2026-02-24 06:00:00','2026-02-24 07:30:00','termine',54,135000),
(2,4,5,'2026-02-25 07:00:00','2026-02-25 09:00:00','termine', 6,18000),
(1,1,1,'2026-03-01 06:00:00','2026-03-01 07:30:00','termine',55,137500),
(1,2,2,'2026-03-01 08:00:00','2026-03-01 09:30:00','termine',20,50000),
(2,3,4,'2026-03-02 07:00:00','2026-03-02 09:00:00','termine', 4,12000),
(3,4,5,'2026-03-05 07:30:00','2026-03-05 08:15:00','termine',22,11000),
(1,1,1,'2026-03-10 06:00:00','2026-03-10 07:30:00','termine',58,145000),
(4,2,2,'2026-03-12 09:00:00','2026-03-12 10:00:00','termine',18,90000),
(3,5,5,'2026-03-13 07:30:00','2026-03-13 08:15:00','termine',19,9500),
(1,4,1,'2026-03-17 06:00:00','2026-03-17 07:30:00','termine',51,127500),
(2,3,4,'2026-03-18 07:00:00','2026-03-18 09:00:00','termine', 3,9000),
(4,1,2,'2026-03-19 09:00:00','2026-03-19 10:00:00','termine',21,105000),
(3,2,5,'2026-03-20 07:30:00','2026-03-20 08:15:00','termine',20,10000),
(1,5,1,'2026-03-20 06:00:00',NULL,'en_cours',45,112500),
(1,1,1,'2026-04-07 06:00:00','2026-04-07 07:30:00','termine',53,132500),
(3,2,5,'2026-04-07 07:30:00','2026-04-07 08:15:00','termine',21,10500),
(2,3,4,'2026-04-08 07:00:00','2026-04-08 09:00:00','termine', 5,15000),
(4,4,2,'2026-04-08 09:00:00','2026-04-08 10:00:00','termine',16,80000),
(1,5,1,'2026-04-09 06:00:00','2026-04-09 07:30:00','termine',56,140000),
(3,1,5,'2026-04-09 07:30:00','2026-04-09 08:15:00','termine',18,9000),
(1,2,2,'2026-04-10 06:00:00','2026-04-10 07:30:00','termine',23,57500),
(2,3,4,'2026-04-10 07:00:00',NULL,'annule',0,0),
(1,4,1,'2026-04-11 06:00:00','2026-04-11 07:30:00','termine',59,147500),
(4,5,2,'2026-04-11 09:00:00','2026-04-11 10:00:00','termine',20,100000),
(3,2,5,'2026-04-12 07:30:00','2026-04-12 08:15:00','termine',22,11000),
(1,1,1,'2026-04-13 06:00:00',NULL,'planifie',0,0);

INSERT INTO incidents (trajet_id,type,description,gravite,date_incident,resolu) VALUES
(2, 'retard','Embouteillage Liberté 6 en heure de pointe','faible','2026-01-06 07:50:00',TRUE),
(3, 'panne', 'Crevaison pneu arrière gauche','moyen','2026-01-07 07:30:00',TRUE),
(7, 'retard','Panne feu rouge carrefour Sandaga','faible','2026-01-13 07:10:00',TRUE),
(13,'autre', 'Passager malaise, arrêt urgence','faible','2026-01-22 08:00:00',TRUE),
(16,'retard','Bouchon autoroute à péage','faible','2026-02-03 07:20:00',TRUE),
(17,'panne', 'Défaillance alternateur','grave','2026-02-03 07:45:00',TRUE),
(22,'accident','Accrochage léger au feu tricolore','moyen','2026-02-11 06:30:00',TRUE),
(25,'retard','Manifestation sur axe principal','moyen','2026-02-17 07:00:00',FALSE),
(29,'retard','Embouteillage au centre-ville','faible','2026-03-01 08:45:00',TRUE),
(30,'panne', 'Crevaison pneu avant droit','moyen','2026-03-01 08:20:00',TRUE),
(31,'panne', 'Surchauffe moteur','grave','2026-03-02 07:30:00',TRUE),
(34,'retard','Pluie torrentielle ralentit la circulation','faible','2026-03-10 07:00:00',TRUE),
(35,'accident','Accrochage léger au rond-point','grave','2026-03-12 09:20:00',FALSE),
(38,'autre', 'Contrôle de police, papiers vérifiés','faible','2026-03-17 06:45:00',TRUE),
(43,'retard','Bouchon inhabituel zone Plateau','faible','2026-04-07 07:15:00',TRUE),
(44,'panne', 'Problème de démarrage à froid','moyen','2026-04-08 07:10:00',FALSE),
(47,'accident','Choc arrière par moto au feu','grave','2026-04-09 06:50:00',FALSE),
(51,'retard','Déviation route principale en travaux','faible','2026-04-12 07:40:00',FALSE);

-- Vérification
SELECT 'vehicules'  AS table_name, COUNT(*) AS nb FROM vehicules UNION ALL
SELECT 'chauffeurs',                COUNT(*)      FROM chauffeurs UNION ALL
SELECT 'lignes',                    COUNT(*)      FROM lignes     UNION ALL
SELECT 'tarifs',                    COUNT(*)      FROM tarifs     UNION ALL
SELECT 'trajets',                   COUNT(*)      FROM trajets    UNION ALL
SELECT 'incidents',                 COUNT(*)      FROM incidents;

-- Test 1 : Trajets de la semaine
SELECT COUNT(*) AS trajets_semaine FROM trajets
WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND statut='termine';

-- Test 2 : Chauffeur avec le plus d incidents ce mois
SELECT c.nom, c.prenom, COUNT(i.id) AS nb_incidents
FROM incidents i JOIN trajets t ON i.trajet_id=t.id JOIN chauffeurs c ON t.chauffeur_id=c.id
WHERE MONTH(i.date_incident)=MONTH(NOW()) AND YEAR(i.date_incident)=YEAR(NOW())
GROUP BY c.id ORDER BY nb_incidents DESC LIMIT 1;

-- Test 3 : Véhicules en maintenance
SELECT immatriculation, type, kilometrage FROM vehicules WHERE statut='maintenance';
