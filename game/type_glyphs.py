"""Pictogrammes des 18 types Pokémon, dessinés en SVG.

Sur une carte, le type se lit à son symbole avant de se lire à son nom : une
goutte pour Eau, un éclair pour Électrik. Chaque entrée est le contenu d'un
``<symbol>`` sur une grille de 24, rempli avec ``currentColor`` — la couleur
du type vient du fond, le pictogramme reste sombre par-dessus.

Un tracé tient sur une seule ligne, même longue : couper une chaîne au milieu
d'un attribut ``d`` recolle deux nombres (« -2 » + « 2.4 » donne « -22.4 ») et
déforme le dessin sans rien casser d'autre.

Les clés sont les ``slug`` de :mod:`game.pokemon_types` ; un test vérifie
qu'aucun type ne se retrouve sans dessin.
"""

# fmt: off
TYPE_GLYPHS = {
    "normal": '<circle cx="12" cy="12" r="6.6" fill="none" stroke="currentColor" stroke-width="3.6"/>',

    "fire": '<path d="M12.6 1.8c.4 3.4 2.6 4.6 4.2 6.8a8 8 0 0 1 1.6 4.9c0 4.2-2.9 7.3-6.6 7.3s-6.4-3.1-6.4-7.1c0-2.4 1-4.2 2.4-5.6.2 1.3.8 2.2 1.8 2.6-.1-3.9.9-6.6 3-8.9Z"/>',

    "water": '<path d="M12 2c3.9 4.9 6.8 8.3 6.8 11.9A6.8 6.8 0 0 1 5.2 13.9C5.2 10.3 8.1 6.9 12 2Z"/>',

    "electric": '<path d="M14.4 1.6 5.4 13.6h4.9L9.4 22.4l9.2-12.6h-5.3l1.1-8.2Z"/>',

    "grass": '<path d="M20.4 3.6C10 3 4.2 8 4.2 14.4c0 2.1.7 3.8 1.8 5l3-3.2c-.2-4 2.4-7 6.6-8.4-3.4 2.2-5.5 4.9-5.6 8.3l-3 3.2c1.2.8 2.7 1.2 4.3 1.2 6.3 0 10.2-6.5 9.1-16.9Z"/>',

    "ice": '<g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2.6v18.8M3.9 7.2l16.2 9.6M20.1 7.2 3.9 16.8"/><path d="M9.4 4.8 12 7.4l2.6-2.6M9.4 19.2 12 16.6l2.6 2.6"/></g>',

    # Poing fermé, pouce replié sur le côté.
    "fighting": '<path d="M5.4 11c0-2.1 1.7-3.8 3.8-3.8h6c2.1 0 3.8 1.7 3.8 3.8v2.8a6.2 6.2 0 0 1-6.2 6.2h-1.2A6.2 6.2 0 0 1 5.4 13.8V11Z"/><path d="M8.8 7.6V6a1.5 1.5 0 0 1 3 0v1.6M12.8 7.6V5.2a1.5 1.5 0 0 1 3 0v2.4M5.6 12.6H4.2a1.6 1.6 0 0 0 0 3.2h1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',

    "poison": '<path d="M11.2 4.4c3.1 3.9 5.4 6.6 5.4 9.5a5.4 5.4 0 0 1-10.8 0c0-2.9 2.3-5.6 5.4-9.5Z"/><circle cx="18.3" cy="6.4" r="2"/><circle cx="19.5" cy="11.6" r="1.3"/>',

    # Sol : des strates de terre, pas un relief — le relief, c'est Roche.
    "ground": '<path d="M2.8 14.4c2.4-1.6 4.7-1.6 6.9 0s4.5 1.6 6.9 0c1.6-1.1 3-1.4 4.6-.9v7.3H2.8v-6.4Z"/><path d="M4 9.4c2-1.4 3.9-1.4 5.7 0s3.7 1.4 5.7 0c1.3-.9 2.5-1.2 3.8-.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',

    # Deux ailes séparées : une aile pleine se confondrait avec la feuille de Plante.
    "flying": '<path d="M11.2 12.4C8.4 8 5 5.8 1 5.8c.8 4.2 3.4 7 7.8 8.4-2.6.4-5 0-7.2-1.2 1.8 3.8 5.2 5.8 10.4 6v-6.6Z"/><path d="M12.8 12.4C15.6 8 19 5.8 23 5.8c-.8 4.2-3.4 7-7.8 8.4 2.6.4 5 0 7.2-1.2-1.8 3.8-5.2 5.8-10.4 6v-6.6Z"/>',

    # Le troisième œil, symbole psy le plus lisible en petit.
    "psychic": '<path fill-rule="evenodd" d="M12 5.2c4.7 0 8.6 3.5 9.8 6.8-1.2 3.3-5.1 6.8-9.8 6.8S3.4 15.3 2.2 12C3.4 8.7 7.3 5.2 12 5.2Zm0 3.4a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8Z"/>',

    "bug": '<ellipse cx="12" cy="14" rx="4.2" ry="5.6"/><circle cx="12" cy="7.4" r="2.6"/><path d="M10.4 5.4 8.4 2.8M13.6 5.4l2-2.6M7.8 11H4.4M16.2 11h3.4M7.8 15.4H4.4M16.2 15.4h3.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',

    # Deux blocs empilés : un bloc seul se lit comme l'hexagone d'Acier.
    "rock": '<path d="M9.6 3.4 14.8 5l1 5.4-4.6 3-5-2.6-.4-5.2 3.8-2.2Z"/><path d="M2.6 21.2 5.8 14l5 2.6 2-3.4 5.2 8H2.6Z"/>',

    "ghost": '<path fill-rule="evenodd" d="M12 2.8a7.2 7.2 0 0 0-7.2 7.2v11l2.4-2.2 2.4 2.2 2.4-2.2 2.4 2.2 2.4-2.2 2.4 2.2V10A7.2 7.2 0 0 0 12 2.8Zm-2.6 6.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8Zm5.2 0a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8Z"/>',

    "dragon": '<path d="M5.6 2.8c2.4 4.4 3.4 9.6 3 15.6l-2.8-2.6c.6-4.6.5-8.9-.2-13Z"/><path d="M11.4 2.2c2.4 4.6 3.4 10 3 16.2l-2.8-2.6c.6-4.8.5-9.3-.2-13.6Z"/><path d="M17.2 2.8c2.4 4.4 3.4 9.6 3 15.6l-2.8-2.6c.6-4.6.5-8.9-.2-13Z"/>',

    "dark": '<path d="M14.6 3.2A9 9 0 1 0 20 16.2a7.2 7.2 0 0 1-5.4-13Z"/>',

    "steel": '<path fill-rule="evenodd" d="M12 2.4 20.3 7v10L12 21.6 3.7 17V7L12 2.4Zm0 5.8a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Z"/>',

    "fairy": '<path d="M10.6 1.8c.9 5.2 3.1 7.4 8.3 8.3-5.2.9-7.4 3.1-8.3 8.3-.9-5.2-3.1-7.4-8.3-8.3 5.2-.9 7.4-3.1 8.3-8.3Z"/><path d="M18.4 14.6c.4 2.3 1.4 3.3 3.7 3.7-2.3.4-3.3 1.4-3.7 3.7-.4-2.3-1.4-3.3-3.7-3.7 2.3-.4 3.3-1.4 3.7-3.7Z"/>',
}
# fmt: on
