"""Échelle de rareté des cartes, et mise en scène qui va avec.

Chaque saison a son échelle. Le Set de Base en compte trois ; la série 151
reprend les huit raretés réelles du set, de la commune à la Rare Or.

Une rareté porte sa propre révélation (``reveal``) : c'est elle que le
navigateur joue à l'ouverture. Deux raretés voisines ne doivent jamais se
ressembler — sinon tirer une Ultra Rare ne se distingue pas d'une rare, et le
booster perd tout son intérêt.
"""

from dataclasses import dataclass

COMMUNE = "COMMUNE"
PEU_COMMUNE = "PEU_COMMUNE"
RARE = "RARE"
LEGENDAIRE = "LEGENDAIRE"
DOUBLE_RARE = "DOUBLE_RARE"
ILLUSTRATION_RARE = "ILLUSTRATION_RARE"
ULTRA_RARE = "ULTRA_RARE"
ILLUSTRATION_SPECIALE = "ILLUSTRATION_SPECIALE"
HYPER_RARE = "HYPER_RARE"


@dataclass(frozen=True, slots=True)
class Rarity:
    key: str
    label: str
    # Sigle affiché sur la carte en collection (C, PC, R, RR, IR, UR, SIR, HR).
    code: str
    # Prestige croissant : sert à trier et à choisir la plus belle carte d'un booster.
    rank: int
    color: str
    # Nom de la révélation jouée à l'ouverture, côté navigateur.
    reveal: str


RARITIES = (
    Rarity(COMMUNE, "Commune", "C", 0, "#9fb0c4", "simple"),
    Rarity(PEU_COMMUNE, "Peu commune", "PC", 1, "#7fe3b0", "sheen"),
    Rarity(RARE, "Rare", "R", 2, "#7cd7ff", "burst"),
    Rarity(LEGENDAIRE, "Légendaire", "L", 3, "#ffd76a", "flare"),
    Rarity(DOUBLE_RARE, "Double rare", "RR", 4, "#ff9ad5", "loop"),
    Rarity(ILLUSTRATION_RARE, "Illustration rare", "IR", 5, "#b58cff", "starfall"),
    Rarity(ULTRA_RARE, "Ultra rare", "UR", 6, "#63f2e4", "explosion"),
    Rarity(ILLUSTRATION_SPECIALE, "Illustration spéciale rare", "SIR", 7, "#ff7ae0", "prism"),
    Rarity(HYPER_RARE, "Rare Or", "HR", 8, "#ffcf4d", "gold"),
)

RARITIES_BY_KEY = {rarity.key: rarity for rarity in RARITIES}

# Le seuil à partir duquel la scène se teinte, les rayons tournent et le tirage
# « compte » : en dessous, la carte se retourne et c'est tout.
SPECIAL_RANK = RARITIES_BY_KEY[RARE].rank


def get_rarity(key) -> Rarity:
    """La rareté demandée, commune par défaut pour une clé inconnue."""

    return RARITIES_BY_KEY.get(key, RARITIES_BY_KEY[COMMUNE])


def is_special(key) -> bool:
    """Ce tirage mérite-t-il une mise en scène ?"""

    return get_rarity(key).rank >= SPECIAL_RANK


def best_rarity(keys):
    """La plus prestigieuse d'une poignée de raretés, ``None`` si vide."""

    known = [get_rarity(key) for key in keys]
    return max(known, key=lambda rarity: rarity.rank) if known else None


def as_dict(key) -> dict:
    """Ce que le navigateur a besoin de savoir d'une rareté."""

    rarity = get_rarity(key)
    return {
        "rarity": rarity.key,
        "rarity_label": rarity.label,
        "rarity_code": rarity.code,
        "rarity_color": rarity.color,
        "rarity_rank": rarity.rank,
        "reveal": rarity.reveal,
    }
