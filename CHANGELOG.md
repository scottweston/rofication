# Changelog

All notable changes to this project that are not yet committed.

## 2025-12-03
- Daemon: Add `del-older-than:<seconds>` communication command to purge notifications older than a given age, with validation and logging.
- GUI: Add keybindings Alt+1/2/3 to delete notifications older than 1h/8h/24h via new daemon command.
- GUI: Add Alt+z to toggle time sort (ascending/descending) and preserve selection by message ID across refreshes.
- GUI: Improve message formatting, markup handling, and keybinding definitions; minor PEP 8 style fixes.
