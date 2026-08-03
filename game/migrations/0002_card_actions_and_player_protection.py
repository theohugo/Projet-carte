from django.db import migrations, models

ACTION_BY_POKEDEX_ID = {
    # Attaques rapides ou puissantes : le joueur suivant pioche deux cartes.
    25: "DRAW_TWO",  # Pikachu
    66: "DRAW_TWO",  # Machoc
    94: "DRAW_TWO",  # Ectoplasma
    149: "DRAW_TWO",  # Dracolosse
    # Les deux jokers les plus rares cumulent changement de type et +4.
    150: "DRAW_FOUR",  # Mewtwo
    151: "DRAW_FOUR",  # Mew
    # Pokémon associés à la copie, l'illusion ou au changement de trajectoire.
    83: "REVERSE",  # Canarticho
    122: "REVERSE",  # M. Mime
    132: "REVERSE",  # Métamorph
    137: "REVERSE",  # Porygon
    # Pokémon défensifs : confèrent un bouclier contre le prochain +2/+4.
    9: "SHIELD",  # Tortank
    95: "SHIELD",  # Onix
    143: "SHIELD",  # Ronflex
    208: "SHIELD",  # Steelix
}


def assign_card_actions(apps, schema_editor):
    PokemonCard = apps.get_model("game", "PokemonCard")
    for pokedex_id, action in ACTION_BY_POKEDEX_ID.items():
        PokemonCard.objects.filter(pokedex_id=pokedex_id).update(action=action)


class Migration(migrations.Migration):
    dependencies = [("game", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="pokemoncard",
            name="action",
            field=models.CharField(
                choices=[
                    ("NORMAL", "Aucun effet"),
                    ("DRAW_TWO", "+2"),
                    ("DRAW_FOUR", "+4"),
                    ("REVERSE", "Inversion"),
                    ("SHIELD", "Protection"),
                ],
                default="NORMAL",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="gameplayer",
            name="has_protection",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(assign_card_actions, migrations.RunPython.noop),
    ]
