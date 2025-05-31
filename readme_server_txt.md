# Server-Side Decimal Field Modification Instructions

## Overview
The following three integer fields have been modified to act as 1 decimal place fractions while remaining stored as integers:

1. **profit_margin** (sel_profit_margin)
2. **loss_cost_trend_margin** (sel_loss_trend_margin) 
3. **marketing_expense** (sel_exp_ratio_mktg)

## Key Changes

### Storage vs Display/Calculation
- **Stored Value**: Integer (e.g., 1, 5, 10, 15)
- **Displayed Value**: Decimal with 1 place (e.g., 0.1, 0.5, 1.0, 1.5)
- **Used in Calculations**: Decimal (stored_value / 10)

### Min/Max Value Adjustments
All minimum and maximum values for these fields should be **multiplied by 10**:
- Old range: 0-10 → New range: 0-100
- Old range: -5 to 5 → New range: -50 to 50

### Range Generation
When generating ranges for dropdowns/selectors:
```python
# OLD: range(min_val, max_val + 1) displaying as integers
# NEW: range(min_val, max_val + 1) displaying as decimals
[f'{x/10:.1f}' for x in range(min_val, max_val + 1)]
```

### Form Processing
When receiving form data:
```python
# Convert decimal string to integer for storage
stored_value = int(float(form_value) * 10)
```

### Display Values
When displaying stored values:
```python
# Convert integer to decimal for display
display_value = f'{stored_value/10:.1f}'
```

### Calculation Usage
In calculations, use the decimal equivalent:
```python
# OLD: stored_value / 100 (for percentage)
# NEW: stored_value / 1000 (for percentage, since stored_value is 10x larger)

# Example for profit margin calculation:
profit_margin_decimal = stored_profit_margin / 1000
```

### Loss Trend Margin Special Case
For loss trend margin calculations in regression functions:
```python
# OLD: (1 + .01 * sel_loss_cost_margin)
# NEW: (1 + .001 * sel_loss_cost_margin)
```

## Database Migration Considerations
- Existing integer data needs to be **multiplied by 10** to maintain same effective values
- Update all seed data and default values accordingly
- Min/max constraint values need to be updated

## Template Updates
Templates should display the decimal format:
```html
<!-- OLD: {{value}} -->
<!-- NEW: {{value|floatformat:1}} or format as f'{value/10:.1f}' in view -->
```

## Testing Checklist
1. Verify range dropdowns show 0.1 increments
2. Confirm calculations use correct decimal values
3. Test form submission converts properly
4. Validate display formats show 1 decimal place
5. Check min/max values are enforced correctly
6. Ensure existing data migrates properly

## Files Modified
- `Pricing/views.py`: Range generation, form processing, calculations, display formatting
- `Pricing/utils.py`: Loss trend margin calculation scaling
- `Pricing/templates/Pricing/decision_input.html`: Display formatting (if needed)
- `Pricing/templates/Pricing/decision_confirm.html`: Display formatting (if needed)

## Example Value Mappings
| Description | Old Stored | Old Display | New Stored | New Display |
|-------------|------------|-------------|------------|-------------|
| Half percent | 1 | 1% | 5 | 0.5% |
| One percent | 2 | 2% | 10 | 1.0% |
| Two percent | 4 | 4% | 20 | 2.0% |
| Ten percent | 10 | 10% | 100 | 10.0% | 

# Terminology Change: In-Force vs Customers

## Overview
For games with difficulty level set to "Novice", all references to "In-Force" should be displayed as "Customers" instead.

Additionally, **Loss Trend Margin** field is completely hidden in Novice games to simplify the interface and remove complex actuarial concepts.

## Implementation
A helper function `get_force_term(game)` has been added to views.py:
```python
def get_force_term(game):
    """Helper function to return 'Customers' for Novice games, 'In-Force' otherwise"""
    try:
        game_prefs = GamePrefs.objects.get(user=game.initiator)
        if game_prefs.game_difficulty == 'Novice':
            return 'Customers'
    except GamePrefs.DoesNotExist:
        pass
    return 'In-Force'
```

## Novice Game Simplifications
- **Loss Trend Margin field**: Hidden from both decision input and confirmation pages
- **Default value**: Set to 0.0% (neutral) for all novice games
- **Template logic**: Uses `{% if not is_novice %}` to conditionally show/hide complex fields

## Affected Views
The following views have been updated to use dynamic terminology:
- **mktgsales_report**: "Beginning-In-Force", "Ending-In-Force", "Market-Total-Customers" (Novice) / "Industry-In-Force" (Expert)
- **financials_report**: "In-Force"
- **valuation_report**: "In-Force"
- **claim_trend_report**: "In-Force"
- **decision_input**: "In-Force"

## Special Cases
- **Marketing/Sales Report**: For Novice games, "Industry-In-Force" becomes "Market-Total-Customers" to better reflect beginner-friendly terminology

## Group Page Updates
The group page has been updated to display game difficulty information:
- **Group game listings** now show difficulty level (Novice/Expert) for each available game
- **Group game creation form** includes game difficulty selection field
- **Group view** adds difficulty information to accessible games by looking up initiator's GamePrefs

## Usage Pattern
```python
# Instead of hardcoded strings like:
new_row_name = 'In-Force'

# Use:
new_row_name = get_force_term(game)

# For prefixed/suffixed versions:
new_row_name = f'Beginning-{get_force_term(game)}'
new_row_name = f'Industry-{get_force_term(game)}'
```

## Server-Side Requirements
When implementing server-side logic, check the game difficulty and adjust terminology accordingly:
- **Novice games**: Use "Customers" terminology
- **Expert games**: Use "In-Force" terminology

The game difficulty can be accessed via the `GamePrefs` model using the game's initiator user. 

# Timezone Fix

## Issue
Dates were showing incorrectly due to timezone differences between server-side timestamp storage and client-side display.

## Root Cause
In the `fetch_game_list` AJAX endpoint, timestamps were being converted to strings using `strftime()` without proper timezone conversion, which stripped timezone information and displayed UTC times instead of local times.

## Solution
Updated the `fetch_game_list` function in `views.py` to use `timezone.localtime()` before formatting timestamps:

```python
# Before:
'timestamp': game.timestamp.strftime('%Y-%m-%d %H:%M:%S'),

# After:
local_timestamp = timezone.localtime(game.timestamp)
'timestamp': local_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
```

Also updated the JavaScript auto-refresh "Last updated" time to use the correct timezone:

```javascript
// Before:
now.toLocaleTimeString('en-GB', {hour12: false});

// After:
now.toLocaleTimeString('en-US', {hour12: false, timeZone: 'America/New_York'});
```

## Files Modified
- `Pricing/views.py`: Fixed timezone handling in `fetch_game_list` function
- `Pricing/templates/Pricing/game_list.html`: Updated JavaScript timezone formatting

## Notes
- Server timezone is set to 'America/New_York' in settings.py
- Django's template date filters are already timezone-aware and work correctly
- The issue only affected the AJAX-loaded game data, not the initial page load data 

# Decision Flow Issues Fixed

## Issue: OSFI Intervention Default Values

### Problem
1. OSFI intervention values were not in the correct format for the decimal field system
2. There was a mismatch between selector display values and calculation display values
3. OSFI intervention should pause for user confirmation, not auto-proceed
4. **Random default values when no previous decisions exist**
5. **Duplicate loss trend margin field in template causing display issues for novice games**
6. **Incorrect OSFI intervention loss trend margin value (was 10.0%, should be 2.0%)**

### Solution
Updated the OSFI intervention values in `decision_input` view to use the correct decimal display format:
```python
# OSFI Intervention Values (when MCT capital test fails):
sel_profit_margin = '7.0'    # 7.0% displayed and calculated  
sel_mktg_expense = '0.0'     # 0.0% displayed and calculated
sel_loss_margin = '2.0'      # 2.0% displayed and calculated (corrected from 10.0%)
```

**Added fallback defaults when no previous decisions exist:**
```python
elif sel_profit_margin is None:
    sel_profit_margin = '5.0'  # 5.0% default profit margin
elif sel_mktg_expense is None:
    sel_mktg_expense = '2.0'   # 2.0% default marketing expense  
elif sel_loss_margin is None:
    sel_loss_margin = '0.0'    # 0.0% default loss trend margin
```

**Fixed template duplicate loss trend margin field:**
- Removed duplicate field that was always showing
- Kept only the conditional field properly wrapped in `{% if not is_novice %}`
- Fixed display issues for both novice and expert games

**Updated OSFI intervention messages:**
- **Novice games**: "OSFI intervention active: Values set to regulatory requirements (7.0% profit, 0.0% marketing)."
- **Expert games**: "OSFI intervention active: Values set to regulatory requirements (7.0% profit, 0.0% marketing, 2.0% loss trend margin)."

## Decision Flow Confirmation

The decision flow works correctly as designed:
1. **decision_input**: User selects values and clicks "Submit"
2. **decision_confirm**: User reviews and clicks "Confirm Decisions" to finalize
3. **Auto-approval only occurs** when OSFI intervention is active (froze_lock = True)

### Normal Flow (No OSFI Intervention)
- User can freely adjust profit margin, marketing expense, and loss trend margin
- User must click "Submit" to proceed to confirmation page
- User must click "Confirm Decisions" to finalize decisions

### OSFI Intervention Flow (MCT Capital Test Fails)
- Form controls are disabled (froze_lock = True)
- Default regulatory-compliant values are automatically set
- User cannot modify values but still must confirm decisions

The system is working as intended - decisions are not being auto-approved without user confirmation. 