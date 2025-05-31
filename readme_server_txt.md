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