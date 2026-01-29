### Added
- Added unsaved changes detection when closing the clipboard editor
  - When closing the editor, the system now checks if the content has been modified
  - If changes are detected, a dialog box prompts the user with three options:
    - **Yes**: Save changes to clipboard and close the editor
    - **No**: Close the editor without saving
    - **Cancel**: Return to the editor to continue editing
  - If no changes are detected, the editor closes immediately
- Added multi-language support for the new save confirmation dialog
  - Chinese translation: "文档已更改，是否保存？" (Document has been modified. Save?)
  - Ukrainian translation: "Документ змінено. Зберегти?" (Document changed. Save?)

### Changed
- Modified `clipEditor.py` to track the original content when the editor is opened
- Enhanced the `on_exit()` method to implement the save confirmation logic
- Updated `on_show()` method to record the baseline content each time the editor is displayed
