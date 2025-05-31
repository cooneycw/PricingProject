# Server-Side Corrections Required

## Overview

After refactoring the Django GUI layer to remove business logic and implement proper separation of concerns, several critical server-side issues have been identified that require correction in the game simulation logic.

## Critical Issues Identified

### 1. **OSFI Values Not Cleared When Capital Test Passes**

**Problem**: OSFI intervention values remain in database even when capital test passes in subsequent years.

**Evidence**:
```
MCT Ratio: 205.5% (Target @ 180.0%) - PASS
Selected Profit Margin: 0.0% (OSFI Mandated) ❌
Selected Marketing Expense: 5.0% (OSFI Mandated) ❌
```

**Root Cause**: Server-side logic applies OSFI penalties but never clears them when companies recover.

**Location**: `src_code/game/game_utils.py` - `process_indications` function

### 2. **Incorrect OSFI Penalty Values**

**Problem**: Current server implementation may not match documented OSFI values.

**Expected Values** (per documentation):
- **Novice Games**: Profit Margin = 100 (10.0%), Trend Loss = 0 (0.0%)
- **Standard Games**: Profit Margin = 80 (8.0%), Trend Loss = 20 (2.0%)

**Current Implementation**: May be using 70 (7.0%) instead of 80 (8.0%) for Expert games.

### 3. **Missing Range Initialization**

**Problem**: GUI expects all min/max range values to be set by server, but some may be missing.

**Evidence**: GUI now raises errors when database values are None:
```python
if profit_min is None or profit_max is None:
    messages.error(request, f"Server error: Missing profit margin ranges")
```

## Required Server-Side Fixes

### Fix 1: Implement OSFI Value Reset Logic

**File**: `src_code/game/game_utils.py`

```python
def process_indications(game_id, year):
    # ... existing calculation logic ...
    
    # CRITICAL: Clear OSFI values when capital test passes
    if pass_capital_test == 'Pass':
        # Reset to normal decision values - remove OSFI penalties
        decision_obj.osfi_intervention_active = False
        
        # Option A: Reset to middle of allowed ranges
        decision_obj.sel_profit_margin = (decision_obj.sel_profit_margin_min + decision_obj.sel_profit_margin_max) // 2
        decision_obj.sel_exp_ratio_mktg = (decision_obj.sel_exp_ratio_mktg_min + decision_obj.sel_exp_ratio_mktg_max) // 2
        
        # Option B: Use previous year's non-OSFI values
        # decision_obj.sel_profit_margin = get_last_normal_value(player, 'profit_margin')
        
    else:
        # Apply OSFI intervention penalties
        decision_obj.osfi_intervention_active = True
        
        if is_novice_game:
            decision_obj.sel_profit_margin = 100  # 10.0%
            decision_obj.sel_loss_trend_margin = 0   # 0.0%
        else:
            decision_obj.sel_profit_margin = 80   # 8.0% (NOT 70!)
            decision_obj.sel_loss_trend_margin = 20  # 2.0%
        decision_obj.sel_exp_ratio_mktg = 0  # 0.0%
    
    decision_obj.save()
```

### Fix 2: Ensure Proper Range Initialization

**File**: `src_code/game/start_game.py` or `config/config.py`

```python
def init_decisions(game_id, player_id, year):
    """Ensure all decision objects have proper min/max ranges set"""
    
    decision_obj = Decisions(
        game_id=game_id,
        player_id=player_id,
        year=year,
        # Ensure ranges are ALWAYS set - no None values
        sel_profit_margin_min=0,     # 0.0%
        sel_profit_margin_max=100,   # 10.0% for novice, 80 for expert
        sel_exp_ratio_mktg_min=0,    # 0.0%
        sel_exp_ratio_mktg_max=50,   # 5.0%
        sel_loss_trend_margin_min=-30,  # -3.0%
        sel_loss_trend_margin_max=30,   # 3.0%
        # Set reasonable defaults
        sel_profit_margin=70,        # 7.0%
        sel_exp_ratio_mktg=20,       # 2.0%
        sel_loss_trend_margin=0,     # 0.0%
    )
    decision_obj.save()
```

### Fix 3: Add OSFI Status Tracking

**File**: `src_code/models/models.py`

```python
class Decisions(models.Model):
    # ... existing fields ...
    
    # Add OSFI tracking field
    osfi_intervention_active = models.BooleanField(default=False)
    
    # Store pre-intervention values for restoration
    pre_osfi_profit_margin = models.IntegerField(null=True, blank=True)
    pre_osfi_exp_ratio_mktg = models.IntegerField(null=True, blank=True)
    pre_osfi_loss_trend_margin = models.IntegerField(null=True, blank=True)
```

## Testing Requirements

### Test Scenario 1: OSFI Intervention Cycle
1. **Year 1**: Capital test fails → OSFI values applied
2. **Year 2**: Capital test passes → OSFI values cleared, normal values restored
3. **Year 3**: Capital test fails again → OSFI values re-applied

### Test Scenario 2: Value Persistence
1. Player sets custom values (e.g., 6.0% profit margin)
2. OSFI intervention occurs → values overridden
3. Capital test passes → custom values restored (not defaults)

### Test Scenario 3: Range Validation
1. All new games must have complete min/max ranges
2. No None values in database
3. GUI should never receive incomplete data

## Implementation Priority

### Phase 1: Critical Bug Fixes
1. ✅ **Fix OSFI value reset logic** (highest priority)
2. ✅ **Correct OSFI penalty values** (8.0% not 7.0%)
3. ✅ **Ensure range initialization**

### Phase 2: Enhancements
1. Add OSFI status tracking
2. Implement value restoration logic
3. Add comprehensive logging

### Phase 3: Validation
1. End-to-end testing of OSFI cycle
2. Multi-year game validation
3. Performance testing

## Validation Criteria

### Success Criteria:
- ✅ Capital test "Pass" → No "(OSFI Mandated)" text in GUI
- ✅ Capital test "Fail" → Correct penalty values applied
- ✅ Values reset properly when capital recovers
- ✅ No hard-coded fallbacks needed in GUI
- ✅ All database fields properly initialized

### Test Data:
```python
# Expected after capital test passes
assert decision_obj.sel_profit_margin != 0  # Not OSFI penalty
assert decision_obj.sel_profit_margin != 100  # Not OSFI penalty
assert osfi_alert == False

# Expected during OSFI intervention
assert decision_obj.sel_profit_margin == 80  # Expert game penalty
assert decision_obj.sel_profit_margin == 100  # Novice game penalty
assert osfi_alert == True
```

## Architecture Compliance

### Before (Incorrect):
```
GUI Layer: Calculates OSFI values, applies business logic
Server Layer: Basic calculations only
```

### After (Correct):
```
GUI Layer: Display only, trusts server values
Server Layer: All business logic, OSFI intervention, value management
```

## Files Requiring Changes

1. **`src_code/game/game_utils.py`** - Main OSFI logic fix
2. **`src_code/game/start_game.py`** - Range initialization
3. **`src_code/models/models.py`** - Database schema updates
4. **`src_code/models/db_utils.py`** - Database update functions
5. **`config/config.py`** - Configuration values

## Risk Assessment

### High Risk:
- Existing games may have inconsistent database states
- Migration required for OSFI status tracking

### Medium Risk:
- Player experience disruption during transition
- Need to communicate changes to users

### Low Risk:
- GUI changes are complete and tested
- Server logic is isolated and testable

## Migration Strategy

1. **Audit existing games** for OSFI inconsistencies
2. **Run data correction script** to fix stale values
3. **Deploy server fixes** with comprehensive testing
4. **Monitor first few game cycles** for issues

---

**Status**: Ready for server-side implementation
**Priority**: Critical - affects game balance and user experience
**Owner**: Server-side development team 