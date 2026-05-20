# Design Doc — Platform Kernel

**Date** : 2026-04-21  
**Statut** : Implémenté (avec extensions au-delà du périmètre minimal initial — voir ci-dessous)  
**Auteur** : Sprint platform kernel

---

## Objectif et périmètre

Ce sprint introduit un **platform kernel** au-dessus du template LangGraph existant. L'objectif est de standardiser la façon dont les pipelines multi-agents sont déclarés, enregistrés et résolus, afin de faciliter l'ajout futur de « domain packs » métier sans dupliquer l'infrastructure API.

### Périmètre minimal initial (Sprint 1 — intention)

- Définir un contrat abstrait (`BaseDomainPack`) que tout pipeline doit respecter.
- Créer un registre explicite (`PackRegistry`) pour découvrir et résoudre les packs disponibles (**Approche B** : enregistrement ligne à ligne dans `platform/__init__.py`, pas d'auto-discovery).
- Migrer `MultiAgentGraph` (anciennement dans `core/graph.py`) vers le premier domain pack : `ResearchAnalysisPack`.
- Assurer la rétrocompatibilité pour les consommateurs existants (`MultiAgentGraph = ResearchAnalysisPack`).
- Ajouter le paramètre de configuration `DEFAULT_PACK_ID`.

### Extensions réellement implémentées (au-delà du minimal ci-dessus)

Le code inclut également : **plusieurs versions par `pack_id`** (`PackVersion`, poids, sélection pondérée ou version **explicite**), **`get_schemas`** / **`list_packs_with_metadata`**, attributs de classe **`version`**, **`input_schema` / `output_schema`**, **`budget_usd`** sur le constructeur du pack, et **endpoints HTTP** pour métadonnées des packs et ajustement des poids (`api/main.py`). Ces points ne remplacent pas l'Approche B : **l'enregistrement reste explicite** dans `platform/__init__.py`.

### Hors périmètre (toujours vrai)

Chargement dynamique sans modifier le code du noyau, **connecteurs inter-packs** dédiés, **hot reload** sans redémarrage du processus.

*(Note : une « API de contrôle plane » **complète** — ex. activation globale arbitraire sans lien avec le déploiement — n'est pas implémentée ; une **découverte HTTP** et la **mise à jour des poids** de version existent pour les packs déjà enregistrés.)*

---

## Approches considérées

### Approche A — Plugin system avec auto-discovery

Chaque domain pack est un package Python installable. Au démarrage, le registre scanne les entry points `langgraph.domain_packs` déclarés dans les `pyproject.toml` des packages installés et les enregistre automatiquement.

**Avantages** : extensible sans toucher au code du noyau, découplage fort entre packs et plateforme.

**Inconvénients** : complexité d'implémentation élevée, comportement non déterministe au démarrage (dépend des packages installés dans l'environnement), débogage difficile, trop tôt dans la maturité du projet.

### Approche B — Registre statique avec enregistrement explicite (retenu)

Un registre de classe partagé sur `PackRegistry`. Les packs sont enregistrés dans `platform/__init__.py` à l'import du package. Pas d'auto-discovery par fichiers ou entry points.

**Avantages** : comportement déterministe, lisible, testable (`PackRegistry._reset()`).

**Inconvénients** : chaque nouveau pack nécessite une modification de `platform/__init__.py` (toujours vrai).

### Approche C — Configuration déclarative (YAML/TOML)

Les packs disponibles sont listés dans un fichier de configuration. Le registre charge et instancie dynamiquement les classes via `importlib`.

**Avantages** : configuration externalisée, possible de changer les packs sans modification de code.

**Inconvénients** : loading dynamique fragile, erreurs de configuration à l'exécution, complexité accrue sans bénéfice immédiat.

### Décision

**Approche B retenue** pour l'enregistrement. Les versions multiples et les poids sont une **couche additive** au-dessus du même registre explicite (voir `platform/registry.py`).

---

## Architecture cible

```
platform/
  __init__.py           # Importe et enregistre les packs built-in
  base_pack.py          # ABC BaseDomainPack (+ version, schémas, budget_usd)
  registry.py           # PackRegistry, PackVersion

domain_packs/
  research_analysis/
    pack.py             # ResearchAnalysisPack
    schemas.py          # Modèles d'entrée/sortie (pattern recommandé)

core/
  config.py             # DEFAULT_PACK_ID, budgets, etc.
  graph.py              # Alias : MultiAgentGraph = ResearchAnalysisPack
```

Flux de résolution typique au démarrage de l'API :

1. L'import de `platform` exécute `platform/__init__.py`, qui appelle `PackRegistry.register(ResearchAnalysisPack)`.
2. Le lifespan FastAPI lit `settings.default_pack_id` (défaut : `"research_analysis"`).
3. Il appelle `PackRegistry.get(default_pack_id)` pour déterminer la classe du pack par défaut (`_active_pack_cls`).
4. Les routes legacy (`/run`, etc.) combinent ce résultat avec l'alias `MultiAgentGraph` importé depuis `core.graph` pour la compatibilité des tests et clients existants.
5. Les routes `/packs/{pack_id}/...` résolvent via `PackRegistry.get(pack_id, version=...)` selon les en-têtes / paramètres (voir `api/main.py`).

---

## Contrat de BaseDomainPack

`BaseDomainPack` est défini dans `platform/base_pack.py`. Référence source : ce fichier dans le dépôt.

### Attributs de classe (obligatoires et optionnels)

Les attributs `pack_id`, `name`, `description` sont **obligatoires** et validés par `PackRegistry.register()`.

En complément, le code supporte : `version` (défaut `"1.0"`), `input_schema` / `output_schema` (modèles Pydantic), et le constructeur accepte **`budget_usd`**.

### Méthodes abstraites

`run`, `arun`, `stream_events` — inchangées par rapport au contrat initial (voir `platform/base_pack.py`).

---

## PackRegistry : interface et comportement

Implémentation réelle : `platform/registry.py`.

Le registre interne est `_registry: dict[str, list[PackVersion]]` — une liste de versions par `pack_id`, **pas** un simple `dict[str, type]`.

### `register(pack_cls)`

Valide `pack_id`, `name`, `description`. Construit un `PackVersion` avec `version = getattr(pack_cls, "version", "1.0")`. Remplace l'entrée si la même version existe (avec **warning** log) ; sinon **ajoute** une nouvelle version.

### `get(pack_id, version=None)`

Si `version` est fourni : retourne la classe de cette version exacte. Si `version` est `None` et une seule version existe : retourne cette classe. Si plusieurs versions et `version` est `None` : sélection **aléatoire pondérée** (`random.choices`) selon `weight`. Erreurs : `KeyError` si pack/version inconnus ou si tous les poids sont nuls.

### `set_weights(pack_id, weights)`

Met à jour les poids par chaîne de version.

### `list_packs()`, `get_schemas(pack_id)`, `list_packs_with_metadata()`

Découverte et schémas JSON — utilisés par l'API HTTP et les tests.

### `_get_versions(pack_id)`, `_reset()`

`_get_versions` : liste des `PackVersion` — usage interne / introspection. `_reset()` : vide le registre (**tests uniquement**).

---

## Stratégie de backward-compat

`core/graph.py` expose :

```python
MultiAgentGraph = ResearchAnalysisPack
```

`api/main.py` importe `MultiAgentGraph` depuis `core.graph` et résout en parallèle la classe par défaut via `PackRegistry.get(settings.default_pack_id)` pour aligner le comportement runtime sur `DEFAULT_PACK_ID` tout en préservant les patches de tests sur `api.main.MultiAgentGraph`.

---

## Fichiers créés et modifiés (état actuel du dépôt)

Les fichiers listés dans la version initiale de ce document ont été étendus : notamment **`api/main.py`**, **`core/config.py`**, **`tests/`**, **`infra/Dockerfile`**, et les dossiers **`platform/`**, **`domain_packs/`** — voir l'arbre du dépôt pour la liste exacte.

---

## In scope / Out of scope (révisé)

### In scope (livré — périmètre minimal + extensions documentées plus haut)

- Contrat `BaseDomainPack` et premier pack `ResearchAnalysisPack`.
- `PackRegistry` avec enregistrement explicite, résolution par `pack_id`, **versions multiples**, **poids**, **schémas**, méthodes de listing / métadonnées (`registry.py`).
- Alias `MultiAgentGraph` dans `core/graph.py`.
- `DEFAULT_PACK_ID` et intégration API (lifespan, routes pack et legacy).
- Tests de contrat et tests API associés.

### Out of scope (non implémenté)

- Auto-discovery / chargement dynamique sans modifier `platform/__init__.py`.
- Connecteurs inter-packs dédiés.
- Hot reload du code pack sans redémarrage du processus.

### Sprint 2 (livré)

- **`ResearchOnlyPack`** (`pack_id=research_only`) — second pack enregistré dans `platform/__init__.py`.
- **Connecteur optionnel** — `ResearchAnalysisPack(connector=...)` ; API via `CONNECTOR_ENABLED` / `CONNECTOR_ID` et `core/connectors.py` (`example_memory`).
- Tests : `tests/test_research_only_pack.py`, `tests/test_connector_pack.py`, `tests/test_core_connectors.py`, `tests/test_api_connector.py`.

### Sprint 3 (livré)

- **Connecteurs** `http` + `rag` ; validation settings (`CONNECTOR_HTTP_URL`, `RAG_ENABLED` pour `rag`).
- **Control plane** — `PolicyRegistry`, `enforce.py`, application API.
- **Sticky Redis/Postgres** — `get_pack_version_for_session` pour production multi-worker friendly (préférer Redis/Postgres + `X-Pack-Version` si besoin).

---

## Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Circular imports | Ordre d'import documenté dans `api/main.py` et `platform/__init__.py` ; pas de cycle nouveau par rapport à l'ancien `core/graph.py`. |
| `DEFAULT_PACK_ID` invalide | Échec au démarrage (`KeyError` / `RuntimeError` dans le lifespan). |
| Plusieurs versions, poids à zéro | `get()` lève `KeyError` si aucun poids positif. |
