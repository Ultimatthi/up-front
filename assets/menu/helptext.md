=====================================================================
```
```
## Key bindings:

```
Key                 Function
----------------    ---------------------------------
LMB (hand card)     Play/discard card on active group
LMB (group tile)    Activate group
LMB (unit)          Select/deselect unit
RMB (hand card)     Cycle card mode (movement / discard on enemy)
Wheel               Cycle own active group (A–D)
Ctrl+Wheel          Cycle enemy active group (A–D)
Alt (hold)          Zoom card/unit
Space               End turn/phase, pass/accept enemy card
S                   Sniper check (active group)
P                   Voluntary panic (selected pinned units, active group)
R                   Reject terrain discarded on own group
Esc                 Leave game, back to menu
F1                  Show help
```

## Unit allocation:

- Allocate units to groups A–D using "userdata\unit_allocation.yaml".
- The file may define allocations for multiple scenarios and nations.

## Unit resolve order:

Own units:

```
┌───┐ ┌───┐ 
│ 5 │→│ 6 │→ ...
└───┘ └───┘ 
  ↑
┌───┐ ┌───┐ ┌───┐ ┌───┐
│ 1 │→│ 2 │→│ 3 │→│ 4 │
└───┘ └───┘ └───┘ └───┘
  ▲
START
```

Enemy units:

```
                   START
                     ▼
 ┌───┐ ┌───┐ ┌───┐ ┌───┐
 │ 4 │←│ 3 │←│ 2 │←│ 1 │
 └───┘ └───┘ └───┘ └───┘
                     ↓
             ┌───┐ ┌───┐
        ... ←│ 6 │←│ 5 │
             └───┘ └───┘
```
=====================================================================