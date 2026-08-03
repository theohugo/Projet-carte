---
name: cours-ui-ux
description: UI/UX — théorie des couleurs (cercle d'Itten, harmonies, WCAG, CIELAB), color picker LAB, et bonnes pratiques d'iconographie (SVG, tailles, touch target).
---

# UI/UX

## lab-color-picker.com — CSS lab() Color Picker

Outil interactif de sélection de couleur dans l'espace colorimétrique **CIELAB (L\*a\*b\*)**, générant le code CSS `lab()` (CSS Color Module 4). Trois axes perceptifs exposés directement :

- **L\*** (Lightness) : 0 (noir) à 100 (blanc) — clarté réellement perçue par l'œil.
- **a\*** : axe Vert (négatif) ↔ Rouge (positif).
- **b\*** : axe Bleu (négatif) ↔ Jaune (positif).

Interface : sphère 3D interactive (rotation/pan/zoom), curseurs L*/a*/b*/alpha, réglage du chroma max (C*), gestion alpha CSS, mode « mask out-of-gamut » (atténue les couleurs non représentables en sRGB), export des valeurs.

**Différence avec un picker RGB/HSL classique** : RGB/HSL ne sont pas *perceptivement uniformes* — un jaune pur (HSL) paraît plus lumineux qu'un bleu pur à L identique. CIELAB corrige ce défaut : une même valeur de L\* garantit une clarté perçue constante quelle que soit la teinte → utile pour construire des palettes cohérentes et des contrastes accessibles calculables de façon fiable.

**Lien :** https://lab-color-picker.com/

## Palettes & Harmonies de Couleurs

### Le Cercle de Johannes Itten
Cercle chromatique (Bauhaus) modélisant 12 teintes fondamentales :
- **Primaires** (triangle central) : Jaune, Rouge, Bleu.
- **Secondaires** (hexagone) : Orange (Jaune+Rouge), Violet (Rouge+Bleu), Vert (Bleu+Jaune).
- **Tertiaires** (couronne, 12 secteurs) : combinaison primaire + secondaire adjacente.

### Harmonies de couleurs
- **Teinte de base** : point d'ancrage, souvent lié à l'identité de marque.
- **Complémentaire** (180°) : fort contraste, idéal appels à l'action.
- **Triade** (3 couleurs à 120°) : équilibre dynamique.
- **Tétrade** (4 couleurs, 2 paires complémentaires à 90°) : interfaces complexes — nécessite une teinte ultra-dominante + 3 secondaires réservées à la catégorisation.

### Contraste et accessibilité (WCAG)
Ratio de contraste minimal : **4.5:1** pour texte normal, **3:1** pour gros texte/éléments graphiques. Mesurer mathématiquement la luminance plutôt que se fier à la perception visuelle seule.

### Le modèle CIELAB et l'uniformité perceptive
RGB/HSL ne sont pas perceptivement uniformes (à S=100%/L=50% HSL, un jaune H=60° paraît bien plus lumineux qu'un bleu H=240°), ce qui fausse le calcul automatisé des contrastes. **CIELAB (L\*a\*b\*, CIE 1976)**, basé sur la théorie de l'opposition des couleurs de la vision humaine, corrige ça : L\* (luminosité fidèle), a\* (Vert↔Rouge), b\* (Bleu↔Jaune). La distance euclidienne entre deux couleurs en CIELAB (**ΔE\***) correspond à la différence visuelle réellement perçue — outil de référence pour générer des gammes de nuances équilibrées et valider mathématiquement des contrastes.

**Lien :** https://modules.apti.space/ui-ux/couleurs

## Iconographie & Métaphores Visuelles

### Rôle des icônes
Accélérateurs cognitifs (l'œil décode une forme graphique plus vite qu'il ne lit un mot) + gain de place (mobile). **Loi du double codage d'Allan Paivio** : le cerveau traite informations visuelles et verbales par des canaux distincts — associer une icône pertinente à un texte permet une identification par reconnaissance visuelle instantanée.

### Standards du marché
- **Material Design Icons** (Google) : formes géométriques pures, grille stricte, variantes (rempli/contour/arrondi/aigu).
- **Font Awesome** : catalogue immense, historiquement diffusé en police d'icônes.
- **Bootstrap Icons** (recommandé pour un Design System sur Bootstrap) : intégration légère, chargement SVG à la carte, tracés cohérents.

### Icon Fonts vs SVG
- **Icon Fonts** (`.woff`/`.ttf`) : simples à styliser mais mauvaise accessibilité (non lues par lecteurs d'écran), bugs de chargement, flou de rendu.
- **SVG** (standard recommandé) : netteté à toute échelle, stylisation CSS précise (fond/contour/animations séparés), pas de dépendance à une police externe, accessibilité native (`aria-hidden`, sémantique).

### Anatomie d'une icône SVG
`viewBox` (système de coordonnées, ex. `0 0 16 16`), `fill` (remplissage), `stroke` (contour), `stroke-width` (épaisseur du contour).

### Métaphores classiques à ne pas réinventer
- **Navigation** : maison = Accueil, liste = Menu, flèche gauche = Retour.
- **Actions** : loupe = Rechercher, crayon = Modifier, corbeille = Supprimer.
- **Système** : engrenage = Configuration, personnage = Profil, flèche sortie = Déconnexion.
- **Feedback** : coche = Succès, triangle d'alerte = Alerte, croix = Fermer.

### Dimensions et alignement
- **Bounding box** : carré invisible d'encombrement garantissant l'alignement dans listes/boutons.
- **Grille de base 8** : **16px** (icônes inline/badges), **24px** (standard boutons/nav), **32px** (boutons proéminents), **64px** (en-têtes/illustrations de statut).
- **Touch target** : zone cliquable > taille visuelle. Minimums accessibilité : **44×44px** (Apple iOS), **48×48px** (Google Android & W3C/WCAG).

**Lien :** https://modules.apti.space/ui-ux/icons
