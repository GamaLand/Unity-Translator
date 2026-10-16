# Guide d’utilisation de UnityTranslator

## Installation et langue

Sous Windows x64, extrayez **toute** l’archive ZIP dans un dossier séparé et lancez
`UnityTranslator.exe`. Le paquet prêt à l’emploi ne nécessite pas Python.
Pour démarrer depuis les sources :

```powershell
uv sync --locked --extra ui
uv run --extra ui unitytranslator gui
```

L’anglais est la langue par défaut. Le menu **Language**, à côté de **Help**, propose
huit langues. Le choix prend effet au prochain démarrage et ne modifie pas les langues
source et cible du projet.

## Traduction

1. **Projet :** choisissez le dossier du jeu, un dossier de projet séparé et les codes
   de langue. Ouvrez un projet existant pour reprendre votre travail.
2. **Textes :** analysez la compatibilité, sélectionnez une source prise en charge et
   extrayez les textes. L’extraction et l’installation ont des compatibilités distinctes.
3. **Modèle :** démarrez LM Studio ou llama-server et chargez vous-même le modèle.
   Indiquez l’adresse locale et l’identifiant du modèle, puis testez la connexion.
4. **Glossaire :** ajoutez au besoin des noms à conserver, des termes et des règles de style.
5. **Traduction :** examinez d’abord un essai représentatif avant la traduction globale.
   Choisissez entre 1 et 16 requêtes parallèles selon le serveur. La réduction de la
   fenêtre n’arrête pas le travail. La pause attend les requêtes en cours ; l’annulation
   interrompt les tâches du client.
6. **Révision :** comparez, corrigez, enregistrez puis approuvez les traductions.
   L’enregistrement d’un brouillon ne vaut pas approbation. L’approbation par page ne
   concerne que les éléments admissibles sélectionnés. Pour tout approuver, confirmez
   d’abord le nombre et les avertissements, puis saisissez exactement la phrase affichée
   et appuyez sur le dernier bouton. Vous pouvez annuler aux deux étapes. Les brouillons
   et erreurs de format sont exclus ; une liste modifiée bloque toute approbation partielle.

## Sauvegarder, installer et partager

Exportez un JSON ou une sauvegarde du projet. Fermez le jeu, préparez le plan dans
l’onglet d’application au jeu, vérifiez les nouveaux fichiers et autorisez séparément
l’installation. Lancez ensuite le jeu vous-même pour contrôler caractères, mise en page
et sens. Cette intégration reste expérimentale.

Retirez les ajouts depuis le projet qui les a installés. Ne supprimez pas aveuglément
`winhttp.dll`/`doorstop_config.ini` et ne réinitialisez pas l’inventaire d’origine.
Voir le [guide développeur](../docs/development.md).

Le destinataire d’un ZIP partageable utilise `Kur.cmd` pour choisir le jeu correspondant
et `Kaldir.cmd` pour retirer les ajouts inchangés dont la propriété est vérifiée. Il n’a
besoin ni du modèle ni de UnityTranslator. Conservez les licences et sources incluses.
Tous les jeux Unity ne sont pas compatibles ; les contrôles ne garantissent pas la qualité.
Certains diagnostics techniques restent dans leur langue d’origine.


Les langues source et cible du jeu sont indépendantes de la langue de l’interface. Utilisez ja pour le japonais, it pour l’italien ou pt-BR pour le portugais brésilien ; d’autres codes sont acceptés. La langue source doit être présente dans le jeu. Les colonnes absentes ou ambiguës sont refusées. Le modèle doit prendre en charge la paire. Les langues, validations et règles de style des projets existants sont conservées ; vérifiez les anciennes règles propres à une langue. Testez les polices, la disposition RTL et les pluriels avec un petit patch avant de le partager. L’anglais peut aussi être la langue cible.
