# File Tree Arrow Bug Fix Design

**Date:** 2026-05-16
**Status:** Draft
**Related Issue:** File tree arrows disappear when rapidly switching directories

## Problem Statement

When users rapidly click to switch between directories in the file tree widget, the expand/collapse arrows disappear for all directories except `data`. The arrows only reappear after restarting the application.

## Root Cause Analysis

### Current Behavior

The `_on_item_expanded` method in [`FileTreeWidget`](autoreport/gui/widgets/file_tree.py) performs operations in this order:

1. Clear all child items (line 665-667)
2. Re-apply `ShowIndicator` policy (line 671-673)

### Why It Fails

When a directory is empty (no sub-files):
- After clearing children, Qt may immediately decide to hide the arrow
- Although `ShowIndicator` is set afterward, during rapid operations this setting may be ignored or overridden
- The `data` directory is unaffected because it always has the `processed` subdirectory, maintaining child items

### Code Location

File: `autoreport/gui/widgets/file_tree.py`
Method: `_on_item_expanded` (line 653-673)

## Solution

### Approach

Reverse the operation order in `_on_item_expanded`:
1. Set `ShowIndicator` policy FIRST
2. Then clear child items

This ensures Qt knows to display the arrow before making any decisions about visibility.

### Code Changes

**Before:**
```python
while item.childCount() > 0:
    child = item.child(0)
    item.removeChild(child)

# Re-apply ShowIndicator after clearing children
item.setChildIndicatorPolicy(
    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
)
```

**After:**
```python
# Set ShowIndicator BEFORE clearing children
item.setChildIndicatorPolicy(
    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
)

while item.childCount() > 0:
    child = item.child(0)
    item.removeChild(child)
```

### Rationale

- Qt decides arrow visibility based on child indicator policy AND current state
- By setting the policy before clearing children, we ensure the policy is in place when Qt re-evaluates the item state
- This is a minimal change with no side effects on existing functionality

## Testing Strategy

### Manual Testing

1. Launch the application
2. Open a directory with files (e.g., references)
3. Rapidly click between directories: references → theory → code → tex
4. Verify all arrows remain visible throughout
5. Test with empty directories - arrows should still be visible

### Expected Results

- All directory arrows remain visible during rapid switching
- Empty directories still show expand arrows
- No change in existing file tree functionality

## Impact

- **Modified Files:** `autoreport/gui/widgets/file_tree.py`
- **Lines Changed:** ~10 lines (reordering existing code)
- **Risk Level:** Low - minimal change, no new logic
- **Backward Compatibility:** Fully compatible - no API changes
