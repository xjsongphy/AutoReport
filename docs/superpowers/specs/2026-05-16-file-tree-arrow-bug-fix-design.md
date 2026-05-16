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

### Why This Fixes the Qt Timing Issue

**Qt's Internal Behavior:**
- Qt's `QTreeWidget` evaluates item visibility (including arrows) based on:
  1. Current child indicator policy
  2. Current item state (has children or not)
- When `childIndicatorPolicy` is `ShowIndicator`, Qt ignores child count and always shows the arrow

**The Original Bug:**
- Original code: Clear children → Set `ShowIndicator`
- Between these two operations, Qt sees: policy=undefined/previous, children=empty
- Qt decides: "No children + no explicit show policy → hide arrow"
- Setting `ShowIndicator` afterward doesn't always trigger a re-render during rapid operations

**The Fix:**
- Fixed code: Set `ShowIndicator` → Clear children
- Throughout the operation: policy=ShowIndicator (even during clearing)
- Qt decides: "ShowIndicator policy → always show arrow, regardless of child count"

**Why Original Order Was Chosen:**
- The original order was likely an oversight rather than intentional
- Comment says "Re-apply ShowIndicator after clearing" suggesting it was meant to be a restore operation
- The assumption was that re-applying after clearing would be sufficient
- This assumption fails under rapid user interaction due to Qt's internal state evaluation timing

**Qt Version Considerations:**
- This behavior is consistent across Qt 6.x versions
- The fix is safe for all Qt 6 versions as it uses documented API behavior
- No performance impact - setting a policy flag is O(1)

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
# Set ShowIndicator BEFORE clearing children to prevent Qt from hiding
# the arrow during rapid directory switching. See spec docs for details.
item.setChildIndicatorPolicy(
    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
)

while item.childCount() > 0:
    child = item.child(0)
    item.removeChild(child)
```

### Code Comment Requirements

Add the following comment before the `setChildIndicatorPolicy` call:

```python
# IMPORTANT: Set ShowIndicator BEFORE clearing children.
# Qt evaluates arrow visibility based on policy AND current state.
# If we clear children first, Qt may hide the arrow before we can
# re-apply the policy, especially during rapid user interactions.
```

This comment prevents future developers from "cleaning up" the seemingly redundant call.

### Rationale

- Qt decides arrow visibility based on child indicator policy AND current state
- By setting the policy before clearing children, we ensure the policy is in place when Qt re-evaluates the item state
- This is a minimal change with no side effects on existing functionality

## Testing Strategy

### Manual Testing

1. **Basic rapid switching:**
   - Launch the application
   - Open a directory with files (e.g., references)
   - Rapidly click between directories: references → theory → code → tex
   - Verify all arrows remain visible throughout

2. **Edge cases:**
   - Expand/collapse the same directory repeatedly 10+ times
   - Rapidly switch while a directory is loading content
   - Test with empty directories - arrows should still be visible
   - Test the `data` directory specifically (has `processed` subdirectory)
   - Test drag-drop operations into directories during/after rapid switching
   - Add/delete directories during runtime and verify arrows remain

3. **Verification of Qt timing fix:**
   - The fix ensures `ShowIndicator` is set before Qt re-evaluates item state
   - After applying the fix, run the same rapid switching sequence that caused the bug
   - Confirm arrows persist where they previously disappeared

### Expected Results

- All directory arrows remain visible during rapid switching
- Empty directories still show expand arrows
- No change in existing file tree functionality (drag-drop, inline create, etc.)
- No performance degradation during rapid operations

## Impact

- **Modified Files:** `autoreport/gui/widgets/file_tree.py`
- **Lines Changed:** ~10 lines (reordering existing code)
- **Risk Level:** Low - minimal change, no new logic
- **Backward Compatibility:** Fully compatible - no API changes
