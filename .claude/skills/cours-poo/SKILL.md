---
name: cours-poo
description: Notions de programmation orientée objet (blocs, portée, flux de contrôle, classes, instances, encapsulation, héritage, polymorphisme) — référence de cours pour ce projet.
---

# Programmation orientée objet

## Blocs, Portée & Flux de Contrôle

Un programme informatique n'est pas une simple liste d'instructions exécutées de haut en bas sans détour. Pour résoudre des problèmes complexes, le programme doit prendre des décisions, répéter des tâches et organiser ses données dans des espaces de visibilité scellés.

### Blocs de code et portée (scope)

Un **bloc de code** est un groupe d'instructions délimité qui s'exécute ensemble :
- En C++, Java, JS, C# : délimité par des accolades `{ ... }`.
- En Python : délimité par l'**indentation** (espaces).

La **portée (scope)** définit la durée de vie et la visibilité d'une variable. Une variable créée à l'intérieur d'un bloc naît à son entrée et **meurt à sa sortie**.

Exemple de portée (Python) :

```python
# Variable Globale (accessible partout)
niveau_global = 100

def calculer_bonus():
    # Variable Locale à la fonction
    bonus_local = 25

    if bonus_local > 10:
        # Variable de bloc (portée restreinte)
        multiplicateur = 2
        total = (niveau_global + bonus_local) * multiplicateur
        return total

    # ERREUR si on essaie d'accéder à multiplicateur ici !
```

**Règle d'or de la portée — le principe du moindre privilège :** une variable doit toujours être déclarée dans la portée la plus restreinte possible. Cela évite qu'une autre partie du programme ne la modifie par accident (effet de bord).

1. **Variables Globales :** à utiliser avec une extrême parcimonie (de préférence uniquement pour des constantes immuables).
2. **Variables Locales :** créées lors de l'appel d'une fonction et détruites dès le `return`.

### Contrôle du flux : conditionnelles & match

Le flux d'exécution représente le chemin emprunté par l'ordinateur à travers le code. Les structures conditionnelles permettent au programme d'emprunter des branches différentes selon la vérité d'une expression logique.

```python
# Structure if / elif / else
if solde >= prix:
    valider_achat()
elif solde > 0:
    proposer_credit()
else:
    refuser_achat()

# Pattern Matching (switch / match)
match statut:
    case "ACTIF":
        autoriser()
    case "SUSPENDU":
        avertir()
    case _:
        bloquer()
```

### Boucles et itérations

Trois formes principales :

```python
# 1. Boucle Pour (For) avec compteur
for i in range(5):
    print(f"Étape {i}")

# 2. Boucle Pour Chaque (For-Each) sur collection
animaux = ["Chat", "Chien", "Oiseau"]
for animal in animaux:
    print(animal)

# 3. Boucle Tant Que (While)
compteur = 0
while compteur < 5:
    compteur += 1
```

`break` interrompt la boucle, `continue` saute à l'itération suivante.

### Fonctions, méthodes & lambdas

Une **fonction** est un bloc de code réutilisable qui prend des **entrées (paramètres)**, effectue des traitements, et retourne un **résultat (valeur de retour)**.

- **Fonction vs Méthode :** une fonction est autonome ; une **méthode** est une fonction rattachée à un objet ou une classe.
- **Fonction Anonyme / Lambda :** une fonction courte déclarée en ligne sans nom explicite, très utilisée pour filtrer ou transformer des données.

```python
# Fonction classique
def calculer_surface(largeur, hauteur):
    return largeur * hauteur

# Fonction Lambda (anonyme)
multiplier_par_deux = lambda x: x * 2

print(multiplier_par_deux(5))  # Résultat: 10
```

**Lien :** https://modules.apti.space/developpement/programation-objet/blocs-et-flux

## Classes & Instances

La Programmation Orientée Objet (POO) est un paradigme qui organise le code autour d'**objets du monde réel** (ou concepts abstraits) plutôt que de simples suites de fonctions. La distinction la plus importante à intégrer est la différence entre la **Classe** et l'**Instance (l'Objet)**.

### L'analogie fondamentale : le moule et la pièce

**La Classe = Le Moule (Plan).** Une Classe est un modèle abstrait, une recette ou un moule de fabrication : elle ne consomme pas de mémoire pour stocker des données réelles, elle définit la structure (attributs) et les capacités (méthodes).

```python
# La Classe (Le Moule à Pièces)
class PieceDeMonnaie:
    def __init__(self, valeur, devise):
        self.valeur = valeur    # Attribut
        self.devise = devise    # Attribut

    def afficher(self):         # Méthode
        return f"{self.valeur} {self.devise}"
```

**L'Instance = La Pièce (L'Objet).** Une Instance est un objet concret frappé à partir du moule : elle existe réellement en mémoire (Heap), avec sa propre identité et ses propres valeurs pour chaque attribut.

```python
# Instanciation (Fabrication de 2 pièces distinctes)
piece1 = PieceDeMonnaie(1, "EUR")
piece2 = PieceDeMonnaie(2, "EUR")

print(piece1.afficher())  # "1 EUR"
print(piece2.afficher())  # "2 EUR"
```

### La mémoire : Stack vs Heap

**Stack (la pile d'exécution) :** stocke les variables locales d'une fonction et les **références (adresses mémoire)** vers les objets. Gestion ultra-rapide en LIFO (*Last In, First Out*), taille limitée.

**Heap (le tas mémoire) :** stocke le **corps complet des objets et instances** créés dynamiquement. Taille beaucoup plus grande, géré automatiquement par le **Garbage Collector** en Python/Java/JS.

**Le piège classique — passage par valeur vs par référence :**
- **Types primitifs** (entiers, booléens) : copiés par **valeur**. Modifier la copie ne touche pas à l'original.
- **Objets / Instances** : copiés par **référence** (adresse mémoire). Deux variables pointant vers la même instance modifient le **même objet sous-jacent** !

### Les trois piliers de la POO

**Encapsulation.** Cacher les détails d'implémentation internes d'un objet et ne laisser l'extérieur interagir qu'à travers une interface contrôlée (méthodes publiques ou getters/setters).

```python
class CompteSecurise:
    def __init__(self, solde_initial):
        self.__solde = solde_initial  # Attribut privé (masqué)

    def deposer(self, montant):
        if montant > 0:
            self.__solde += montant

    def get_solde(self):
        return self.__solde
```

**Héritage.** Permet à une classe enfant d'hériter automatiquement des attributs et méthodes d'une classe parent, tout en pouvant les enrichir ou les redéfinir (*override*).

```python
class Vehicule:  # Parent
    def rouler(self):
        print("Vroum !")

class VoitureElectrique(Vehicule):  # Enfant
    def recharger(self):
        print("Recharge en cours...")
```

**Polymorphisme.** ("plusieurs formes") permet de traiter des objets d'espèces différentes via une même interface commune sans se soucier de leur classe exacte.

```python
def faire_travailler(employes):
    for emp in employes:
        emp.travailler()  # Chaque sous-classe répond à sa façon !
```

**Lien :** https://modules.apti.space/developpement/programation-objet/classes-et-instances
