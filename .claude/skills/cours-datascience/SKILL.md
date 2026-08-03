---
name: cours-datascience
description: Data science / ML — cycle de vie de la donnée, modèles & apprentissage, biais-variance (over/underfitting), statistiques descriptives, réseaux de neurones profonds, autoencodeurs/VAE.
---

# Data Science / Machine Learning

## Introduction à la Science des Données

**L'entonnoir de raffinage de la donnée** (analogie du pétrole) : à chaque étape le volume de données diminue mais sa valeur stratégique augmente. Signal Brut (100%) → Information Structurée (~75%) → Connaissance (~50%) → Décision Métier (~35%).

**Cycle de vie de la donnée (7 étapes, inspiré CRISP-DM/OSEMN)** — processus itératif, non strictement linéaire :

1. **Acquisition** — API, web scraping, capteurs IoT. **Batch** (historique) vs **Streaming** (temps réel).
2. **Nettoyage** — étape la plus chronophage (**80% du temps** projet). Principe **Garbage In, Garbage Out (GIGO)**.
3. **Visualisation** — chiffres bruts → signaux visuels actionnables.
4. **Analyse Exploratoire (EDA)** — motifs, corrélations, anomalies (*outliers*).
5. **Modélisation** — ML : prédiction/classification/clustering, **Feature Engineering**.
6. **Évaluation & MLOps** — métriques (F1-Score, RMSE) ; en production, surveillance continue de la **dérive (Drift)**.
7. **Communication** — **Data Storytelling**, dashboards, rapports.

Si une dérive est détectée en production (étape 6), le MLOps ré-enclenche l'acquisition pour ré-entraîner le modèle.

**Lien :** https://modules.apti.space/datascience/intro-datascience

## Modèles & Apprentissage Automatique

**Analogie du moulage** : les **Données** = la figurine de référence (matrices de nombres) ; le **Modèle** = matière brute qui se moule autour, définie par des **paramètres** modifiables ; l'**Apprentissage** = presser/déformer/ajuster itérativement (les **époques**) pour que le modèle épouse au mieux les données réelles et puisse ensuite en générer de nouvelles instances.

**Lien :** https://modules.apti.space/ml/mod%C3%A8les

## Compromis Biais-Variance (Under/Overfitting)

Trop rigide → rate les tendances (**biais élevé**, *underfitting*). Trop fluide → mémorise le bruit (**variance élevée**, *overfitting*). Entre les deux : la zone de généralisation optimale.

**Biais** — erreur systématique d'un modèle trop simpliste :
$$\text{Biais}(\hat{Y}) = E[\hat{Y}] - Y$$

**Variance** — sensibilité excessive aux fluctuations du jeu d'entraînement (mémorise le bruit) :
$$\text{Variance}(\hat{Y}) = E\left[(\hat{Y} - E[\hat{Y}])^2\right]$$

**Double descente** : en Deep Learning, la perte peut redescendre pour de très grands modèles (le modèle découvre des règles plus simples/robustes) — souvent lié à un scaling composite (taille modèle + données variant simultanément).

**Diagnostic pratique** : erreur d'entraînement très faible + erreur de test élevée → variance excessive → ajuster l'architecture ou régulariser, plutôt que sur-interpréter les perfs d'entraînement.

**Lien :** https://modules.apti.space/ml/under-overfitting

## Statistiques Descriptives

Exemple fil rouge : série **4, 6, 7, 9, 14, 15, 17**.

**Moyenne** — point d'équilibre de la série, sensible aux outliers :
$$\bar{x} = \frac{x_1 + x_2 + \cdots + x_n}{n}$$

**Médiane et quartiles** — coupent la série **triée** en groupes égaux (Q1 ≈ 1er quart, médiane = milieu, Q3 ≈ 3e quart). L'intervalle interquartile (Q1–Q3) contient la partie centrale des données.

**Variance** — dispersion autour de la moyenne (écarts au carré, pour éviter que + et − s'annulent, et amplifier les grands écarts) :
$$V = \frac{(x_1-\bar{x})^2 + \cdots + (x_n-\bar{x})^2}{n}$$

**Écart type** — racine de la variance, revient dans la même unité que les données ("distance typique" autour de la moyenne) :
$$\sigma = \sqrt{V}$$

Ces mesures sont souvent le premier contrôle qualité d'une colonne numérique en data science.

**Lien :** https://modules.apti.space/maths/statistiques

## Réseaux de Neurones Profonds (Deep Learning)

### Morphologie générale
**Couche d'entrée** (reçoit les vecteurs de caractéristiques bruts) → **Couches cachées** (Deep Learning ≥ 4 couches cachées ; apprentissage hiérarchique : formes simples → concepts abstraits) → **Couche de sortie** (softmax en classification : distribution de probabilités somme=1).

### Neurone artificiel
$$h = \sum_{i} w_i x_i + b$$
$w_i$ = poids (importance de chaque entrée), $b$ = biais (niveau d'excitation minimal).

### Propagation avant (Forward Propagation)
$$\mathbf{a}^l = \sigma\!\left(\mathbf{W}^l \mathbf{a}^{l-1} + \mathbf{b}^l\right)$$
Formalisme vectoriel nécessaire pour l'accélération GPU (calcul matriciel parallèle). La non-linéarité de $\sigma$ est impérative — sans elle, le réseau s'effondre en simple régression linéaire.

### Rétropropagation (Backpropagation)
Règle de la chaîne pour calculer la contribution d'un poids à l'erreur :
$$\frac{\partial \mathcal{L}}{\partial w} = \frac{\partial \mathcal{L}}{\partial a} \cdot \frac{\partial a}{\partial z} \cdot \frac{\partial z}{\partial w}$$
Les gradients indiquent la direction/amplitude de correction des poids (descente de gradient).

### Fonctions d'activation
- **Sigmoïde/TanH** : saturent aux extrêmes (dérivée → 0), bloquent le gradient.
- **ReLU** ($\max(0,x)$) : simple, rapide, mais "Dying ReLU" (gradient nul si entrée négative).
- **Softmax** : distribution de probabilités en sortie.
- **GELU** : pilier des Transformers, flux de gradient fluide.
- **SELU** : auto-normalisante.
- **Swish** ($x \cdot \text{sigmoid}(\beta x)$) : équivaut à SiLU quand $\beta=1$.

### Vanishing / Exploding Gradient
$$\frac{\partial \mathcal{L}}{\partial w^1} = \frac{\partial \mathcal{L}}{\partial a^L} \cdot \left( \prod_{k=2}^{L} w^k \sigma'(z^{k-1}) \right) \sigma'(z^1) x^0$$
Termes < 1 en cascade → **vanishing** (gradient s'annule, premières couches n'apprennent plus). Termes > 1 → **exploding** (croissance exponentielle, updates chaotiques).

### Solutions
- **ReLU + initialisation intelligente**.
- **Batch Normalization** (Ioffe & Szegedy 2015) : normalise chaque mini-lot (μ, σ²) puis applique une échelle/décalage apprenables (γ, β). Ordre standard : Linéaire → BN → Activation.
- **Portes (gates)** LSTM/GRU : "voies rapides" pour l'état de la cellule, contournent le vanishing gradient sur longues séquences.

### Limites du MLP
- **Incapacité spatiale** (traite chaque pixel indépendamment, explosion du nombre de paramètres) → motive les **CNN**.
- **Rigidité séquentielle** (pas de mémoire du passé) → motive **RNN, LSTM, GRU, Transformers** (le bloc FFN d'un Transformer reste structurellement un MLP à 2 couches).
- **LR schedulers** : StepLR, ReduceLROnPlateau, CosineAnnealingLR, Warmup+Decay (Transformers).

**Lien :** https://deeplearning.apti.space/cours/2_r%C3%A9seaux_de_neurones/

## Autoencodeurs & VAE

### Autoencodeur classique (AE)
Architecture "sablier" : **Entrée** $x \in \mathbb{R}^n$ → **Encodeur** $f_\theta(x) \to z$ → **Bottleneck** $z \in \mathbb{R}^d$ ($d \ll n$, force la condensation en concepts sémantiques) → **Décodeur** $g_\phi(z) \to \hat{x}$ → **Sortie** $\hat{x}$.

Erreur de reconstruction :
$$\mathcal{L}_{AE}(\theta, \phi) = \| x - g_\phi(f_\theta(x)) \|^2$$

Applications : **Denoising AE** (reconstruire une version propre à partir d'une entrée bruitée, force à capturer la structure réelle) ; **détection d'anomalies** (entraîné sur données normales, erreur de reconstruction élevée sur données anormales).

### Du déterminisme au probabilisme : le VAE
L'**Autoencodeur Variationnel** encode l'entrée sous forme de paramètres d'une distribution (moyenne $\mu$, écart-type $\sigma$) plutôt qu'un point fixe.
- **AE** : concepts = points isolés → interpolation traverse des "trous sémantiques" (décodages invalides).
- **VAE** : nuages de probabilité qui se recouvrent → interpolation continue et réaliste entre concepts.

### VQ-VAE : espace latent discret
Remplace l'espace latent continu par un **Codebook** fini de vecteurs représentatifs (utile pour données de nature discrète : mots, éléments d'image). Projection sur le code le plus proche :
$$k^* = \operatorname{argmin}_k \| z_e(x) - e_k \|_2$$

**Lien :** https://modules.apti.space/llm/vae
