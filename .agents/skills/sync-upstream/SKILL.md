---
name: sync-upstream
description: Sync this fork with the upstream pyeventbt repo without overwriting local custom changes.
---

# sync-upstream

Checks and syncs this fork (`RhapsyDev/pyeventbt`) with the upstream (`marticastany/pyeventbt`).

## Usage

```
/sync-upstream          # muestra estado actual (behind/ahead) sin modificar nada
/sync-upstream --sync   # fetch upstream + merge upstream/develop en develop + rebase orb-strategy
```

## What it does

1. **Status mode** (`/sync-upstream`):
   - `git fetch upstream` (solo trae, no mergea)
   - Muestra `git rev-list --count` de commits behind/ahead para develop y orb-strategy
   - Dice si es seguro hacer sync

2. **Sync mode** (`/sync-upstream --sync`):
   - Stash cualquier cambio local no commiteado
   - `git checkout develop`
   - `git merge upstream/develop` (fast-forward si es posible, merge commit si no)
   - `git push origin develop`
   - `git checkout <rama-activa-al-inicio>` (la rama en la que estabas trabajando, e.g. `orb-strategy`)
   - `git merge develop` (trae los cambios nuevos a tu rama de trabajo)
   - `git push origin <rama-activa-al-inicio>`
   - Restaura stash si había cambios
   - Muestra resumen final

## Merge strategy

- `develop` → siempre merge FF/merge con upstream/develop (commit historia lineal)
- `orb-strategy` → merge develop (no rebase, no se reescribe historia local)
- Tus custom strategies en `custom_strategies/` no se tocan porque upstream no tiene esa carpeta
- El framework `pyeventbt/` se actualiza con los últimos fixes del original

## Safety

- Si hay cambios sin commit, sync los stashea automáticamente
- Si hay conflictos durante el merge, aborta y avisa (no resuelve automáticamente)
- Siempre vuelve a tu rama activa al final y mergea develop en ella (no asume `orb-strategy` fijo)
- Solo opera sobre `develop` y tu rama de trabajo actual

## AI Execution Instructions

When the user invokes this skill, follow these steps:

### Status mode (no arguments or `/sync-upstream`)
1. Run the script in status mode: `& "C:\trading\bots\pyeventbt\.agents\skills\sync-upstream\sync_upstream.ps1"` (redirect 2>$null for cleaner output)
2. Show the user the status output
3. If behind, ask if they want to sync

### Sync mode (`/sync-upstream --sync`)
1. Confirm with the user before proceeding
2. Run: `& "C:\trading\bots\pyeventbt\.agents\skills\sync-upstream\sync_upstream.ps1" -Sync` (redirect 2>$null)
3. If the script errors or reports a conflict, tell the user and suggest manual resolution
4. Show the final status
