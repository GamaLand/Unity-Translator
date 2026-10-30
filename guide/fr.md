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
   Choisissez entre 1 et 36 requêtes parallèles selon le serveur. La réduction de la
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
Voir le [guide développeur](../docs/installation.md).

Le destinataire d’un ZIP partageable utilise `Kur.cmd` pour choisir le jeu correspondant
et `Kaldir.cmd` pour retirer les ajouts inchangés dont la propriété est vérifiée. Il n’a
besoin ni du modèle ni de UnityTranslator. Conservez les licences et sources incluses.
Tous les jeux Unity ne sont pas compatibles ; les contrôles ne garantissent pas la qualité.
Certains diagnostics techniques restent dans leur langue d’origine.


Les langues source et cible du jeu sont indépendantes de la langue de l’interface. Utilisez ja pour le japonais, it pour l’italien ou pt-BR pour le portugais brésilien ; d’autres codes sont acceptés. La langue source doit être présente dans le jeu. Les colonnes absentes ou ambiguës sont refusées. Le modèle doit prendre en charge la paire. Les langues, validations et règles de style des projets existants sont conservées ; vérifiez les anciennes règles propres à une langue. Testez les polices, la disposition RTL et les pluriels avec un petit patch avant de le partager. L’anglais peut aussi être la langue cible.

## Krypta FM

Pour la version correspondante de Krypta FM, choisissez `en` comme source et `tr` comme cible. Le profil 2 couvre 449 champs dans 34 TextAssets et une grille du journal ; deux sources et d’autres textes d’interface ou d’image restent exclus. Les identifiants et approbations sont conservés.

Après vérification et approbation, fermez le jeu puis examinez sous « Appliquer au jeu » le plan des deux nouveaux fichiers `winhttp.dll` et `doorstop_config.ini`. Le runtime expérimental reste dans le projet séparé ; aucun fichier original n’est remplacé. Retirez les ajouts depuis ce même projet. L’export de textes n’est pas un paquet d’installation ; les ZIP d’installation prennent aussi en charge la version Krypta en→tr correspondante. Le destinataire lance Install.cmd, examine le plan et saisit INSTALL ; Uninstall.cmd retire uniquement les ajouts propres inchangés. La combinaison portable a des tests synthétiques ; son contrôle spécifique en jeu reste à faire. Démarrage/menu, options, passage au jeu, pause et sous-titres ont été observés. Les autres écrans, changements de langue et la mise en page nécessitent une vérification manuelle ; un long libellé peut chevaucher son explication.

Les paramètres avancés permettent de désactiver le raisonnement pour les requêtes LM Studio. Cela peut réserver davantage de tokens de sortie à la traduction. La prise en charge dépend du modèle chargé et du serveur ; une option non prise en charge peut arrêter la tâche. Les valeurs par défaut et les paramètres globaux du serveur sont conservés.

## Traduction Ren'Py

Dans Textes, choisissez le moteur et lancez l’analyse. Un fichier
`game/tl/<langue>/*.rpy` fait lire tout le dossier de langue. Les `.rpy` d’origine,
`_ren.py` vérifiés et archives RPA-3.0 avec sources sont contrôlés selon des contrats
de comportement comparés à Ren'Py 8.1.2 et 8.3.6 ; la version seule ne suffit pas.
Les grands ensembles et conteneurs sans chevauchement sont pris en charge ; les
chemins ou noms de base de sources identiques sont refusés. Le lecteur couvre les
dialogues sur une ligne avec attributs de personnage et temporaires `@`, `nointeract`,
clés explicites `_()` et textes de menu. Le dialogue du menu doit précéder les choix
et ne peut pas être mélangé aux titres. Les groupes voice/nvl, dialogues multilignes,
textes dynamiques, scripts uniquement compilés et textes dans les images restent
exclus. Vérifiez les exclusions signalées. Aucun code de jeu n’est exécuté.
Les grands exports peuvent contenir plusieurs fichiers numérotés ; conservez
l’arborescence exportée complète.

Le ZIP d’installation reste limité à Ren'Py `8.1.2.23090503` ; les métadonnées privées de dépôt, d’outils IA ou d’identifiants bloquent le paquet de copie.

Utilisez le modèle, le pilote, les brouillons et la validation humaine habituels.
Les anciennes traductions des modèles restent en lecture seule dans l’historique.
Après approbation, indiquez une langue Ren'Py explicite, par exemple `turkish` ;
le code de langue n’est pas converti automatiquement. Terminez ou abandonnez les
brouillons. L’export natif prépare les fichiers dans le projet ; des traductions
approuvées contradictoires d’une même clé globale bloquent l’export.

**Créer un ZIP d’installation Ren'Py** accepte la version correspondante avec un
seul EXE de jeu à la racine. Le ZIP ne contient aucun contenu original du jeu.
Extrayez-le hors du jeu d’origine puis lancez `Install.cmd`. Sélectionnez le jeu
correspondant et un dossier de sortie distinct, puis examinez le plan exact.
L’installation prépare une copie traduite complète et demande de l’espace disque
supplémentaire. Elle ne remplace pas les originaux et ne démarre pas le jeu.
`Play-Translated.cmd` dans la copie lance la langue du paquet. Les sauvegardes,
journaux et caches d’origine ne sont pas copiés ; les nouvelles sauvegardes sont séparées.
Le destinataire n’a besoin ni de Python, ni de modèle, ni de UnityTranslator.

Gardez le ZIP pour `Remove.cmd`. Seuls les fichiers propres inchangés de la copie
sont retirés ; les fichiers modifiés ou créés à l’exécution et les reçus sont préservés.
Le dossier n’est pas nécessairement vidé.
CLI : `export-renpy-zip --game ... --project ... --language turkish`.
L’installation directe dans le dossier d’origine reste indisponible.

Si le rapport du pilote indique une tâche en cours, actualisez-le après son arrêt. Un pilote annulé peut être évalué si tout l’échantillon requis a été tenté et contient des résultats terminés. Cela autorise le travail complet avec les mêmes réglages et sources, sans valider les traductions.

Après évaluation du pilote, les modifications enregistrées du glossaire/style s’appliquent aux nouvelles requêtes sans nouvel essai. Les requêtes en cours gardent leurs règles initiales ; les traductions existantes restent inchangées. Examinez les entrées concernées et relancez explicitement leur traduction si nécessaire. Utiliser les réglages du pilote évalué rétablit le modèle et la génération en conservant le glossaire/style actuel.

Dans Révision, Retraduire les entrées de cette page envoie jusqu’à 200 entrées de la page filtrée visible dans la file commune avec le modèle actuel et le glossaire/style enregistré. Un pilote évalué correspondant est requis. Les brouillons et entrées en cours sont exclus. Le texte validé reste sélectionné ; les nouveaux candidats apparaissent dans l’historique. L’onglet Traduction affiche la progression.

Dans Révision, **Actions groupées** permet d’approuver les traductions non vides exactement identiques à la source ou de remettre les traductions vides en attente. Toutes les pages des filtres actuels sont concernées, avec nombre et exemples avant confirmation. Effacez les filtres pour tout le projet. Brouillons, entrées en file/en cours et approbations existantes sont exclus. Une copie peut rester une phrase non traduite : l’approbation est votre décision explicite. La remise en attente conserve l’historique et n’envoie aucune requête au modèle ; lancez ensuite un travail groupé dans Traduire avec le pilote évalué habituel.
