# Design Doc — Platform Kernel

**Date** : 2026-04-21
**Statut** : Implémenté
**Auteur** : Sprint platform kernel

---

## Objectif et périmètre

Ce sprint introduit un **platform kernel** au-dessus du template LangGraph existant. L'objectif est de standardiser la façon dont les pipelines multi-agents sont déclarés, enregistrés et résolus, afin de faciliter l'ajout futur de "domain packs" métier sans modifier l'infrastructure API.

**Périmètre du sprint :**

- Définir un contrat abstrait (`BaseDomainPack`) que tout pipeline doit respecter.
- Créer un registre explicite (`PackRegistry`) pour découvrir et résoudre les packs disponibles.
- Migrer `MultiAgentGraph` (défini dans `core/graph.py`) vers le premier domain pack : `ResearchAnalysisPack`.
- Assurer la rétrocompatibilité totale pour les consommateurs existants.
- Ajouter le paramètre de configuration `DEFAULT_PACK_ID`.

**Hors périmètre :** chargement dynamique, API de contrôle plane, connecteurs inter-packs, versionnement des packs.

---

## Approches considérées

### Approche A — Plugin system avec auto-discovery

Chaque domain pack est un package Python installable. Au démarrage, le registre scanne les entry points `langgraph.domain_packs` déclarés dans les `pyproject.toml` des packages installés et les enregistre automatiquement.

**Avantages** : extensible sans toucher au code du noyau, découplage fort entre packs et plateforme.

**Inconvénients** : complexité d'implémentation élevée, comportement non déterministe au démarrage (dépend des packages installés dans l'environnement), débogage difficile, trop tôt dans la maturité du projet.

### Approche B — Registre statique avec enregistrement explicite (retenu)

Un dict de classe partagé sur `PackRegistry`. Les packs sont enregistrés ligne à ligne dans `platform/__init__.py` à l'import du package. Pas d'auto-discovery, pas de magie.

**Avantages** : comportement entièrement déterministe, facile à lire et à déboguer, pas de dépendance à des mécanismes Python avancés, facilement testable (`_reset()`).

**Inconvénients** : chaque nouveau pack nécessite une modification de `platform/__init__.py`.

### Approche C — Configuration déclarative (YAML/TOML)

Les packs disponibles sont listés dans un fichier de configuration. Le registre charge et instancie dynamiquement les classes via `importlib`.

**Avantages** : configuration externalisée, possible de changer les packs sans modification de code.

**Inconvénients** : introduce un loading dynamique fragile, les erreurs de typo dans le YAML échouent à l'exécution plutôt qu'à l'import, complexité accrue sans bénéfice immédiat.

### Décision

**Approche B retenue.** La simplicité et la lisibilité priment à ce stade. L'auto-discovery pourra être ajouté en sprint 2 si le nombre de packs le justifie.

---

## Architecture cible

```
platform/
  __init__.py           # Importe et enregistre tous les packs built-in au démarrage
  base_pack.py          # ABC BaseDomainPack
  registry.py           # PackRegistry — dict statique

domain_packs/
  __init__.py
  research_analysis/
    __init__.py
    pack.py             # ResearchAnalysisPack (migré de core/graph.py)

core/
  config.py             # + DEFAULT_PACK_ID setting
  graph.py              # Alias : MultiAgentGraph = ResearchAnalysisPack
```

Le flux de résolution au démarrage de l'API est :

1. L'import de `platform` déclenche `platform/__init__.py`, qui enregistre `ResearchAnalysisPack` dans `PackRegistry`.
2. Le lifespan FastAPI lit `settings.default_pack_id` (valeur par défaut : `"research_analysis"`).
3. Il appelle `PackRegistry.get(default_pack_id)` pour obtenir la classe du pack actif.
4. La classe est instanciée à la demande dans chaque requête avec les dépendances partagées (`llm`, `checkpointer`).

---

## Contrat de BaseDomainPack

`BaseDomainPack` est défini dans `platform/base_pack.py`. C'est la seule source de vérité pour le contrat que tout domain pack doit respecter.

### Attributs de classe (obligatoires)

| Attribut | Type | Description |
|---|---|---|
| `pack_id` | `str` | Identifiant stable et unique. Utilisé comme clé dans `PackRegistry`. Doit être en snake_case. |
| `name` | `str` | Nom lisible affiché dans les logs et les futures API de contrôle. |
| `description` | `str` | Une phrase décrivant ce que fait le pack. |

Ces attributs sont vérifiés par `PackRegistry.register()` : une `ValueError` est levée si `pack_id` est absent ou vide.

### Signature du constructeur

```python
def __init__(
    self,
    run_id: str | None = None,
    llm: Any | None = None,
    checkpointer: Any | None = None,
) -> None:
```

`BaseDomainPack.__init__` stocke `run_id`, `_llm`, et `_checkpointer` comme attributs d'instance. Les sous-classes appellent `super().__init__()` puis complètent leur propre initialisation.

### Méthodes abstraites

**`run(query: str) -> Any`**
Exécution synchrone du pipeline. Retourne un résultat structuré (le type exact est propre à chaque pack). Lève `AgentValidationError` si `query` est vide, `AgentExecutionError` en cas d'échec interne.

**`arun(query: str) -> Any`**
Exécution asynchrone. Dans `ResearchAnalysisPack`, cette méthode délègue à `run()` via `loop.run_in_executor()` pour éviter de bloquer la boucle d'événements. D'autres packs peuvent implémenter un pipeline nativement async.

**`stream_events(query: str) -> AsyncGenerator[dict, None]`**
Générateur asynchrone qui yield des dicts au format `{"event": str, "data": dict}` au fil de l'exécution. Les types d'événements reconnus par l'API sont : `phase_started`, `phase_completed`, `token`, `pipeline_completed`. Un pack peut en définir d'autres, mais `pipeline_completed` est obligatoire et doit être le dernier événement émis.

### Méthodes optionnelles

**`close() -> None`**
Hook de cycle de vie. Libère les ressources détenues par le pack (thread pool, connexions). Appelé automatiquement par `__exit__` quand le pack est utilisé comme context manager.

---

## PackRegistry : interface et comportement

`PackRegistry` est une classe sans état d'instance. Toutes les méthodes sont des `@classmethod`. Le registre est un dict de classe `_registry: dict[str, type[BaseDomainPack]]` partagé sur tout le processus.

### `register(pack_cls)`

Enregistre `pack_cls` sous sa valeur de `pack_id`. Si `pack_cls` n'a pas d'attribut `pack_id` non vide, lève `ValueError`. L'enregistrement est idempotent : enregistrer deux fois le même pack remplace silencieusement l'entrée précédente.

### `get(pack_id)`

Retourne `type[BaseDomainPack]` correspondant à `pack_id`. Si le `pack_id` n'est pas dans le registre, lève `KeyError` avec un message listant les packs disponibles, ce qui permet de diagnostiquer rapidement une faute de frappe dans `DEFAULT_PACK_ID`.

### `list_packs()`

Retourne `list[str]` — la liste triée alphabétiquement des `pack_id` enregistrés. Utilisée pour les logs de démarrage et les futures API de contrôle.

### `_reset()`

Vide le registre. Réservé aux tests : à utiliser dans un fixture pytest avec `yield` pour garantir l'isolation entre tests.

```python
@pytest.fixture(autouse=True)
def clean_registry():
    yield
    PackRegistry._reset()
```

---

## Stratégie de backward-compat

La contrainte principale est que tout code existant important `from core.graph import MultiAgentGraph` doit continuer de fonctionner sans modification.

La solution retenue est un alias de module dans `core/graph.py` :

```python
# core/graph.py
from domain_packs.research_analysis.pack import ResearchAnalysisPack

MultiAgentGraph = ResearchAnalysisPack
```

`ResearchAnalysisPack` expose exactement la même signature de constructeur et les mêmes méthodes publiques que l'ancien `MultiAgentGraph` : `run()`, `arun()`, `stream_events()`, `get_research_result()`, `close()`, `__enter__`, `__exit__`. Aucun consommateur ne voit de différence.

`OrchestratorState` est également réexporté depuis `domain_packs/research_analysis/pack.py` pour les cas (rares) où des tests référencent ce type directement.

L'API FastAPI (`api/main.py`) importe toujours `from core.graph import MultiAgentGraph` et n'a pas besoin d'être modifiée dans ce sprint. La migration vers `PackRegistry.get(settings.default_pack_id)` est prévue en sprint 2.

---

## Fichiers créés et modifiés

### Créés

| Fichier | Description |
|---|---|
| `platform/__init__.py` | Enregistre `ResearchAnalysisPack` au démarrage |
| `platform/base_pack.py` | ABC `BaseDomainPack` |
| `platform/registry.py` | `PackRegistry` |
| `domain_packs/__init__.py` | Package marker |
| `domain_packs/research_analysis/__init__.py` | Package marker |
| `domain_packs/research_analysis/pack.py` | `ResearchAnalysisPack` (pipeline Research → Analysis) |

### Modifiés

| Fichier | Modification |
|---|---|
| `core/graph.py` | Ajout de l'alias `MultiAgentGraph = ResearchAnalysisPack` ; l'implémentation de la classe est supprimée et remplacée par l'import |
| `core/config.py` | Ajout du champ `default_pack_id: str = Field(default="research_analysis", validation_alias="DEFAULT_PACK_ID")` |

### Non modifiés

`api/main.py`, `agents/`, `tests/`, `examples/`, `infra/`, `pyproject.toml`, tous les fichiers de configuration.

---

## In scope / Out of scope

### In scope

- Définition du contrat `BaseDomainPack` (ABC, attributs de classe, méthodes abstraites, lifecycle).
- Implémentation de `PackRegistry` avec `register`, `get`, `list_packs`, `_reset`.
- Migration de `MultiAgentGraph` vers `ResearchAnalysisPack` héritant de `BaseDomainPack`.
- Alias de rétrocompatibilité dans `core/graph.py`.
- Ajout de `DEFAULT_PACK_ID` dans `core/config.py`.
- Enregistrement de `ResearchAnalysisPack` dans `platform/__init__.py`.

### Out of scope

- Chargement dynamique de packs via entry points ou filesystem.
- API REST pour lister ou switcher les packs (`GET /packs`, `POST /packs/activate`).
- Connecteurs permettant à un pack de consommer la sortie d'un autre.
- Versionnement des packs (`pack_id@v2`).
- Migration de `api/main.py` pour utiliser `PackRegistry` directement (prévu sprint 2).
- Documentation des packs dans l'OpenAPI schema.

---

## Risques et mitigations

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| `platform/__init__.py` importe `domain_packs` qui importe `core` — risque de circular import | Moyenne | Bloquant | L'import de `platform` dans `api/main.py` se fait après que `core` est entièrement chargé. Les imports dans `domain_packs/research_analysis/pack.py` suivent le même ordre que l'ancien `core/graph.py` ; aucun cycle nouveau n'est introduit. |
| Un développeur enregistre deux packs avec le même `pack_id` | Faible | Silencieux | L'enregistrement est idempotent (le second écrase le premier). Ajouter un warning de log dans `register()` si la clé existe déjà est prévu pour rendre le comportement visible. |
| `PackRegistry._reset()` oublié dans un test, pollution de l'état global | Moyenne | Test flaky | Documenter l'usage de `_reset()` dans le guide de contribution. Envisager un fixture `autouse=True` dans `conftest.py` pour les tests qui touchent le registre. |
| `DEFAULT_PACK_ID` configuré sur un pack non enregistré en production | Faible | Bloquant au démarrage | `PackRegistry.get()` lève `KeyError` avec la liste des packs disponibles. Le lifespan FastAPI propagera l'exception et le processus refusera de démarrer, ce qui est le comportement souhaité (fail fast). |
