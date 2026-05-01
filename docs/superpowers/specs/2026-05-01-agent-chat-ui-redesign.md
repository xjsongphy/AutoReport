# Agent Chat UI Redesign Design Spec

**Date:** 2026-05-01
**Status:** Draft
**References:** [Cline](https://github.com/cline/cline), [Nanobot](https://github.com/HKUDS/nanobot)

## Problem Statement

The current agent chat UI has three critical issues:
1. **Keyboard input not working** - Enter to send, Shift+Enter for newline not responding
2. **No response feedback** - Messages sent with no indication of API call status/response
3. **Visual issues** - Inconsistent styling, unclear message hierarchy

## Design Goals

1. Fix keyboard handling (Enter/Shift+Enter)
2. Add API debug panel for visibility into requests/responses
3. Improve visual design following Cline's layout + Codex's simplicity

## Architecture

### Component Structure

```
autoreport/gui/widgets/
├── agent_panel.py          # Container (refactored)
├── chat_input.py           # Fixed keyboard handling
├── message_row.py          # New: Single message renderer
├── tool_call_group.py      # New: Collapsible tool calls
├── debug_panel.py          # New: API debug panel
└── messages_area.py        # New: Message container with scroll
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `AgentPanel` | Layout container, state coordination, signal routing |
| `ChatInput` | Text input with @ references, **fixed keyboard handling** |
| `MessageRow` | Render single message (user/agent) with timestamp |
| `ToolCallGroup` | Render tool calls with collapse/expand, status icon |
| `DebugPanel` | Show API request/response summary in collapsible panel |
| `MessagesArea` | Scrollable container for messages |

## Visual Design (Cline-inspired)

### Color Scheme

```python
# Dark mode (existing, refined)
claude_orange = "#d97757"
header_bg = "#252526"
msg_bg = "#1e1e1e"
user_bubble = "#0e639c"
agent_bubble = "#2d2d2d"

# New: Status colors
status_thinking = "#4fc3f7"
status_tool = "#ffb74d"
status_error = "#f14c4c"
status_success = "#81c784"
```

### Layout

```
┌─────────────────────────────────────────────────┐
│ 🤖 Data Analysis Agent  [空闲] [🔍 Debug]     │ Header
├─────────────────────────────────────────────────┤
│                                                 │
│  14:32  你                                     │ Message
│    请分析这个数据...                            │
│                                                 │
│  14:32  Agent  [▶]                             │ Message
│    我来分析数据...                              │
│    ✎ python_exec(data_analysis.py)            │ ToolCall (collapsed)
│    ✓ Analysis complete                         │
│                                                 │
├─────────────────────────────────────────────────┤
│ 🔍 API Debug                   [▼] 3 calls    │ DebugPanel
├─────────────────────────────────────────────────┤
│ 📄 3 lines selected  👁                         │ ContextBar
├─────────────────────────────────────────────────┤
│ [输入消息… (@ 引用文件)              [↑] Send] │ InputBar
└─────────────────────────────────────────────────┘
```

## Key Changes

### 1. ChatInput Keyboard Fix

**Problem:** `keyPressEvent` not handling Enter/Shift+Enter correctly.

**Solution:**
```python
def keyPressEvent(self, event: QKeyEvent):
    key = event.key()
    modifiers = event.modifiers()

    # Enter sends message, Shift+Enter for newline
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Shift+Enter: insert newline
            cursor = self.textCursor()
            cursor.insertText("\n")
            return
        elif modifiers == Qt.KeyboardModifier.NoModifier:
            # Plain Enter: send message
            self.send_message.emit()
            return

    super().keyPressEvent(event)
```

### 2. DebugPanel Component

**Purpose:** Show API request/response summary for debugging.

**Display format:**
```
🔍 API Debug (3 calls) [▼]
  14:32:15 → POST /v1/messages (claude-sonnet-4-20250514)
    Tokens: 1234 in, 567 out | Duration: 2.3s
    Status: ✓ Success

  14:31:02 → POST /v1/messages (claude-sonnet-4-20250514)
    Error: ✗ Rate limit exceeded

  [Copy to clipboard] [Clear all]
```

**DebugPanel Data Management:**
- Max 50 entries, FIFO eviction (prevent memory leaks)
- Clear button to reset all entries
- Export to JSON for analysis
- Compact 1-line summary per call, expandable for details

### 3. ToolCallGroup Component

**Purpose:** Group tool calls with collapse/expand.

**Collapsed:**
```
  ✓ 3 tools executed (2.3s) [▶]
```

**Expanded:**
```
  ✓ python_exec (1.2s)
    result: analysis_complete.json

  ✓ read_file (0.1s)
    file: data/input.csv

  ✗ write_file (0.5s)
    error: Permission denied
```

**ToolCallGroup Details:**
- No nested tool call support (flatten to sequential list)
- Max 3 tool names visible in collapsed state, then "+N more"
- No animation/transition (keep it simple for PyQt6)

### 4. MessageRow Component

**Purpose:** Unified message rendering.

**Format:**
```
HH:MM  [Role]  [Status]

  Content line 1
  Content line 2
```

### 5. Visual Polish

- Input border radius: 8px → 12px
- Add subtle shadow to input bar
- Send button: circular with ↑ icon
- Tool calls: monospace font, status icons
- Debug panel: monospace, muted colors

## Data Flow

### Message Flow

```
User types in ChatInput
  ↓ (Enter)
AgentPanel._on_send()
  ↓ (emit signal)
Backend: AgentLoop.process_message()
  ↓ (streaming)
AgentPanel.add_message(role="agent", content=..., streaming=True)
  ↓ (append content)
MessagesArea.update()
```

### Debug Info Flow

```
Backend: API call made
  ↓ (emit signal with metadata)
AgentPanel.add_api_debug(request, response, duration)
  ↓
DebugPanel.add_entry()
  ↓
DebugPanel.update_display()
```

## Error Handling

1. **Keyboard failures:** Log to console, show tooltip "Press Enter to send"
2. **API errors:** Display in DebugPanel with red ✗ icon
3. **Tool failures:** Display in ToolCallGroup with error details
4. **Stream interruption:** Show "Response incomplete" indicator

## Implementation Notes

### Files to Modify

| File | Change Type | Description |
|------|-------------|-------------|
| `chat_input.py` | Fix | Correct keyboard handling |
| `agent_panel.py` | Refactor | Extract to new components |
| `message_row.py` | New | Single message renderer |
| `tool_call_group.py` | New | Collapsible tool calls |
| `debug_panel.py` | New | API debug panel |

### Backend Integration

The backend needs to emit debug metadata:

```python
# In AgentLoop or LoopManager
self.api_debug_sent.emit({
    "timestamp": datetime.now(),
    "model": "claude-sonnet-4-20250514",
    "tokens_in": 1234,
    "tokens_out": 567,
    "duration_ms": 2300,
    "status": "success" | "error",
    "error": "error message" if error else None
})
```

**Backend Signal Integration Details:**
- Hook in `AgentLoop._call_llm_api()` - emit before API call (start time) and after response (end time)
- Use `QMetaObject.invokeMethod` for thread-safe GUI updates from background threads
- For streaming responses: emit final debug info on stream completion, not per-chunk
- Signal type: `pyqtSignal(dict)` named `api_debug_sent`

### Streaming Display Behavior

- Don't parse/render markdown until stream complete (show raw text during streaming)
- Auto-scroll to bottom during stream, pause if user scrolls up
- Show "● 思考中…" indicator with animated colors during stream
- On stream completion: parse markdown, apply syntax highlighting to code blocks

## Testing Checklist

### Keyboard & Input
- [ ] Enter sends message
- [ ] Shift+Enter inserts newline
- [ ] Ctrl+Enter, other combos work correctly
- [ ] @ file reference popup triggers correctly
- [ ] File search results display and select properly
- [ ] Inserted file references format correctly

### UI Components
- [ ] Debug panel expands/collapses
- [ ] Tool call group expands/collapses
- [ ] Stream responses append correctly
- [ ] Error messages display in debug panel
- [ ] Dark/light mode colors work

### Debug Features
- [ ] API debug entries populate correctly
- [ ] Debug panel FIFO eviction works at 50 entries
- [ ] Copy to clipboard works for debug entries
- [ ] Export to JSON works
- [ ] Clear button removes all entries

## Future Enhancements

1. Message copying to clipboard
2. Message editing/regeneration
3. Image attachments (Nanobot-style)
4. Voice input support
5. Export chat history
